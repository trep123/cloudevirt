package domainxml

import (
	"encoding/xml"
	"testing"
)

func TestHardwareFirmwareTopologyAndLimits(t *testing.T) {
	spec := validSpec()
	spec.Hardware = Hardware{CPUMode: "host-model", Sockets: 1, Cores: 2, Threads: 1, Firmware: "uefi", SecureBoot: true, TPM: true, CPUQuotaPercent: 150, DiskReadIOPS: 2000, NetworkMbps: 20}
	spec.AdditionalDiskPaths = []string{"/disks/data.qcow2"}
	spec.AdditionalNetworks = []NetworkSpec{{Network: "secondary"}}
	content, err := Build(spec)
	if err != nil {
		t.Fatal(err)
	}
	var actual domain
	if err := xml.Unmarshal([]byte(content), &actual); err != nil {
		t.Fatal(err)
	}
	if actual.CPU.Topology.Cores != 2 || actual.CPUTune.Quota != 150000 || actual.OS.Firmware != "efi" || actual.Devices.TPM == nil || actual.Features.SMM.State != "on" {
		t.Fatal("hardware not applied")
	}
	if len(actual.Devices.Disks) != 2 || actual.Devices.Disks[1].IOTune.Read != 2000 || len(actual.Devices.Interfaces) != 2 || actual.Devices.Interfaces[1].Bandwidth.Inbound.Average != 2441 {
		t.Fatal("device limits not applied")
	}
	spec.Hardware.Cores = 3
	if _, err := Build(spec); err == nil {
		t.Fatal("accepted mismatching topology")
	}
}

func TestTemplateDiskBusAndNICModel(t *testing.T) {
	spec := validSpec()
	spec.Network = "default"
	spec.AdditionalNetworks = []NetworkSpec{{Network: "extra"}}
	spec.AdditionalDiskPaths = []string{"/disks/data.qcow2"}
	spec.Hardware = Hardware{NICModel: "e1000e", DataDiskBus: "sata"}
	content, err := Build(spec)
	if err != nil {
		t.Fatal(err)
	}
	var actual domain
	if err = xml.Unmarshal([]byte(content), &actual); err != nil {
		t.Fatal(err)
	}
	if actual.Devices.Disks[1].Target.Bus != "sata" || actual.Devices.Disks[1].Target.Dev != "sdc" {
		t.Fatal("template data disk bus ignored")
	}
	for _, nic := range actual.Devices.Interfaces {
		if nic != nil && nic.Model.Type != "e1000e" {
			t.Fatal("template NIC model ignored")
		}
	}
}

func TestUEFIAlwaysEnablesACPI(t *testing.T) {
	for _, secure := range []bool{false, true} {
		spec := validSpec()
		spec.Hardware = Hardware{Firmware: "uefi", SecureBoot: secure}
		content, err := Build(spec)
		if err != nil {
			t.Fatal(err)
		}
		var actual domain
		if err := xml.Unmarshal([]byte(content), &actual); err != nil {
			t.Fatal(err)
		}
		if actual.Features == nil || actual.Features.ACPI == nil || actual.Features.APIC == nil {
			t.Fatal("UEFI missing ACPI/APIC")
		}
		if secure && (actual.Features.SMM == nil || actual.Features.SMM.State != "on") {
			t.Fatal("secure boot missing SMM")
		}
	}
}
