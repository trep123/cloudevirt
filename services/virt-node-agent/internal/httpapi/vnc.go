package httpapi

import (
	"bufio"
	"crypto/sha1"
	"encoding/base64"
	"encoding/binary"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
)

const websocketGUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

// websocketAccept 计算 Sec-WebSocket-Accept。
func websocketAccept(key string) string {
	sum := sha1.Sum([]byte(key + websocketGUID))
	return base64.StdEncoding.EncodeToString(sum[:])
}

// vncProxyHandler 把 WebSocket 连接桥接到本地 VNC 端口。
func vncProxyHandler(deps Dependencies) http.HandlerFunc {
	return func(writer http.ResponseWriter, request *http.Request) {
		requestID := RequestIDFromContext(request.Context())
		ticket, valid := parseConsoleTicket(deps.Token, request.Header.Get("X-Console-Ticket"))
		origin, originError := url.Parse(request.Header.Get("Origin"))
		if !valid || (ticket.Protocol != "" && ticket.Protocol != "vnc") || originError != nil || origin.Host != request.Host || (origin.Scheme != "http" && origin.Scheme != "https") || request.URL.RawQuery != "" {
			writeAPIError(writer, deps.Logger, apierr.New(
				apierr.CodeUnauthorized, "控制台凭证无效", nil,
			), requestID)
			return
		}
		if !consumeConsoleTicket(ticket) {
			writeAPIError(writer, deps.Logger, apierr.New(
				apierr.CodeUnauthorized, "控制台凭证无效或已过期", nil,
			), requestID)
			return
		}
		if !strings.EqualFold(request.Header.Get("Upgrade"), "websocket") || request.Header.Get("Sec-WebSocket-Key") == "" {
			writeAPIError(writer, deps.Logger, apierr.New(
				apierr.CodeInvalidArgument, "需要 WebSocket 升级请求", nil,
			), requestID)
			return
		}
		key, keyError := base64.StdEncoding.DecodeString(request.Header.Get("Sec-WebSocket-Key"))
		if request.Header.Get("Sec-WebSocket-Version") != "13" || keyError != nil || len(key) != 16 {
			writeAPIError(writer, deps.Logger, apierr.New(apierr.CodeInvalidArgument, "WebSocket 握手无效", nil), requestID)
			return
		}
		if deps.Virtualizer == nil {
			writeAPIError(writer, deps.Logger, errNoVirtualizer, requestID)
			return
		}
		port, err := deps.Virtualizer.DomainVNCPort(request.Context(), ticket.Domain)
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		target, err := net.DialTimeout("tcp", fmt.Sprintf("127.0.0.1:%d", port), 5*time.Second)
		if err != nil {
			writeAPIError(writer, deps.Logger, apierr.New(
				apierr.CodeOperationFailed, "无法连接虚拟机控制台", err,
			), requestID)
			return
		}
		defer target.Close()

		hijacker, ok := writer.(http.Hijacker)
		if !ok {
			writeAPIError(writer, deps.Logger, apierr.New(
				apierr.CodeInternalError, "当前服务不支持 WebSocket", nil,
			), requestID)
			return
		}
		connection, buffered, err := hijacker.Hijack()
		if err != nil {
			writeAPIError(writer, deps.Logger, apierr.New(
				apierr.CodeInternalError, "WebSocket 升级失败", err,
			), requestID)
			return
		}
		defer connection.Close()
		_ = connection.SetDeadline(time.Time{})
		if !trackConsole(ticket.SID, connection, target) {
			return
		}
		defer untrackConsole(ticket.SID)

		accept := websocketAccept(request.Header.Get("Sec-WebSocket-Key"))
		if _, err := fmt.Fprintf(
			connection,
			"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: %s\r\n\r\n",
			accept,
		); err != nil {
			return
		}

		var writeMu sync.Mutex
		go func() {
			forwardVNCServerToWebSocket(target, connection, &writeMu)
			connection.Close()
		}()
		proxyWebSocketToVNC(buffered.Reader, target, connection, &writeMu)
	}
}

// proxyWebSocketToVNC 读取客户端帧并写入 VNC 连接。
func proxyWebSocketToVNC(reader *bufio.Reader, target net.Conn, connection net.Conn, writeMu *sync.Mutex) {
	var fragments []byte
	var messageOpcode byte
	for {
		opcode, final, payload, err := readClientFrame(reader)
		if err != nil {
			return
		}
		switch opcode {
		case 0x8:
			return
		case 0x9:
			_ = writeWebSocketFrame(connection, 0xA, payload, writeMu)
		case 0xA:
			continue
		case 0x0:
			if messageOpcode == 0 {
				return
			}
			fragments = append(fragments, payload...)
			if len(fragments) > 4<<20 {
				return
			}
			if final {
				_, _ = target.Write(fragments)
				fragments = nil
				messageOpcode = 0
			}
		case 0x2:
			if messageOpcode != 0 {
				return
			}
			if final {
				_, _ = target.Write(payload)
				continue
			}
			messageOpcode = opcode
			fragments = append(fragments[:0], payload...)
		}
	}
}

// forwardVNCServerToWebSocket 把 VNC 输出封装为 WebSocket 二进制帧。
func forwardVNCServerToWebSocket(target net.Conn, connection net.Conn, writeMu *sync.Mutex) {
	buffer := make([]byte, 32*1024)
	for {
		read, err := target.Read(buffer)
		if read > 0 {
			if writeErr := writeWebSocketFrame(connection, 0x2, buffer[:read], writeMu); writeErr != nil {
				return
			}
		}
		if err != nil {
			return
		}
	}
}

// readClientFrame 读取一个客户端 WebSocket 帧（必须带掩码）。
func readClientFrame(reader *bufio.Reader) (byte, bool, []byte, error) {
	header := make([]byte, 2)
	if _, err := io.ReadFull(reader, header); err != nil {
		return 0, false, nil, err
	}
	final := header[0]&0x80 != 0
	opcode := header[0] & 0x0F
	if header[0]&0x70 != 0 || (opcode != 0 && opcode != 2 && opcode != 8 && opcode != 9 && opcode != 10) {
		return 0, false, nil, fmt.Errorf("不支持的 WebSocket 帧")
	}
	masked := header[1]&0x80 != 0
	length := int64(header[1] & 0x7F)
	switch length {
	case 126:
		extended := make([]byte, 2)
		if _, err := io.ReadFull(reader, extended); err != nil {
			return 0, false, nil, err
		}
		length = int64(binary.BigEndian.Uint16(extended))
	case 127:
		extended := make([]byte, 8)
		if _, err := io.ReadFull(reader, extended); err != nil {
			return 0, false, nil, err
		}
		value := binary.BigEndian.Uint64(extended)
		if value > 4<<20 {
			return 0, false, nil, fmt.Errorf("帧过大")
		}
		length = int64(value)
	}
	if !masked {
		return 0, false, nil, fmt.Errorf("客户端帧必须带掩码")
	}
	if opcode >= 8 && (!final || length > 125) {
		return 0, false, nil, fmt.Errorf("控制帧无效")
	}
	mask := make([]byte, 4)
	if _, err := io.ReadFull(reader, mask); err != nil {
		return 0, false, nil, err
	}
	payload := make([]byte, length)
	if _, err := io.ReadFull(reader, payload); err != nil {
		return 0, false, nil, err
	}
	for index := range payload {
		payload[index] ^= mask[index%4]
	}
	return opcode, final, payload, nil
}

// writeWebSocketFrame 发送服务端帧（不带掩码）。
func writeWebSocketFrame(writer io.Writer, opcode byte, payload []byte, writeMu *sync.Mutex) error {
	writeMu.Lock()
	defer writeMu.Unlock()

	header := []byte{0x80 | opcode}
	length := len(payload)
	switch {
	case length < 126:
		header = append(header, byte(length))
	case length <= 65535:
		header = append(header, 126, byte(length>>8), byte(length))
	default:
		header = append(header, 127, 0, 0, 0, 0,
			byte(length>>24), byte(length>>16), byte(length>>8), byte(length))
	}
	if _, err := writer.Write(header); err != nil {
		return err
	}
	_, err := writer.Write(payload)
	return err
}
