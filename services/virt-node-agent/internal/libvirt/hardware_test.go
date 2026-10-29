package libvirt

import (
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/domainxml"
	"strings"
	"testing"
)

func TestXMLHardwareEditsPreserveNestedMetadata(t *testing.T) {
	content := `<domain><metadata><vcpu>999</vcpu><devices><disk/></devices></metadata><vcpu placement="static">2</vcpu><memory unit="KiB">524288</memory><devices><disk device="disk"><source file="/outside/file"/><target dev="vda" bus="virtio"/></disk></devices></domain>`
	updated, err := replaceXMLChild(content, "domain", "vcpu", "<vcpu>4</vcpu>")
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(updated, "<metadata><vcpu>999</vcpu>") {
		t.Fatal("metadata changed")
	}
	parts, err := xmlParts(updated, "domain/devices", "disk")
	if err != nil || len(parts) != 1 || !strings.Contains(parts[0].raw, "/outside/file") {
		t.Fatal("matched wrong disk")
	}
}
func TestHardwareBuildersValidateAndEscape(t *testing.T) {
	good := HardwareChange{MAC: "02:00:00:00:00:01", Model: "e1000e", Network: domainxml.NetworkSpec{NetworkType: "LIBVIRT_NETWORK", Network: "default"}}
	if raw, err := buildNIC(good); err != nil || !strings.Contains(raw, "e1000e") {
		t.Fatalf("%s %v", raw, err)
	}
	for _, mac := range []string{"ff:ff:ff:ff:ff:ff", "01:00:00:00:00:00", "bad"} {
		c := good
		c.MAC = mac
		if _, err := buildNIC(c); err == nil {
			t.Fatal("invalid MAC accepted")
		}
	}
	if raw, err := buildDisk(HardwareChange{Bus: "virtio", Target: "vdb"}, "/tmp/a&b.qcow2"); err != nil || !strings.Contains(raw, "a&amp;b.qcow2") {
		t.Fatal("path not XML escaped")
	}
	if _, err := buildDisk(HardwareChange{Bus: "virtio", Target: "sda"}, "/tmp/disk"); err == nil {
		t.Fatal("invalid target accepted")
	}
}
