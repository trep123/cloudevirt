package libvirt

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestDisplayReplacementPreservesUnrelatedXML(t *testing.T) {
	original := `<domain><name>cv-test</name><metadata><custom value="keep"/></metadata><devices><disk type="file"><source file="/disk.qcow2"/></disk><video><model type="cirrus" vram="16384"/><alias name="video0"/><address type="pci" bus="0x00" slot="0x02"/></video></devices></domain>`
	want := DisplayConfig{Model: "virtio", Width: 1920, Height: 1080}
	result, err := replaceDisplay(original, want)
	if err != nil {
		t.Fatal(err)
	}
	for _, keep := range []string{`<metadata><custom value="keep"/></metadata>`, `<disk type="file"><source file="/disk.qcow2"/></disk>`, `<alias name="video0"/>`, `<address type="pci" bus="0x00" slot="0x02"/>`} {
		if !strings.Contains(result, keep) {
			t.Fatalf("lost unrelated configuration: %s", keep)
		}
	}
	actual, err := parseDisplay(result)
	if err != nil || actual != want {
		t.Fatalf("%+v %v", actual, err)
	}
	// Reapplying a configuration containing a nested resolution must be idempotent.
	again, err := replaceDisplay(result, want)
	if err != nil || again != result {
		t.Fatalf("not idempotent: %v %s", err, again)
	}
	if _, err := replaceDisplay(strings.Replace(original, "</devices>", "<video><model type='vga'/></video></devices>", 1), want); err == nil {
		t.Fatal("accepted multiple GPUs")
	}
}
func TestDisplayCannotChangeRunningGuest(t *testing.T) {
	binary := filepath.Join(t.TempDir(), "virsh")
	if err := os.WriteFile(binary, []byte("#!/bin/sh\ncase \"$*\" in *domstate*) echo running;; *) exit 99;; esac\n"), 0700); err != nil {
		t.Fatal(err)
	}
	client := NewClient(0)
	client.Binary = binary
	if _, err := client.ConfigureDisplay(t.Context(), "cv-test", DisplayConfig{Model: "virtio", Width: 1920, Height: 1080}); err == nil {
		t.Fatal("accepted live hardware change")
	}
}
