package httpapi

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"net"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

type deadlineRecorder struct {
	net.Conn
	deadline time.Time
}

func (connection *deadlineRecorder) SetDeadline(value time.Time) error {
	connection.deadline = value
	return connection.Conn.SetDeadline(value)
}

func signedConsoleTicket(secret string, ticket consoleTicket) string {
	raw, _ := json.Marshal(ticket)
	payload := base64.RawURLEncoding.EncodeToString(raw)
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte("console-v1." + payload))
	return payload + "." + hex.EncodeToString(mac.Sum(nil))
}

func TestConsoleTicketScopeExpiryAndReplay(t *testing.T) {
	secret := "test-secret"
	ticket := consoleTicket{SID: "34ee37a0-f2fb-4bc2-aa49-c6f8d034126c", Domain: "cv-test", Exp: time.Now().Unix() + 30}
	token := signedConsoleTicket(secret, ticket)
	parsed, ok := parseConsoleTicket(secret, token)
	if !ok || parsed.SID != ticket.SID {
		t.Fatal("valid ticket rejected")
	}
	if _, ok := parseConsoleTicket("wrong", token); ok {
		t.Fatal("wrong secret accepted")
	}
	ticket.Exp = time.Now().Unix() - 1
	if _, ok := parseConsoleTicket(secret, signedConsoleTicket(secret, ticket)); ok {
		t.Fatal("expired ticket accepted")
	}
	ticket.Exp = time.Now().Unix() + 30
	if !consumeConsoleTicket(ticket) {
		t.Fatal("initial ticket rejected")
	}
	if consumeConsoleTicket(ticket) {
		t.Fatal("replay accepted")
	}
	consoleConnections.Lock()
	delete(consoleConnections.used, ticket.SID)
	consoleConnections.Unlock()
}
func TestConsoleLeaseAndRevocation(t *testing.T) {
	rawBrowser, otherBrowser := net.Pipe()
	browser := &deadlineRecorder{Conn: rawBrowser}
	target, otherTarget := net.Pipe()
	defer browser.Close()
	defer otherBrowser.Close()
	defer target.Close()
	defer otherTarget.Close()
	id := "4e698242-dcf3-40d4-9d48-becdbd1d3ac2"
	trackConsole(id, browser, target)
	if remaining := time.Until(browser.deadline); remaining < 89*time.Second || remaining > 91*time.Second {
		t.Fatal("hard lease deadline missing")
	}
	browser.deadline = time.Time{}
	defer untrackConsole(id)
	deps := testDependencies()
	for _, path := range []string{"/api/v1/console-sessions/" + id + "/lease", "/api/v1/console-sessions/" + id} {
		method := http.MethodPost
		if path[len(path)-5:] != "lease" {
			method = http.MethodDelete
		}
		req := httptest.NewRequest(method, path, nil)
		req.Header.Set("Authorization", "Bearer "+deps.Token)
		recorder := httptest.NewRecorder()
		NewRouter(deps).ServeHTTP(recorder, req)
		if recorder.Code != 200 {
			t.Fatalf("lease/revoke failed: %d", recorder.Code)
		}
		if method == http.MethodPost && time.Until(browser.deadline) < 89*time.Second {
			t.Fatal("renewal did not extend the transport lease")
		}
	}
	otherBrowser.SetReadDeadline(time.Now().Add(time.Second))
	buffer := make([]byte, 1)
	if _, err := otherBrowser.Read(buffer); err == nil {
		t.Fatal("revocation did not close transport")
	}
}
func TestLegacyConsoleURLCannotAuthorize(t *testing.T) {
	deps := testDependencies()
	recorder := httptest.NewRecorder()
	NewRouter(deps).ServeHTTP(recorder, httptest.NewRequest("GET", "/vnc?domain=cv-test&exp=9999999999&sig=old", nil))
	if recorder.Code != 401 {
		t.Fatal("legacy query ticket accepted")
	}
}
