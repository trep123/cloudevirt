package libvirt

import (
	"encoding/xml"
	"strings"
	"testing"
)

func TestNormalizeAutomaticUEFISelectsStandardFirmware(t *testing.T) {
	for _, loader := range []string{"", `<loader type="rom">/usr/share/ovmf/OVMF.amdsev.fd</loader>`} {
		source := `<domain><name>test</name><os firmware="efi"><type arch="x86_64">hvm</type>` + loader + `<boot dev="cdrom"/></os><devices><disk/></devices></domain>`
		fixed, err := normalizeFirmwareWith(source, func(string) bool { return true })
		if err != nil {
			t.Fatal(err)
		}
		if strings.Contains(fixed, "amdsev") || strings.Contains(fixed, `firmware="efi"`) || !strings.Contains(fixed, "OVMF_CODE_4M.fd") || !strings.Contains(fixed, "OVMF_VARS_4M.fd") || !strings.Contains(fixed, `dev="cdrom"`) {
			t.Fatal(fixed)
		}
		var parsed any
		if xml.Unmarshal([]byte(fixed), &parsed) != nil {
			t.Fatal("invalid XML")
		}
		again, err := normalizeFirmwareWith(fixed, func(string) bool { return true })
		if err != nil || again != fixed {
			t.Fatal("not idempotent")
		}
	}
}
func TestNormalizeFirmwareFailsClosedAndPreservesCustomState(t *testing.T) {
	source := `<domain><os firmware="efi"><type>hvm</type></os></domain>`
	if _, err := normalizeFirmwareWith(source, func(string) bool { return false }); err == nil {
		t.Fatal("accepted missing firmware")
	}
	state := `<domain><os firmware="efi"><loader>/usr/share/ovmf/OVMF.amdsev.fd</loader><nvram>/saved/keys.fd</nvram></os></domain>`
	if _, err := normalizeFirmwareWith(state, func(string) bool { return true }); err == nil {
		t.Fatal("replaced saved keys")
	}
	custom := `<domain><os><loader>/custom/firmware.fd</loader></os></domain>`
	fixed, err := normalizeFirmwareWith(custom, func(string) bool { return false })
	if err != nil || fixed != custom {
		t.Fatal("modified custom firmware")
	}
}
