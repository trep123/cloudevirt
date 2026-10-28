package httpapi

import (
	"bufio"
	"bytes"
	"testing"
)

// TestWebSocketAccept 校验 RFC 6455 握手示例。
func TestWebSocketAccept(t *testing.T) {
	got := websocketAccept("dGhlIHNhbXBsZSBub25jZQ==")
	want := "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
	if got != want {
		t.Fatalf("accept 错误: got=%s want=%s", got, want)
	}
}

// TestReadClientFrame 校验带掩码的客户端帧解析。
func TestReadClientFrame(t *testing.T) {
	payload := []byte("hello")
	mask := []byte{1, 2, 3, 4}
	var buffer bytes.Buffer
	buffer.WriteByte(0x82)
	buffer.WriteByte(0x80 | byte(len(payload)))
	buffer.Write(mask)
	for index, value := range payload {
		buffer.WriteByte(value ^ mask[index%4])
	}

	opcode, final, decoded, err := readClientFrame(bufio.NewReader(&buffer))
	if err != nil {
		t.Fatalf("解析失败: %v", err)
	}
	if opcode != 0x2 || !final || string(decoded) != "hello" {
		t.Fatalf("帧内容错误: opcode=%d final=%v payload=%q", opcode, final, decoded)
	}
}

func TestReadClientFrameRejectsInvalidControlAndUnmaskedData(t *testing.T) {
	for name, raw := range map[string][]byte{
		"unmasked":           {0x82, 0},
		"reserved-bit":       {0xc2, 0x80, 0, 0, 0, 0},
		"text":               {0x81, 0x80, 0, 0, 0, 0},
		"fragmented-control": {0x09, 0x80, 0, 0, 0, 0},
		"oversized-control":  {0x89, 0xfe, 0, 126, 0, 0, 0, 0},
	} {
		t.Run(name, func(t *testing.T) {
			if _, _, _, err := readClientFrame(bufio.NewReader(bytes.NewReader(raw))); err == nil {
				t.Fatal("invalid frame accepted")
			}
		})
	}
}
