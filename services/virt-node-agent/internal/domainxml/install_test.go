package domainxml

import (
	"encoding/xml"
	"testing"
)

func TestISOHasReadonlyCDROMAndDisk(t *testing.T) {
	spec := validSpec()
	spec.ISOPath = "/images/os.iso"
	content, err := Build(spec)
	if err != nil {
		t.Fatal(err)
	}
	var actual domain
	if err := xml.Unmarshal([]byte(content), &actual); err != nil {
		t.Fatal(err)
	}
	if len(actual.Devices.Disks) != 2 || actual.Devices.Disks[1].Device != "cdrom" || actual.Devices.Disks[1].Readonly == nil || actual.OS.Boot[0].Dev != "cdrom" {
		t.Fatal("bad installation devices")
	}
}
