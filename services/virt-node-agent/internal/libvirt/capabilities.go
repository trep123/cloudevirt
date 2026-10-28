package libvirt

import (
	"context"
	"encoding/xml"
	"os/exec"
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
	return map[string]any{"cpu_modes": modes, "firmware": firmware, "secure_boot": secure && parsed.OS.Loader.Supported == "yes", "tpm_emulator": parsed.Devices.TPM.Supported == "yes" && swtpmErr == nil}, nil
}
