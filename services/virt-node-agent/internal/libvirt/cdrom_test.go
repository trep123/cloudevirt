package libvirt

import (
	"strings"
	"testing"
)

func TestOpticalChangesPreserveDisksAndAreReplayable(t *testing.T) {
	base := `<domain><os><type>hvm</type><boot dev="hd"/></os><devices><disk device="disk"><source file="/data/system.qcow2"/><target dev="vda"/></disk></devices></domain>`
	added, err := replaceCDROM(base, "sda", "/iso/test&install.iso", false)
	if err != nil || !strings.Contains(added, "test&amp;install.iso") || !strings.Contains(added, "/data/system.qcow2") { t.Fatalf("unsafe optical update: %v", err) }
	replayed, err := replaceCDROM(added, "sda", "/iso/test&install.iso", false)
	if err != nil || replayed != added { t.Fatal("mount replay changed XML") }
	removed, err := replaceCDROM(added, "sda", "", true)
	if err != nil || removed != base { t.Fatal("eject modified other devices") }
	if _, err := replaceCDROM(strings.Replace(base, `dev="vda"`, `dev="sda"`, 1), "sda", "/iso/a.iso", false); err == nil { t.Fatal("replaced system disk with optical drive") }
	boot, err := opticalBootOrder(added, false)
	if err != nil || !strings.Contains(boot, `<boot dev="cdrom"/><boot dev="hd"/>`) { t.Fatal("installation boot order missing") }
	boot, err = opticalBootOrder(boot, true)
	if err != nil || strings.Contains(boot, `<boot dev="cdrom"/>`) { t.Fatal("eject retained optical boot") }
}
