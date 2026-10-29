package domainxml

import (
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
)

type Hardware struct {
	Clipboard       bool   `json:"clipboard"`
	VideoModel      string `json:"video_model"`
	VideoWidth      int    `json:"video_width"`
	VideoHeight     int    `json:"video_height"`
	CPUMode         string `json:"cpu_mode"`
	Sockets         int    `json:"sockets"`
	Cores           int    `json:"cores"`
	Threads         int    `json:"threads"`
	Firmware        string `json:"firmware"`
	SecureBoot      bool   `json:"secure_boot"`
	TPM             bool   `json:"tpm"`
	CPUQuotaPercent int    `json:"cpu_quota_percent"`
	DiskReadIOPS    int    `json:"disk_read_iops"`
	DiskWriteIOPS   int    `json:"disk_write_iops"`
	NetworkMbps     int    `json:"network_mbps"`
}
type cpuSpec struct {
	Mode     string       `xml:"mode,attr,omitempty"`
	Topology *cpuTopology `xml:"topology,omitempty"`
}
type cpuTopology struct {
	Sockets int `xml:"sockets,attr"`
	Cores   int `xml:"cores,attr"`
	Threads int `xml:"threads,attr"`
}
type cpuTune struct {
	Period int `xml:"period"`
	Quota  int `xml:"quota"`
}
type firmwareSpec struct {
	Features []firmwareFeature `xml:"feature"`
}
type firmwareFeature struct {
	Name    string `xml:"name,attr"`
	Enabled string `xml:"enabled,attr"`
}
type featuresSpec struct {
	ACPI *struct{} `xml:"acpi,omitempty"`
	APIC *struct{} `xml:"apic,omitempty"`
	SMM  *smmSpec  `xml:"smm,omitempty"`
}
type smmSpec struct {
	State string `xml:"state,attr"`
}
type tpmSpec struct {
	Model   string     `xml:"model,attr"`
	Backend tpmBackend `xml:"backend"`
}
type tpmBackend struct {
	Type    string `xml:"type,attr"`
	Version string `xml:"version,attr"`
}
type ioTune struct {
	Read  int `xml:"read_iops_sec,omitempty"`
	Write int `xml:"write_iops_sec,omitempty"`
}
type bandwidthSpec struct {
	Inbound  bandwidthRate `xml:"inbound"`
	Outbound bandwidthRate `xml:"outbound"`
}
type bandwidthRate struct {
	Average int `xml:"average,attr"`
}

func ApplyHardware(payload *domain, spec Spec) error {
	h := spec.Hardware
	video, err := BuildVideo(h.VideoModel, h.VideoWidth, h.VideoHeight)
	if err != nil {
		return err
	}
	payload.Devices.Video = video
	if h.Clipboard {
		payload.Devices.Channels = []ClipboardChannel{NewClipboardChannel()}
	}
	if h.CPUMode != "" && h.CPUMode != "host-model" && h.CPUMode != "host-passthrough" {
		return apierr.New(apierr.CodeInvalidArgument, "CPU 模式不受支持", nil)
	}
	topology := h.Sockets != 0 || h.Cores != 0 || h.Threads != 0
	if topology && (h.Sockets < 1 || h.Sockets > 128 || h.Cores < 1 || h.Cores > 128 || h.Threads < 1 || h.Threads > 128 || h.Sockets*h.Cores*h.Threads != spec.VCPU) {
		return apierr.New(apierr.CodeInvalidArgument, "CPU 拓扑与 vCPU 不一致", nil)
	}
	if h.CPUMode != "" || topology {
		mode := h.CPUMode
		if mode == "" {
			mode = "host-model"
		}
		payload.CPU = &cpuSpec{Mode: mode}
		if topology {
			payload.CPU.Topology = &cpuTopology{Sockets: h.Sockets, Cores: h.Cores, Threads: h.Threads}
		}
	}
	if h.Firmware != "" && h.Firmware != "bios" && h.Firmware != "uefi" {
		return apierr.New(apierr.CodeInvalidArgument, "固件类型无效", nil)
	}
	if h.SecureBoot && h.Firmware != "uefi" {
		return apierr.New(apierr.CodeInvalidArgument, "Secure Boot 需要 UEFI", nil)
	}
	if h.Firmware == "uefi" {
		payload.Features = &featuresSpec{ACPI: &struct{}{}, APIC: &struct{}{}}
		payload.OS.Firmware = "efi"
		payload.OS.FirmwareConfig = &firmwareSpec{Features: []firmwareFeature{{Name: "secure-boot", Enabled: "no"}}}
		if h.SecureBoot {
			payload.OS.FirmwareConfig.Features = []firmwareFeature{{Name: "secure-boot", Enabled: "yes"}, {Name: "enrolled-keys", Enabled: "yes"}}
			payload.Features.SMM = &smmSpec{State: "on"}
		}
	}
	if h.TPM {
		payload.Devices.TPM = &tpmSpec{Model: "tpm-crb", Backend: tpmBackend{Type: "emulator", Version: "2.0"}}
	}
	if h.CPUQuotaPercent < 0 || h.CPUQuotaPercent > spec.VCPU*100 || h.DiskReadIOPS < 0 || h.DiskReadIOPS > 1000000 || h.DiskWriteIOPS < 0 || h.DiskWriteIOPS > 1000000 || h.NetworkMbps < 0 || h.NetworkMbps > 100000 {
		return apierr.New(apierr.CodeInvalidArgument, "性能限制参数超出范围", nil)
	}
	if h.CPUQuotaPercent > 0 {
		payload.CPUTune = &cpuTune{Period: 100000, Quota: h.CPUQuotaPercent * 1000}
	}
	for i := range payload.Devices.Disks {
		if payload.Devices.Disks[i].Device == "disk" && (h.DiskReadIOPS > 0 || h.DiskWriteIOPS > 0) {
			payload.Devices.Disks[i].IOTune = &ioTune{Read: h.DiskReadIOPS, Write: h.DiskWriteIOPS}
		}
	}
	if h.NetworkMbps > 0 {
		if spec.NetworkType == "OVS" {
			return apierr.New(apierr.CodeInvalidArgument, "OVS 限速需独立 QoS 实现", nil)
		}
		for _, nic := range payload.Devices.Interfaces {
			if nic != nil {
				nic.Bandwidth = &bandwidthSpec{Inbound: bandwidthRate{Average: h.NetworkMbps * 1000000 / 8 / 1024}, Outbound: bandwidthRate{Average: h.NetworkMbps * 1000000 / 8 / 1024}}
			}
		}
	}
	return nil
}
