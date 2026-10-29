package libvirt

import (
	"context"
	"crypto/rand"
	"fmt"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/domainxml"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

func TestFirmwareBootIntegration(t *testing.T) {
	if os.Getenv("CLOUDVIRT_TEST_FIRMWARE_BOOT") != "1" {
		t.Skip("explicit isolated firmware boot opt-in required")
	}
	for _, secure := range []bool{false, true} {
		t.Run(fmt.Sprintf("secure_%v", secure), func(t *testing.T) {
			bytes := make([]byte, 16)
			if _, err := rand.Read(bytes); err != nil {
				t.Fatal(err)
			}
			uuid := fmt.Sprintf("%x-%x-%x-%x-%x", bytes[:4], bytes[4:6], bytes[6:8], bytes[8:10], bytes[10:])
			name := "cv-fwtest-" + fmt.Sprintf("%x", bytes[:6])
			diskRoot := os.Getenv("CLOUDVIRT_TEST_DISK_DIR")
			if !filepath.IsAbs(diskRoot) {
				t.Fatal("explicit absolute test disk directory required")
			}
			disk := filepath.Join(diskRoot, name+".qcow2")
			ctx := context.Background()
			client := NewClient(DefaultTimeout)
			defer func() {
				_ = client.DestroyDomain(ctx, name)
				_ = client.UndefineDomainState(ctx, name, true)
				_ = os.Remove(disk)
			}()
			if err := exec.Command("qemu-img", "create", "-f", "qcow2", disk, "1G").Run(); err != nil {
				t.Fatal(err)
			}
			content, err := domainxml.Build(domainxml.Spec{Name: name, UUID: uuid, VCPU: 1, MemoryMiB: 256, DiskPath: disk, Hardware: domainxml.Hardware{Firmware: "uefi", SecureBoot: secure}})
			if err != nil {
				t.Fatal(err)
			}
			if err := client.DefineDomain(ctx, content); err != nil {
				t.Fatal(err)
			}
			if err := client.StartDomain(ctx, name); err != nil {
				t.Fatal(err)
			}
			state, err := client.DomainState(ctx, name)
			if err != nil || state != StateRunning {
				t.Fatalf("not running: %s %v", state, err)
			}
		})
	}
}
