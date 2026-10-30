package httpapi

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/domainxml"
	"net"
	"net/http"
	"regexp"
	"strings"
	"sync"
	"time"
)

var consoleID = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`)

type consoleTicket struct {
	Protocol string `json:"protocol,omitempty"`
	Address  string `json:"address,omitempty"`
	SID      string `json:"sid"`
	Domain   string `json:"domain"`
	Exp      int64  `json:"exp"`
}
type consoleConnection struct {
	browser net.Conn
	target  net.Conn
}

var consoleConnections = struct {
	sync.Mutex
	active map[string]consoleConnection
	used   map[string]int64
}{active: map[string]consoleConnection{}, used: map[string]int64{}}

func parseConsoleTicket(secret, token string) (consoleTicket, bool) {
	var ticket consoleTicket
	parts := strings.Split(token, ".")
	if secret == "" || len(parts) != 2 || len(token) > 2048 {
		return ticket, false
	}
	signature, err := hex.DecodeString(parts[1])
	if err != nil {
		return ticket, false
	}
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte("console-v1." + parts[0]))
	if !hmac.Equal(signature, mac.Sum(nil)) {
		return ticket, false
	}
	raw, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return ticket, false
	}
	if json.Unmarshal(raw, &ticket) != nil {
		return ticket, false
	}
	now := time.Now().Unix()
	return ticket, consoleID.MatchString(ticket.SID) && domainxml.ValidName(ticket.Domain) && ticket.Exp >= now && ticket.Exp <= now+35
}

func consumeConsoleTicket(ticket consoleTicket) bool {
	consoleConnections.Lock()
	defer consoleConnections.Unlock()
	now := time.Now().Unix()
	for id, exp := range consoleConnections.used {
		if exp < now {
			delete(consoleConnections.used, id)
		}
	}
	if _, ok := consoleConnections.used[ticket.SID]; ok {
		return false
	}
	if _, active := consoleConnections.active[ticket.SID]; active {
		return false
	}
	reserved := len(consoleConnections.used)
	for id := range consoleConnections.active {
		if _, used := consoleConnections.used[id]; !used {
			reserved++
		}
	}
	if reserved >= 64 {
		return false
	}
	consoleConnections.used[ticket.SID] = ticket.Exp
	return true
}

func trackConsole(id string, browser, target net.Conn) bool {
	consoleConnections.Lock()
	defer consoleConnections.Unlock()
	if _, exists := consoleConnections.active[id]; exists || len(consoleConnections.active) >= 64 {
		return false
	}
	consoleConnections.active[id] = consoleConnection{browser, target}
	deadline := time.Now().Add(90 * time.Second)
	browser.SetDeadline(deadline)
	target.SetDeadline(deadline)
	return true
}

func untrackConsole(id string) {
	consoleConnections.Lock()
	defer consoleConnections.Unlock()
	delete(consoleConnections.active, id)
}

func consoleLeaseHandler(deps Dependencies) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := r.PathValue("id")
		consoleConnections.Lock()
		connection, ok := consoleConnections.active[id]
		if ok {
			if r.Method == http.MethodDelete {
				connection.browser.Close()
				connection.target.Close()
				delete(consoleConnections.active, id)
			} else {
				deadline := time.Now().Add(90 * time.Second)
				connection.browser.SetDeadline(deadline)
				connection.target.SetDeadline(deadline)
			}
		}
		consoleConnections.Unlock()
		if !ok && r.Method != http.MethodDelete {
			writeAPIError(w, deps.Logger, apierr.New(apierr.CodeNotFound, "控制台连接已结束", nil), RequestIDFromContext(r.Context()))
			return
		}
		writeJSON(w, 200, map[string]bool{"active": ok && r.Method != http.MethodDelete})
	}
}
