package libvirt

import (
	"crypto/rand"
	"fmt"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/domainxml"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestDisplayBootIntegration(t *testing.T) {
	if os.Getenv("CLOUDVIRT_TEST_DISPLAY_BOOT") != "1" {
		t.Skip("isolated video boot test opt-in required")
	}
	root := os.Getenv("CLOUDVIRT_TEST_DISK_DIR")
	if !filepath.IsAbs(root) {
		t.Fatal("absolute test disk directory required")
	}
	for _, model := range []string{"vga", "virtio"} {
		t.Run(model, func(t *testing.T) {
			nonce := make([]byte, 16)
			if _, err := rand.Read(nonce); err != nil {
				t.Fatal(err)
			}
			uuid := fmt.Sprintf("%x-%x-%x-%x-%x", nonce[:4], nonce[4:6], nonce[6:8], nonce[8:10], nonce[10:])
			name := fmt.Sprintf("cv-displaytest-%x", nonce[:6])
			disk := filepath.Join(root, name+".qcow2")
			ctx := t.Context()
			client := NewClient(DefaultTimeout)
			defer func() {
				_ = client.DestroyDomain(ctx, name)
				_ = client.UndefineDomainState(ctx, name, true)
				_ = os.Remove(disk)
			}()
			if err := exec.Command("qemu-img", "create", "-f", "qcow2", disk, "1G").Run(); err != nil {
				t.Fatal(err)
			}
			spec := domainxml.Spec{Name: name, UUID: uuid, VCPU: 1, MemoryMiB: 256, DiskPath: disk, Hardware: domainxml.Hardware{Firmware: "uefi"}}
			content, err := domainxml.Build(spec)
			if err != nil {
				t.Fatal(err)
			}
			if err = client.DefineDomain(ctx, content); err != nil {
				t.Fatal(err)
			}
			want := DisplayConfig{Model: model, Width: 1920, Height: 1080, Clipboard: true}
			if _, err = client.ConfigureDisplay(ctx, name, want); err != nil {
				t.Fatal(err)
			}
			if err = client.StartDomain(ctx, name); err != nil {
				t.Fatal(err)
			}
			if state, err := client.DomainState(ctx, name); err != nil || state != StateRunning {
				t.Fatalf("boot failed: %s %v", state, err)
			}
			// Confirm libvirt translated the mode into QEMU hardware properties.
			content, err = client.run(ctx, "dumpxml", name, "--inactive")
			if err != nil {
				t.Fatal(err)
			}
			args, err := client.run(ctx, "domxml-to-native", "qemu-argv", "--domain", name)
			if err != nil {
				t.Fatal(err)
			}
			if !strings.Contains(args, `"xres":1920`) || !strings.Contains(args, `"yres":1080`) {
				t.Fatalf("missing QEMU resolution properties: %s", args)
			}
			got, err := parseDisplay(content)
			if err != nil || got != want {
				t.Fatalf("configuration lost: %+v %v", got, err)
			}
			if _, err = client.ConfigureDisplay(ctx, name, want); err == nil {
				t.Fatal("accepted running VM reconfiguration")
			}
			t.Logf("%s booted with guest-visible 1920x1080 hardware properties; guest desktop mode is not asserted", model)
		})
	}
}
