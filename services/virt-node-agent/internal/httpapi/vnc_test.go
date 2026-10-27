package httpapi

import (
	"bufio"
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"testing"
	"time"
)

// TestWebSocketAccept 校验 RFC 6455 握手示例。
func TestWebSocketAccept(t *testing.T) {
	got := websocketAccept("dGhlIHNhbXBsZSBub25jZQ==")
	want := "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
	if got != want {
		t.Fatalf("accept 错误: got=%s want=%s", got, want)
	}
}

// TestConsoleSignature 校验签名与过期时间。
func TestConsoleSignature(t *testing.T) {
	secret := "shared-secret"
	domain := "cv-test"
	expiresAt := time.Now().Add(60 * time.Second).Unix()
	mac := hmac.New(sha256.New, []byte(secret))
	fmt.Fprintf(mac, "%s|%d", domain, expiresAt)
	signature := hex.EncodeToString(mac.Sum(nil))

	if !validConsoleSignature(secret, domain, expiresAt, signature) {
		t.Fatal("有效签名被拒绝")
	}
	if validConsoleSignature(secret, domain, expiresAt, "bad") {
		t.Fatal("错误签名被接受")
	}
	if validConsoleSignature(secret, domain, time.Now().Add(-120*time.Second).Unix(), signature) {
		t.Fatal("过期签名被接受")
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
