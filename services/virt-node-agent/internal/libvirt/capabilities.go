package libvirt

import (
	"context"
	"encoding/xml"
	"os/exec"
	"strings"
)

type capabilityEnum struct {
	Name   string   `xml:"name,attr"`
	Values []string `xml:"value"`
}
type domainCapabilities struct {
	CPU struct {
		Modes []struct {
			Name      string `xml:"name,attr"`
			Supported string `xml:"supported,attr"`
		} `xml:"mode"`
	} `xml:"cpu"`
	OS struct {
		Enums  []capabilityEnum `xml:"enum"`
		Loader struct {
			Supported string           `xml:"supported,attr"`
			Enums     []capabilityEnum `xml:"enum"`
		} `xml:"loader"`
	} `xml:"os"`
	Devices struct {
		Video struct {
			Enums []capabilityEnum `xml:"enum"`
		} `xml:"video"`
		TPM struct {
			Supported string           `xml:"supported,attr"`
			Enums     []capabilityEnum `xml:"enum"`
		} `xml:"tpm"`
	} `xml:"devices"`
}

func (c *Client) CreationCapabilities(ctx context.Context) (map[string]any, error) {
	content, err := c.run(ctx, "domcapabilities", "--arch", "x86_64", "--machine", "q35", "--virttype", "kvm")
	if err != nil {
		return nil, err
	}
	var parsed domainCapabilities
	if err := xml.Unmarshal([]byte(content), &parsed); err != nil {
		return nil, err
	}
	modes := []string{}
	for _, mode := range parsed.CPU.Modes {
		if mode.Supported == "yes" && (mode.Name == "host-model" || mode.Name == "host-passthrough") {
			modes = append(modes, mode.Name)
		}
	}
	firmware := []string{"bios"}
	for _, enum := range parsed.OS.Enums {
		if enum.Name == "firmware" {
			for _, value := range enum.Values {
				if value == "efi" {
					firmware = append(firmware, "uefi")
				}
			}
		}
	}
	secure := false
	for _, enum := range parsed.OS.Loader.Enums {
		if enum.Name == "secure" {
			for _, value := range enum.Values {
				secure = secure || value == "yes"
			}
		}
	}
	_, swtpmErr := exec.LookPath("swtpm")
	charDevices, charErr := exec.CommandContext(ctx, "qemu-system-x86_64", "-chardev", "help").CombinedOutput()
	videoModels := []string{}
	for _, enum := range parsed.Devices.Video.Enums {
		if enum.Name == "modelType" {
			for _, value := range enum.Values {
				if value == "vga" || value == "virtio" {
					videoModels = append(videoModels, value)
				}
			}
		}
	}
	return map[string]any{"clipboard": charErr == nil && strings.Contains(string(charDevices), "qemu-vdagent"), "video_models": videoModels, "cpu_modes": modes, "firmware": firmware, "secure_boot": secure && parsed.OS.Loader.Supported == "yes", "tpm_emulator": parsed.Devices.TPM.Supported == "yes" && swtpmErr == nil}, nil
}
