package libvirt

import (
	"context"
	"testing"
)

func TestHardwareInventoryReportsActualSystemConfiguration(t *testing.T) {
	xml := `<domain><uuid>test</uuid><vcpu>4</vcpu><memory unit="MiB">4096</memory><os firmware="efi"><type arch="x86_64" machine="pc-q35-10.0">hvm</type><loader>/usr/share/OVMF/OVMF_CODE.fd</loader><boot dev="cdrom"/><boot dev="hd"/></os><cpu mode="host-passthrough"><topology sockets="1" cores="2" threads="2"/></cpu><devices/></domain>`
	info, err := parseHardware(context.Background(), xml, t.TempDir())
	if err != nil { t.Fatal(err) }
	if info.System.OS.Firmware != "efi" || info.System.OS.Type.Machine != "pc-q35-10.0" || info.System.CPU.Mode != "host-passthrough" { t.Fatalf("lost system configuration: %+v", info.System) }
	if info.System.CPU.Topology == nil || info.System.CPU.Topology.Threads != 2 || len(info.System.OS.Boot) != 2 { t.Fatal("lost topology or boot sequence") }
}
