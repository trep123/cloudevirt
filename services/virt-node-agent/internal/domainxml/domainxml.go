// Package domainxml 生成并校验 libvirt 域定义 XML。
//
// 所有动态字段通过 encoding/xml 序列化，天然转义，禁止字符串拼接；
// 生成后必须重新解析校验，失败时不得调用 libvirt。
package domainxml

import (
	"encoding/xml"
	"fmt"
	"regexp"
	"strings"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
)

// 默认值。
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

// Spec 是创建域所需的全部输入。
type Spec struct {
	Name      string
	UUID      string
	VCPU      int
	MemoryMiB int
	DiskPath  string
	Network   string
}

// domain 是 XML 结构，字段顺序即输出顺序。
type domain struct {
	XMLName xml.Name `xml:"domain"`
	Type    string   `xml:"type,attr"`
	Name    string   `xml:"name"`
	UUID    string   `xml:"uuid"`
	Memory  memory   `xml:"memory"`
	VCPU    int      `xml:"vcpu"`
	OS      osSpec   `xml:"os"`
	Devices devices  `xml:"devices"`
}

type memory struct {
	Unit  string `xml:"unit,attr"`
	Value int    `xml:",chardata"`
}

type osSpec struct {
	Type osType `xml:"type"`
}

type osType struct {
	Arch    string `xml:"arch,attr"`
	Machine string `xml:"machine,attr"`
	Value   string `xml:",chardata"`
}

type devices struct {
	Disks     []disk      `xml:"disk"`
	Interface *iface      `xml:"interface,omitempty"`
	Console   consoleSpec `xml:"console"`
}

type disk struct {
	Type   string    `xml:"type,attr"`
	Device string    `xml:"device,attr"`
	Driver diskDrive `xml:"driver"`
	Source diskSrc   `xml:"source"`
	Target diskTgt   `xml:"target"`
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
	Type   string     `xml:"type,attr"`
	Source ifaceSrc   `xml:"source"`
	Model  ifaceModel `xml:"model"`
}

type ifaceSrc struct {
	Network string `xml:"network,attr"`
}

type ifaceModel struct {
	Type string `xml:"type,attr"`
}

type consoleSpec struct {
	Type string `xml:"type,attr"`
}

// ValidateSpec 校验输入字段格式与取值范围。
func ValidateSpec(spec Spec) error {
	if !namePattern.MatchString(spec.Name) {
		return apierr.New(apierr.CodeInvalidArgument, "域名格式非法", nil)
	}
	if !uuidPattern.MatchString(spec.UUID) {
		return apierr.New(apierr.CodeInvalidArgument, "UUID 格式非法", nil)
	}
	if spec.VCPU <= 0 || spec.VCPU > 128 {
		return apierr.New(apierr.CodeInvalidArgument, "vCPU 数量超出允许范围", nil)
	}
	if spec.MemoryMiB < 128 || spec.MemoryMiB > 1048576 {
		return apierr.New(apierr.CodeInvalidArgument, "内存大小超出允许范围", nil)
	}
	if strings.TrimSpace(spec.DiskPath) == "" {
		return apierr.New(apierr.CodeInvalidArgument, "磁盘路径不能为空", nil)
	}
	if spec.Network != "" && !namePattern.MatchString(spec.Network) {
		return apierr.New(apierr.CodeInvalidArgument, "网络名称格式非法", nil)
	}
	return nil
}

// Build 生成域定义 XML。
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
			Disks: []disk{{
				Type:   "file",
				Device: "disk",
				Driver: diskDrive{Name: "qemu", Type: DiskFormat},
				Source: diskSrc{File: spec.DiskPath},
				Target: diskTgt{Dev: "vda", Bus: DiskBus},
			}},
			Console: consoleSpec{Type: "pty"},
		},
	}
	if spec.Network != "" {
		payload.Devices.Interface = &iface{
			Type:   "network",
			Source: ifaceSrc{Network: spec.Network},
			Model:  ifaceModel{Type: "virtio"},
		}
	}

	encoded, err := xml.MarshalIndent(payload, "", "  ")
	if err != nil {
		return "", apierr.New(apierr.CodeOperationFailed, "域 XML 生成失败", err)
	}
	content := xml.Header + string(encoded)
	if err := Validate(content); err != nil {
		return "", err
	}
	return content, nil
}

// Validate 校验 XML 结构完整且关键字段与约定一致。
func Validate(content string) error {
	var parsed domain
	if err := xml.Unmarshal([]byte(content), &parsed); err != nil {
		return apierr.New(apierr.CodeOperationFailed, "域 XML 解析失败", err)
	}
	if parsed.Name == "" || parsed.UUID == "" {
		return apierr.New(apierr.CodeOperationFailed, "域 XML 缺少名称或 UUID", nil)
	}
	if parsed.Memory.Value <= 0 || parsed.VCPU <= 0 {
		return apierr.New(apierr.CodeOperationFailed, "域 XML 缺少内存或 vCPU", nil)
	}
	if len(parsed.Devices.Disks) == 0 || parsed.Devices.Disks[0].Source.File == "" {
		return apierr.New(apierr.CodeOperationFailed, "域 XML 缺少磁盘定义", nil)
	}
	if parsed.Devices.Disks[0].Target.Bus != DiskBus {
		return apierr.New(apierr.CodeOperationFailed, "磁盘总线不符合约定", nil)
	}
	return nil
}

// memoryToMiB 按 unit 归一化内存值到 MiB（virsh dumpxml 默认输出 KiB）。
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

// Describe 返回简短摘要，便于日志与调试。
func Describe(spec Spec) string {
	return fmt.Sprintf("%s(%s) vcpu=%d mem=%dMiB", spec.Name, spec.UUID, spec.VCPU, spec.MemoryMiB)
}

// Parse 从域定义 XML 中提取关键字段，用于创建后核对。
//
// Args:
//
//	content: virsh dumpxml 输出的 XML。
//
// Returns:
//
//	提取出的规格；缺少关键字段时返回错误。
func Parse(content string) (Spec, error) {
	var parsed domain
	if err := xml.Unmarshal([]byte(content), &parsed); err != nil {
		return Spec{}, apierr.New(apierr.CodeOperationFailed, "域 XML 解析失败", err)
	}
	if parsed.Name == "" || parsed.UUID == "" {
		return Spec{}, apierr.New(apierr.CodeOperationFailed, "域 XML 缺少名称或 UUID", nil)
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
	if parsed.Devices.Interface != nil {
		spec.Network = parsed.Devices.Interface.Source.Network
	}
	return spec, nil
}
