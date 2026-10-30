package httpapi

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"golang.org/x/crypto/ssh"
)

type fakeSSHTarget struct{ fakeOperator }

func (f *fakeSSHTarget) DomainSSHTargets(context.Context, string) ([]string, error) {
	return []string{"192.0.2.50"}, nil
}

func TestSSHWebSocketRequiresTrustBeforeAuthenticationAndRelaysTerminal(t *testing.T) {
	testSSHRelay(t, true)
}

func TestSSHWrongFingerprintNeverAuthenticates(t *testing.T) {
	testSSHRelay(t, false)
}

func testSSHRelay(t *testing.T, accept bool) {
	_, private, _ := ed25519.GenerateKey(rand.Reader)
	signer, _ := ssh.NewSignerFromKey(private)
	var authenticated atomic.Int32
	config := &ssh.ServerConfig{PasswordCallback: func(meta ssh.ConnMetadata, password []byte) (*ssh.Permissions, error) {
		authenticated.Add(1)
		if meta.User() != "tester" || string(password) != "test-password" {
			return nil, fmt.Errorf("denied")
		}
		return nil, nil
	}}
	config.AddHostKey(signer)
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	go func() {
		conn, err := listener.Accept()
		if err != nil {
			return
		}
		defer conn.Close()
		server, channels, requests, err := ssh.NewServerConn(conn, config)
		if err != nil {
			return
		}
		defer server.Close()
		go ssh.DiscardRequests(requests)
		for channel := range channels {
			if channel.ChannelType() != "session" {
				channel.Reject(ssh.UnknownChannelType, "session only")
				continue
			}
			stream, requests, err := channel.Accept()
			if err != nil {
				return
			}
			go func() { defer stream.Close(); io.Copy(stream, stream) }()
			go func() {
				for request := range requests {
					request.Reply(request.Type == "pty-req" || request.Type == "shell" || request.Type == "window-change", nil)
				}
			}()
		}
	}()
	deps := testDependencies()
	deps.Virtualizer = &fakeSSHTarget{}
	deps.SSHDial = func(_, address string, _ time.Duration) (net.Conn, error) {
		if address != "192.0.2.50:22" {
			return nil, fmt.Errorf("wrong target")
		}
		return net.Dial("tcp", listener.Addr().String())
	}
	server := httptest.NewServer(NewRouter(deps))
	defer server.Close()
	id := "b6bd1000-1234-4234-8234-000000000001"
	if !accept {
		id = "b6bd1000-1234-4234-8234-000000000002"
	}
	t.Cleanup(func() { consoleConnections.Lock(); delete(consoleConnections.used, id); consoleConnections.Unlock() })
	token := signedSSHTicket(deps.Token, id, "192.0.2.50")
	headers := http.Header{"Origin": []string{server.URL}, "X-Console-Ticket": []string{token}}
	ws, _, err := websocket.DefaultDialer.Dial(strings.Replace(server.URL, "http:", "ws:", 1)+"/ssh", headers)
	if err != nil {
		t.Fatal(err)
	}
	defer ws.Close()
	ws.SetReadDeadline(time.Now().Add(5 * time.Second))
	if err := ws.WriteJSON(map[string]any{"type": "auth", "user": "tester", "password": "test-password", "cols": 80, "rows": 24}); err != nil {
		t.Fatal(err)
	}
	var message map[string]any
	if err := ws.ReadJSON(&message); err != nil {
		t.Fatal(err)
	}
	if message["type"] != "hostkey" || message["fingerprint"] != ssh.FingerprintSHA256(signer.PublicKey()) {
		t.Fatalf("missing verified host key: %v", message)
	}
	if authenticated.Load() != 0 {
		t.Fatal("password sent before user trusted host key")
	}
	if !accept {
		ws.WriteJSON(map[string]any{"type": "trust", "fingerprint": "SHA256:wrong"})
		if err := ws.ReadJSON(&message); err != nil {
			t.Fatal(err)
		}
		if message["type"] != "error" || authenticated.Load() != 0 {
			t.Fatal("untrusted key authenticated")
		}
		return
	}
	ws.WriteJSON(map[string]any{"type": "trust", "fingerprint": message["fingerprint"]})
	if err := ws.ReadJSON(&message); err != nil {
		t.Fatal(err)
	}
	if message["type"] != "ready" || authenticated.Load() != 1 {
		t.Fatalf("not ready: %v", message)
	}
	ws.WriteJSON(map[string]any{"type": "resize", "cols": 100, "rows": 30})
	ws.WriteJSON(map[string]any{"type": "input", "data": "terminal-echo-test"})
	kind, data, err := ws.ReadMessage()
	if err != nil || kind != websocket.BinaryMessage || string(data) != "terminal-echo-test" {
		t.Fatalf("echo failed %d %q %v", kind, data, err)
	}
	ws.Close()
	deadline := time.Now().Add(time.Second)
	for time.Now().Before(deadline) {
		consoleConnections.Lock()
		_, active := consoleConnections.active[id]
		consoleConnections.Unlock()
		if !active {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatal("disconnected SSH lease leaked")
}

func signedSSHTicket(secret, id, address string) string {
	return signedConsoleTicket(secret, consoleTicket{SID: id, Domain: "cv-ssh-test", Exp: time.Now().Unix() + 30, Protocol: "ssh", Address: address})
}

func TestSSHRejectsArbitraryTargetAndCrossProtocolTicket(t *testing.T) {
	deps := testDependencies()
	deps.Virtualizer = &fakeSSHTarget{}
	request := httptest.NewRequest("GET", "http://testserver/ssh", nil)
	request.Header.Set("Origin", "http://testserver")
	request.Header.Set("X-Console-Ticket", signedSSHTicket(deps.Token, "b6bd1000-1234-4234-8234-000000000003", "192.0.2.51"))
	response := httptest.NewRecorder()
	sshProxyHandler(deps)(response, request)
	if response.Code != 403 {
		t.Fatalf("arbitrary address accepted: %d", response.Code)
	}
	request = httptest.NewRequest("GET", "http://testserver/vnc", nil)
	request.Header.Set("Origin", "http://testserver")
	request.Header.Set("X-Console-Ticket", signedSSHTicket(deps.Token, "b6bd1000-1234-4234-8234-000000000004", "192.0.2.50"))
	response = httptest.NewRecorder()
	vncProxyHandler(deps)(response, request)
	if response.Code != 401 {
		t.Fatalf("SSH ticket accepted by VNC: %d", response.Code)
	}
}
