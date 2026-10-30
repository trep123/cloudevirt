package httpapi

import (
	"context"
	"encoding/json"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

type directOperator struct {
	fakeOperator
	content string
	blocked bool
}

func (f *directOperator) CheckUnusedDisk(context.Context, string, string) error {
	if f.blocked {
		return apierr.New(apierr.CodeConflict, "in use", nil)
	}
	return nil
}
func (f *directOperator) DefineDomain(_ context.Context, content string) error {
	f.content = content
	f.defineCall++
	return nil
}
func (f *directOperator) DumpXML(context.Context, string) (string, error) { return f.content, nil }
func TestDirectDiskCreationUsesExistingFileAndRefusesOccupied(t *testing.T) {
	if _, err := exec.LookPath("qemu-img"); err != nil {
		t.Skip("qemu-img required")
	}
	for _, blocked := range []bool{false, true} {
		t.Run(map[bool]string{false: "direct", true: "occupied"}[blocked], func(t *testing.T) {
			deps := testDependencies()
			deps.DiskDir = t.TempDir()
			path := filepath.Join(deps.DiskDir, "installed.qcow2")
			if err := exec.Command("qemu-img", "create", "-f", "qcow2", path, "1G").Run(); err != nil {
				t.Fatal(err)
			}
			before, _ := os.ReadFile(path)
			op := &directOperator{blocked: blocked}
			deps.Virtualizer = op
			var body map[string]any
			_ = json.Unmarshal([]byte(createPayload(t)), &body)
			body["disk_relative_path"] = "installed.qcow2"
			body["use_existing_disk"] = true
			body["start_after_create"] = false
			encoded, _ := json.Marshal(body)
			r := httptest.NewRequest(http.MethodPost, "/api/v1/domains", strings.NewReader(string(encoded)))
			r.Header.Set("Authorization", "Bearer "+deps.Token)
			w := httptest.NewRecorder()
			NewRouter(deps).ServeHTTP(w, r)
			if blocked {
				if w.Code != 409 || op.defineCall != 0 {
					t.Fatalf("occupied: %d %s", w.Code, w.Body.String())
				}
			} else {
				if w.Code != 201 || !strings.Contains(op.content, path) {
					t.Fatalf("direct: %d %s", w.Code, w.Body.String())
				}
			}
			after, _ := os.ReadFile(path)
			if string(before) != string(after) {
				t.Fatal("existing disk changed during definition")
			}
		})
	}
}
