package httpapi

import (
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/domainxml"
	"golang.org/x/crypto/ssh"
)

type sshTargetProvider interface {
	DomainSSHTargets(context.Context, string) ([]string, error)
}

func sshTargetsHandler(deps Dependencies) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		provider, ok := deps.Virtualizer.(sshTargetProvider)
		if !ok || !domainxml.ValidName(r.PathValue("name")) {
			http.Error(w, "SSH target lookup unavailable", 409)
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
		defer cancel()
		addresses, err := provider.DomainSSHTargets(ctx, r.PathValue("name"))
		if err != nil {
			http.Error(w, "SSH target lookup failed", 409)
			return
		}
		writeJSON(w, 200, map[string]any{"addresses": addresses, "port": 22})
	}
}

type sshMessage struct {
	Type        string `json:"type"`
	User        string `json:"user"`
	Password    string `json:"password"`
	PrivateKey  string `json:"private_key"`
	Passphrase  string `json:"passphrase"`
	Fingerprint string `json:"fingerprint"`
	Data        string `json:"data"`
	Cols        int    `json:"cols"`
	Rows        int    `json:"rows"`
}

func sshSize(cols, rows int) bool { return cols >= 20 && cols <= 512 && rows >= 5 && rows <= 200 }

type sshOutput struct {
	socket *websocket.Conn
	mutex  *sync.Mutex
}

func (out sshOutput) Write(data []byte) (int, error) {
	out.mutex.Lock()
	defer out.mutex.Unlock()
	if err := out.socket.WriteMessage(websocket.BinaryMessage, data); err != nil {
		return 0, err
	}
	return len(data), nil
}

func sshProxyHandler(deps Dependencies) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ticket, valid := parseConsoleTicket(deps.Token, r.Header.Get("X-Console-Ticket"))
		origin, err := url.Parse(r.Header.Get("Origin"))
		if !valid || ticket.Protocol != "ssh" || net.ParseIP(ticket.Address) == nil || err != nil || origin.Host != r.Host || (origin.Scheme != "https" && origin.Scheme != "http") || r.URL.RawQuery != "" {
			http.Error(w, "SSH authorization denied", 401)
			return
		}
		provider, ok := deps.Virtualizer.(sshTargetProvider)
		if !ok {
			http.Error(w, "SSH unavailable", 409)
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), 10*time.Second)
		addresses, err := provider.DomainSSHTargets(ctx, ticket.Domain)
		cancel()
		allowed := false
		for _, address := range addresses {
			if address == ticket.Address {
				allowed = true
			}
		}
		if err != nil || !allowed || !consumeConsoleTicket(ticket) {
			http.Error(w, "SSH target or ticket invalid", 403)
			return
		}
		upgrader := websocket.Upgrader{ReadBufferSize: 4096, WriteBufferSize: 32768,
			CheckOrigin: func(_ *http.Request) bool { return true }, EnableCompression: false}
		ws, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		defer ws.Close()
		ws.SetReadLimit(128 << 10)
		ws.SetReadDeadline(time.Now().Add(30 * time.Second))
		var writeMu sync.Mutex
		send := func(message map[string]any) {
			writeMu.Lock()
			defer writeMu.Unlock()
			_ = ws.WriteJSON(message)
		}
		fail := func(message string) { send(map[string]any{"type": "error", "message": message}) }
		var initial sshMessage
		if ws.ReadJSON(&initial) != nil || initial.Type != "auth" || len(initial.User) == 0 || len(initial.User) > 128 || strings.ContainsAny(initial.User, "\x00\r\n") || !sshSize(initial.Cols, initial.Rows) {
			fail("SSH 登录参数无效")
			return
		}
		var auth ssh.AuthMethod
		if initial.PrivateKey != "" {
			if len(initial.PrivateKey) > 65536 || len(initial.Passphrase) > 4096 {
				fail("私钥或口令过长")
				return
			}
			var signer ssh.Signer
			if initial.Passphrase != "" {
				signer, err = ssh.ParsePrivateKeyWithPassphrase([]byte(initial.PrivateKey), []byte(initial.Passphrase))
			} else {
				signer, err = ssh.ParsePrivateKey([]byte(initial.PrivateKey))
			}
			if err != nil {
				fail("私钥格式或私钥口令无效")
				return
			}
			auth = ssh.PublicKeys(signer)
		} else {
			if len(initial.Password) == 0 || len(initial.Password) > 4096 {
				fail("请输入有效密码或私钥")
				return
			}
			auth = ssh.Password(initial.Password)
		}
		initial.Password = ""
		initial.PrivateKey = ""
		initial.Passphrase = ""
		targetAddress := net.JoinHostPort(ticket.Address, "22")
		dial := deps.SSHDial
		if dial == nil {
			dial = net.DialTimeout
		}
		target, err := dial("tcp", targetAddress, 5*time.Second)
		if err != nil {
			fail("无法连接虚拟机 SSH，请检查服务、端口 22 和防火墙")
			return
		}
		defer target.Close()
		if !trackConsole(ticket.SID, ws.UnderlyingConn(), target) {
			fail("连接数达到上限")
			return
		}
		defer untrackConsole(ticket.SID)
		handshakeTimer := time.AfterFunc(60*time.Second, func() { target.Close(); ws.Close() })
		defer handshakeTimer.Stop()
		config := &ssh.ClientConfig{User: initial.User, Auth: []ssh.AuthMethod{auth}, Timeout: 10 * time.Second,
			HostKeyCallback: func(_ string, _ net.Addr, key ssh.PublicKey) error {
				fingerprint := ssh.FingerprintSHA256(key)
				send(map[string]any{"type": "hostkey", "fingerprint": fingerprint, "algorithm": key.Type(), "address": ticket.Address})
				var confirmation sshMessage
				if ws.ReadJSON(&confirmation) != nil || confirmation.Type != "trust" || confirmation.Fingerprint != fingerprint {
					return fmt.Errorf("host key not confirmed")
				}
				return nil
			}}
		connection, channels, requests, err := ssh.NewClientConn(target, targetAddress, config)
		config.Auth = nil
		if err != nil {
			fail("SSH 握手或认证失败，请核对指纹、用户名和凭据")
			return
		}
		handshakeTimer.Stop()
		client := ssh.NewClient(connection, channels, requests)
		defer client.Close()
		session, err := client.NewSession()
		if err != nil {
			fail("无法创建 SSH 终端")
			return
		}
		defer session.Close()
		input, err := session.StdinPipe()
		if err != nil {
			return
		}
		output := sshOutput{ws, &writeMu}
		session.Stdout = output
		session.Stderr = output
		if session.RequestPty("xterm-256color", initial.Rows, initial.Cols, ssh.TerminalModes{ssh.ECHO: 1}) != nil || session.Shell() != nil {
			fail("SSH 服务拒绝交互式终端")
			return
		}
		_ = target.SetDeadline(time.Now().Add(90 * time.Second))
		_ = ws.SetReadDeadline(time.Now().Add(90 * time.Second))
		maximum := time.AfterFunc(2*time.Hour, func() { target.Close(); ws.Close() })
		defer maximum.Stop()
		send(map[string]any{"type": "ready"})
		go func() {
			err := session.Wait()
			if err == nil {
				send(map[string]any{"type": "exit"})
			} else {
				send(map[string]any{"type": "exit", "message": "远程终端已结束"})
			}
			ws.Close()
		}()
		for {
			var message sshMessage
			if ws.ReadJSON(&message) != nil {
				return
			}
			switch message.Type {
			case "input":
				if len(message.Data) > 65536 {
					return
				}
				if _, err := io.WriteString(input, message.Data); err != nil {
					return
				}
			case "resize":
				if !sshSize(message.Cols, message.Rows) {
					return
				}
				if session.WindowChange(message.Rows, message.Cols) != nil {
					return
				}
			default:
				return
			}
		}
	}
}
