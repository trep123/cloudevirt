package httpapi

import (
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestDesktopPublisherIsIdempotentBoundedAndRevocable(t *testing.T) {
	script := filepath.Join(t.TempDir(), "capture.py")
	if err := os.WriteFile(script, []byte("import sys,time\nsys.stdin.read()\ntime.sleep(60)\n"), 0600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("CLOUDVIRT_DESKTOP_PUBLISHER_SCRIPT", script)
	t.Setenv("CLOUDVIRT_MEDIA_PUBLISH_BASE_URL", "rtsp://127.0.0.1:8554")
	t.Setenv("CLOUDVIRT_DESKTOP_STREAM_LIMIT", "1")
	publisher := NewDesktopPublisher()
	defer publisher.Close()
	id := "371cc72e-ecf9-4f23-a1b8-a949a0bd273d"
	if err := publisher.start(id, "test-domain", "private-vnc", 5901); err != nil {
		t.Fatal(err)
	}
	first := publisher.processes[id]
	if strings.Contains(strings.Join(first.command.Args, " "), "private-vnc") {
		t.Fatal("credential exposed in argv")
	}
	if err := publisher.start(id, "test-domain", "private-vnc", 5901); err != nil {
		t.Fatal(err)
	}
	if publisher.processes[id] != first {
		t.Fatal("duplicate start spawned another capture")
	}
	if publisher.start("471cc72e-ecf9-4f23-a1b8-a949a0bd273d", "second", "secret", 5902) == nil {
		t.Fatal("capacity limit bypassed")
	}
	deps := testDependencies()
	deps.Publisher = publisher
	request := httptest.NewRequest("DELETE", "/api/v1/desktop-streams/"+id, nil)
	request.Header.Set("Authorization", "Bearer "+deps.Token)
	response := httptest.NewRecorder()
	NewRouter(deps).ServeHTTP(response, request)
	if response.Code != 200 {
		t.Fatalf("stop failed: %d", response.Code)
	}
	select {
	case <-first.done:
	case <-time.After(5 * time.Second):
		t.Fatal("capture process leaked")
	}
}
func TestDesktopPublisherExpiresWithoutController(t *testing.T) {
	script := filepath.Join(t.TempDir(), "capture.py")
	if err := os.WriteFile(script, []byte("import sys,time\nsys.stdin.read()\ntime.sleep(60)\n"), 0600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("CLOUDVIRT_DESKTOP_PUBLISHER_SCRIPT", script)
	t.Setenv("CLOUDVIRT_MEDIA_PUBLISH_BASE_URL", "rtsp://127.0.0.1:8554")
	publisher := NewDesktopPublisher()
	defer publisher.Close()
	id := "571cc72e-ecf9-4f23-a1b8-a949a0bd273d"
	if err := publisher.start(id, "test-domain", "secret", 5901); err != nil {
		t.Fatal(err)
	}
	publisher.mu.Lock()
	process := publisher.processes[id]
	process.expires = time.Now().Add(-time.Second)
	publisher.mu.Unlock()
	select {
	case <-process.done:
	case <-time.After(6 * time.Second):
		t.Fatal("expired publisher survived")
	}
}
