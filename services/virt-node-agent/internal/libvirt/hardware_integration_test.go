package libvirt

import (
	"crypto/rand"
	"fmt"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/domainxml"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

func TestHardwareLifecycleIntegration(t *testing.T) {
	if os.Getenv("CLOUDVIRT_TEST_HARDWARE") != "1" {
		t.Skip("explicit disposable VM hardware opt-in required")
	}
	root := os.Getenv("CLOUDVIRT_TEST_DISK_DIR")
	if !filepath.IsAbs(root) {
		t.Fatal("absolute disk directory required")
	}
	nonce := make([]byte, 16)
	if _, err := rand.Read(nonce); err != nil {
		t.Fatal(err)
	}
	uuid := fmt.Sprintf("%x-%x-%x-%x-%x", nonce[:4], nonce[4:6], nonce[6:8], nonce[8:10], nonce[10:])
	name := fmt.Sprintf("cv-hwtest-%x", nonce[:6])
	system := filepath.Join(root, name+"-sys.qcow2")
	data := name + "-data.qcow2"
	sata := name + "-sata.qcow2"
	client := NewClient(DefaultTimeout)
	ctx := t.Context()
	defer func() {
		_ = client.DestroyDomain(ctx, name)
		_ = client.UndefineDomainState(ctx, name, true)
		for _, path := range []string{system, filepath.Join(root, data), filepath.Join(root, sata)} {
			_ = os.Remove(path)
		}
	}()
	if err := exec.Command("qemu-img", "create", "-f", "qcow2", system, "1G").Run(); err != nil {
		t.Fatal(err)
	}
	content, err := domainxml.Build(domainxml.Spec{Name: name, UUID: uuid, VCPU: 1, MemoryMiB: 256, DiskPath: system})
	if err != nil {
		t.Fatal(err)
	}
	if err = client.DefineDomain(ctx, content); err != nil {
		t.Fatal(err)
	}
	apply := func(change HardwareChange) HardwareInventory {
		t.Helper()
		change.UUID = uuid
		result, err := client.ChangeHardware(ctx, name, root, change)
		if err != nil {
			t.Fatal(err)
		}
		return result
	}
	result := apply(HardwareChange{Operation: "compute", VCPU: 2, MemoryMiB: 512})
	if result.VCPU != 2 || result.MemoryMiB != 512 {
		t.Fatal("compute not applied")
	}
	add := HardwareChange{Operation: "disk-add", RelativePath: data, SizeGiB: 2, Bus: "virtio", Target: "vdb"}
	apply(add)
	result = apply(add)
	if len(result.Disks) != 2 {
		t.Fatal("duplicate disk created")
	}
	add.Operation = "disk-resize"
	add.SizeGiB = 3
	result = apply(add)
	if result.Disks[1].SizeBytes != 3*1024*1024*1024 {
		t.Fatal("resize failed")
	}
	apply(add)
	add.Operation = "disk-detach"
	result = apply(add)
	if len(result.Disks) != 1 {
		t.Fatal("detach failed")
	}
	if _, err = os.Stat(filepath.Join(root, data)); err != nil {
		t.Fatal("detached file lost")
	}
	add.Operation = "disk-attach"
	result = apply(add)
	if len(result.Disks) != 2 {
		t.Fatal("reattach failed")
	}
	apply(HardwareChange{Operation: "disk-add", RelativePath: sata, SizeGiB: 1, Bus: "sata", Target: "sdc"})
	nic := HardwareChange{Operation: "nic-add", MAC: "02:00:00:ab:cd:ef", Model: "e1000e", Network: domainxml.NetworkSpec{NetworkType: "LIBVIRT_NETWORK", Network: "default"}}
	result = apply(nic)
	if len(result.NICs) != 1 || result.NICs[0].ModelName != "e1000e" {
		t.Fatal("NIC not added")
	}
	result = apply(nic)
	if len(result.NICs) != 1 {
		t.Fatal("NIC duplicated")
	}
	nic.Operation = "nic-remove"
	result = apply(nic)
	if len(result.NICs) != 0 {
		t.Fatal("NIC not removed")
	}
	if err = client.StartDomain(ctx, name); err != nil {
		t.Fatal(err)
	}
	if _, err = client.ChangeHardware(ctx, name, root, HardwareChange{Operation: "compute", UUID: uuid, VCPU: 1, MemoryMiB: 256}); err == nil {
		t.Fatal("running guest changed")
	}
	t.Log("compute, VirtIO/SATA add, idempotent retry, expand, detach retaining file, reattach, NIC add/remove, final boot and live refusal verified")
}
