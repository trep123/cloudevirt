// Package domainxml ���ɲ�У�� libvirt ���� XML��
//
// ���ж�̬�ֶ�ͨ�� encoding/xml ���л�����Ȼת�壬��ֹ�ַ���ƴ�ӣ�
// ���ɺ�������½���У�飬ʧ��ʱ���õ��� libvirt��
package domainxml

import (
	"encoding/xml"
	"fmt"
	"net"
	"regexp"
	"strings"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
)

// Ĭ��ֵ��
const (
	DomainType   = "kvm"
	MachineType  = "q35"
	Architecture = "x86_64"
	DiskBus      = "virtio"
	DiskFormat   = "qcow2"
)

var (
	namePattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`)
	uuidPattern = regexp.MustCompile(`^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$`)
)

// Spec �Ǵ����������ȫ�����롣
type Spec struct {
	MAC                 string
	SeedPath            string
	Hardware            Hardware
	Name                string
	UUID                string
	VCPU                int
	MemoryMiB           int
	DiskPath            string
	Network             string
	NetworkType         string
	NetworkBridge       string
	VLANID              int
	VNCPassword         string
	ISOPath             string
	AdditionalDiskPaths []string
	AdditionalNetworks  []NetworkSpec
}
type NetworkSpec struct {
	MAC           string `json:"mac"`
	Network       string `json:"network"`
	NetworkType   string `json:"network_type"`
	NetworkBridge string `json:"network_bridge"`
	VLANID        int    `json:"vlan_id"`
}

// domain �� XML �ṹ���ֶ�˳�����˳��
type domain struct {
	XMLName  xml.Name      `xml:"domain"`
	Type     string        `xml:"type,attr"`
	Name     string        `xml:"name"`
	UUID     string        `xml:"uuid"`
	Memory   memory        `xml:"memory"`
	VCPU     int           `xml:"vcpu"`
	OS       osSpec        `xml:"os"`
	CPU      *cpuSpec      `xml:"cpu,omitempty"`
	CPUTune  *cpuTune      `xml:"cputune,omitempty"`
	Features *featuresSpec `xml:"features,omitempty"`
	Devices  devices       `xml:"devices"`
}

type memory struct {
	Unit  string `xml:"unit,attr"`
	Value int    `xml:",chardata"`
}

type osSpec struct {
	Firmware       string        `xml:"firmware,attr,omitempty"`
	FirmwareConfig *firmwareSpec `xml:"firmware,omitempty"`
	Type           osType        `xml:"type"`
	Boot           []bootDevice  `xml:"boot,omitempty"`
}
type bootDevice struct {
	Dev string `xml:"dev,attr"`
}

type osType struct {
	Arch    string `xml:"arch,attr"`
	Machine string `xml:"machine,attr"`
	Value   string `xml:",chardata"`
}

type devices struct {
	Video      *Video        `xml:"video,omitempty"`
	TPM        *tpmSpec      `xml:"tpm,omitempty"`
	Disks      []disk        `xml:"disk"`
	Interfaces []*iface      `xml:"interface,omitempty"`
	Console    consoleSpec   `xml:"console"`
	Graphics   *graphicsSpec `xml:"graphics,omitempty"`
}

type disk struct {
	IOTune   *ioTune   `xml:"iotune,omitempty"`
	Type     string    `xml:"type,attr"`
	Device   string    `xml:"device,attr"`
	Driver   diskDrive `xml:"driver"`
	Source   diskSrc   `xml:"source"`
	Target   diskTgt   `xml:"target"`
	Readonly *struct{} `xml:"readonly,omitempty"`
}

type diskDrive struct {
	Name string `xml:"name,attr"`
	Type string `xml:"type,attr"`
}

type diskSrc struct {
	File string `xml:"file,attr"`
}

type diskTgt struct {
	Dev string `xml:"dev,attr"`
	Bus string `xml:"bus,attr"`
}

type iface struct {
	MAC         *macSpec       `xml:"mac,omitempty"`
	Bandwidth   *bandwidthSpec `xml:"bandwidth,omitempty"`
	Type        string         `xml:"type,attr"`
	Source      ifaceSrc       `xml:"source"`
	VirtualPort *virtualPort   `xml:"virtualport,omitempty"`
	VLAN        *vlanSpec      `xml:"vlan,omitempty"`
	Model       ifaceModel     `xml:"model"`
}

type macSpec struct {
	Address string `xml:"address,attr"`
}

type ifaceSrc struct {
	Network string `xml:"network,attr,omitempty"`
	Bridge  string `xml:"bridge,attr,omitempty"`
}

type virtualPort struct {
	Type string `xml:"type,attr"`
}

type vlanSpec struct {
	Tag vlanTag `xml:"tag"`
}

type vlanTag struct {
	ID int `xml:"id,attr"`
}

type ifaceModel struct {
	Type string `xml:"type,attr"`
}

type consoleSpec struct {
	Type string `xml:"type,attr"`
}

type graphicsSpec struct {
	Type     string `xml:"type,attr"`
	Port     string `xml:"port,attr"`
	Autoport string `xml:"autoport,attr"`
	Listen   string `xml:"listen,attr"`
	Passwd   string `xml:"passwd,attr,omitempty"`
}

// ValidName �ж������Ƿ������������
func ValidName(name string) bool {
	return namePattern.MatchString(name)
}

// ValidateSpec У�������ֶθ�ʽ��ȡֵ��Χ��
func ValidateSpec(spec Spec) error {
	if !namePattern.MatchString(spec.Name) {
		return apierr.New(apierr.CodeInvalidArgument, "������ʽ�Ƿ�", nil)
	}
	if !uuidPattern.MatchString(spec.UUID) {
		return apierr.New(apierr.CodeInvalidArgument, "UUID ��ʽ�Ƿ�", nil)
	}
	if spec.VCPU <= 0 || spec.VCPU > 128 {
		return apierr.New(apierr.CodeInvalidArgument, "vCPU ��������������Χ", nil)
	}
	if spec.MemoryMiB < 128 || spec.MemoryMiB > 1048576 {
		return apierr.New(apierr.CodeInvalidArgument, "�ڴ��С����������Χ", nil)
	}
	if strings.TrimSpace(spec.DiskPath) == "" {
		return apierr.New(apierr.CodeInvalidArgument, "����·������Ϊ��", nil)
	}
	if spec.Network != "" && !namePattern.MatchString(spec.Network) {
		return apierr.New(apierr.CodeInvalidArgument, "�������Ƹ�ʽ�Ƿ�", nil)
	}
	if len(spec.VNCPassword) > 8 {
		return apierr.New(apierr.CodeInvalidArgument, "VNC ����ܳ��� 8 ���ַ�", nil)
	}
	if spec.NetworkType != "" && spec.NetworkType != "LIBVIRT_NETWORK" && spec.NetworkType != "BRIDGE" && spec.NetworkType != "OVS" {
		return apierr.New(apierr.CodeInvalidArgument, "�������Ͳ���֧��", nil)
	}
	if spec.NetworkType == "OVS" && strings.TrimSpace(spec.NetworkBridge) == "" {
		return apierr.New(apierr.CodeInvalidArgument, "OVS �������ָ����������", nil)
	}
	if spec.VLANID < 0 || spec.VLANID > 4094 {
		return apierr.New(apierr.CodeInvalidArgument, "VLAN ID ������Χ", nil)
	}
	return nil
}

// Build �������� XML��
func Build(spec Spec) (string, error) {
	if err := ValidateSpec(spec); err != nil {
		return "", err
	}
	payload := domain{
		Type:   DomainType,
		Name:   spec.Name,
		UUID:   spec.UUID,
		Memory: memory{Unit: "MiB", Value: spec.MemoryMiB},
		VCPU:   spec.VCPU,
		OS:     osSpec{Type: osType{Arch: Architecture, Machine: MachineType, Value: "hvm"}},
		Devices: devices{
			Interfaces: []*iface{nil},
			Disks: []disk{{
				Type:   "file",
				Device: "disk",
				Driver: diskDrive{Name: "qemu", Type: DiskFormat},
				Source: diskSrc{File: spec.DiskPath},
				Target: diskTgt{Dev: "vda", Bus: DiskBus},
			}},
			Console: consoleSpec{Type: "pty"},
			Graphics: &graphicsSpec{
				Type:     "vnc",
				Port:     "-1",
				Autoport: "yes",
				Listen:   "127.0.0.1",
				Passwd:   spec.VNCPassword,
			},
		},
	}
	if spec.SeedPath != "" {
		payload.Devices.Disks = append(payload.Devices.Disks, disk{Type: "file", Device: "cdrom", Driver: diskDrive{Name: "qemu", Type: "raw"}, Source: diskSrc{File: spec.SeedPath}, Target: diskTgt{Dev: "sdb", Bus: "sata"}, Readonly: &struct{}{}})
	}
	if spec.ISOPath != "" {
		payload.OS.Boot = []bootDevice{{Dev: "cdrom"}, {Dev: "hd"}}
		payload.Devices.Disks = append(payload.Devices.Disks, disk{Type: "file", Device: "cdrom", Driver: diskDrive{Name: "qemu", Type: "raw"}, Source: diskSrc{File: spec.ISOPath}, Target: diskTgt{Dev: "sda", Bus: "sata"}, Readonly: &struct{}{}})
	}
	if len(spec.AdditionalDiskPaths) > 8 || len(spec.AdditionalNetworks) > 7 {
		return "", apierr.New(apierr.CodeInvalidArgument, "�豸��������", nil)
	}
	for index, path := range spec.AdditionalDiskPaths {
		if strings.TrimSpace(path) == "" {
			return "", apierr.New(apierr.CodeInvalidArgument, "������·��Ϊ��", nil)
		}
		payload.Devices.Disks = append(payload.Devices.Disks, disk{Type: "file", Device: "disk", Driver: diskDrive{Name: "qemu", Type: DiskFormat}, Source: diskSrc{File: path}, Target: diskTgt{Dev: fmt.Sprintf("vd%c", 'b'+index), Bus: DiskBus}})
	}
	switch spec.NetworkType {
	case "OVS":
		bridge := strings.TrimSpace(spec.NetworkBridge)
		payload.Devices.Interfaces[0] = &iface{
			Type:        "bridge",
			Source:      ifaceSrc{Bridge: bridge},
			VirtualPort: &virtualPort{Type: "openvswitch"},
			Model:       ifaceModel{Type: "virtio"},
		}
		if spec.VLANID > 0 {
			payload.Devices.Interfaces[0].VLAN = &vlanSpec{Tag: vlanTag{ID: spec.VLANID}}
		}
	case "BRIDGE":
		bridge := strings.TrimSpace(spec.NetworkBridge)
		if bridge == "" {
			bridge = spec.Network
		}
		payload.Devices.Interfaces[0] = &iface{
			Type:   "bridge",
			Source: ifaceSrc{Bridge: bridge},
			Model:  ifaceModel{Type: "virtio"},
		}
		if spec.VLANID > 0 {
			payload.Devices.Interfaces[0].VLAN = &vlanSpec{Tag: vlanTag{ID: spec.VLANID}}
		}
	default:
		if spec.Network != "" {
			payload.Devices.Interfaces[0] = &iface{
				Type:   "network",
				Source: ifaceSrc{Network: spec.Network},
				Model:  ifaceModel{Type: "virtio"},
			}
		}
	}

	if spec.MAC != "" {
		mac, err := net.ParseMAC(spec.MAC)
		if err != nil || len(mac) != 6 || mac[0]&1 != 0 {
			return "", apierr.New(apierr.CodeInvalidArgument, "MAC ��ַ��Ч", err)
		}
		if payload.Devices.Interfaces[0] != nil {
			payload.Devices.Interfaces[0].MAC = &macSpec{Address: mac.String()}
		}
	}
	for _, network := range spec.AdditionalNetworks {
		child := spec
		child.AdditionalNetworks = nil
		child.AdditionalDiskPaths = nil
		child.Network = network.Network
		child.MAC = network.MAC
		child.NetworkType = network.NetworkType
		child.NetworkBridge = network.NetworkBridge
		child.VLANID = network.VLANID
		content, err := Build(child)
		if err != nil {
			return "", err
		}
		var parsed domain
		if err := xml.Unmarshal([]byte(content), &parsed); err != nil {
			return "", err
		}
		if len(parsed.Devices.Interfaces) != 1 || parsed.Devices.Interfaces[0] == nil {
			return "", apierr.New(apierr.CodeInvalidArgument, "����������Ч", nil)
		}
		payload.Devices.Interfaces = append(payload.Devices.Interfaces, parsed.Devices.Interfaces[0])
	}
	if err := ApplyHardware(&payload, spec); err != nil {
		return "", err
	}
	encoded, err := xml.MarshalIndent(payload, "", "  ")
	if err != nil {
		return "", apierr.New(apierr.CodeOperationFailed, "�� XML ����ʧ��", err)
	}
	content := xml.Header + string(encoded)
	if err := Validate(content); err != nil {
		return "", err
	}
	return content, nil
}

// Validate У�� XML �ṹ�����ҹؼ��ֶ���Լ��һ�¡�
func Validate(content string) error {
	var parsed domain
	if err := xml.Unmarshal([]byte(content), &parsed); err != nil {
		return apierr.New(apierr.CodeOperationFailed, "�� XML ����ʧ��", err)
	}
	if parsed.Name == "" || parsed.UUID == "" {
		return apierr.New(apierr.CodeOperationFailed, "�� XML ȱ�����ƻ� UUID", nil)
	}
	if parsed.Memory.Value <= 0 || parsed.VCPU <= 0 {
		return apierr.New(apierr.CodeOperationFailed, "�� XML ȱ���ڴ�� vCPU", nil)
	}
	if len(parsed.Devices.Disks) == 0 || parsed.Devices.Disks[0].Source.File == "" {
		return apierr.New(apierr.CodeOperationFailed, "�� XML ȱ�ٴ��̶���", nil)
	}
	if parsed.Devices.Disks[0].Target.Bus != DiskBus {
		return apierr.New(apierr.CodeOperationFailed, "�������߲�����Լ��", nil)
	}
	return nil
}

// memoryToMiB �� unit ��һ���ڴ�ֵ�� MiB��virsh dumpxml Ĭ����� KiB����
func memoryToMiB(value memory) int {
	switch value.Unit {
	case "KiB", "kB", "":
		return value.Value / 1024
	case "GiB", "GB":
		return value.Value * 1024
	default:
		return value.Value
	}
}

// Describe ���ؼ��ժҪ��������־����ԡ�
func Describe(spec Spec) string {
	return fmt.Sprintf("%s(%s) vcpu=%d mem=%dMiB", spec.Name, spec.UUID, spec.VCPU, spec.MemoryMiB)
}

// Parse ������ XML ����ȡ�ؼ��ֶΣ����ڴ�����˶ԡ�
//
// Args:
//
//	content: virsh dumpxml ����� XML��
//
// Returns:
//
//	��ȡ���Ĺ��ȱ�ٹؼ��ֶ�ʱ���ش���
func Parse(content string) (Spec, error) {
	var parsed domain
	if err := xml.Unmarshal([]byte(content), &parsed); err != nil {
		return Spec{}, apierr.New(apierr.CodeOperationFailed, "�� XML ����ʧ��", err)
	}
	if parsed.Name == "" || parsed.UUID == "" {
		return Spec{}, apierr.New(apierr.CodeOperationFailed, "�� XML ȱ�����ƻ� UUID", nil)
	}
	spec := Spec{
		Name:      parsed.Name,
		UUID:      parsed.UUID,
		VCPU:      parsed.VCPU,
		MemoryMiB: memoryToMiB(parsed.Memory),
	}
	if len(parsed.Devices.Disks) > 0 {
		spec.DiskPath = parsed.Devices.Disks[0].Source.File
	}
	if len(parsed.Devices.Interfaces) > 0 && parsed.Devices.Interfaces[0] != nil {
		spec.Network = parsed.Devices.Interfaces[0].Source.Network
	}
	return spec, nil
}
