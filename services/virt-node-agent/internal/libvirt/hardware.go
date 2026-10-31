package libvirt

import (
	"context"
	"encoding/xml"
	"fmt"
	"io"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/domainxml"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/storage"
)

type HardwareChange struct {
	ImageRelativePath string `json:"image_relative_path,omitempty"`
	ImageStoragePool string `json:"image_storage_pool,omitempty"`
	MediaPath string `json:"-"`
	Live         bool                  `json:"live,omitempty"`
	Operation    string                `json:"operation"`
	UUID         string                `json:"uuid"`
	VCPU         int                   `json:"vcpu"`
	MemoryMiB    int                   `json:"memory_mib"`
	Target       string                `json:"target"`
	Bus          string                `json:"bus"`
	RelativePath string                `json:"relative_path"`
	SizeGiB      int                   `json:"size_gib"`
	MAC          string                `json:"mac"`
	Model        string                `json:"model"`
	Network      domainxml.NetworkSpec `json:"network"`
}
type HardwareDisk struct {
	Target       string `json:"target"`
	Bus          string `json:"bus"`
	RelativePath string `json:"relative_path"`
	SizeBytes    int64  `json:"size_bytes"`
	Managed      bool   `json:"managed"`
}
type HardwareNIC struct {
	Type string `json:"type" xml:"type,attr"`
	MAC  struct {
		Address string `xml:"address,attr"`
	} `json:"-" xml:"mac"`
	Model struct {
		Type string `xml:"type,attr"`
	} `json:"-" xml:"model"`
	Source struct {
		Network string `xml:"network,attr,omitempty"`
		Bridge  string `xml:"bridge,attr,omitempty"`
	} `json:"-" xml:"source"`
	VirtualPort *struct {
		Type string `xml:"type,attr"`
	} `json:"-" xml:"virtualport,omitempty"`
	VLAN *struct {
		Tag struct {
			ID int `xml:"id,attr"`
		} `xml:"tag"`
	} `json:"-" xml:"vlan,omitempty"`
	Address     string `json:"mac" xml:"-"`
	ModelName   string `json:"model" xml:"-"`
	NetworkName string `json:"source" xml:"-"`
}
type HardwareInventory struct {
	CDROMs []HardwareCDROM `json:"cdroms"`
	System HardwareSystem `json:"system"`
	UUID      string         `json:"uuid"`
	VCPU      int            `json:"vcpu"`
	MemoryMiB int            `json:"memory_mib"`
	Disks     []HardwareDisk `json:"disks"`
	NICs      []HardwareNIC  `json:"nics"`
}
type HardwareCDROM struct {
	Source string `json:"source"`
	Target string `json:"target"`
	Bus string `json:"bus"`
	Mounted bool `json:"mounted"`
}
type HardwareSystem struct {
	OS struct {
		Firmware string `xml:"firmware,attr" json:"firmware"`
		Loader string `xml:"loader" json:"loader"`
		Type struct { Machine string `xml:"machine,attr" json:"machine"`; Arch string `xml:"arch,attr" json:"arch"` } `xml:"type" json:"type"`
		Boot []struct { Device string `xml:"dev,attr" json:"device"` } `xml:"boot" json:"boot"`
	} `xml:"os" json:"os"`
	CPU struct {
		Mode string `xml:"mode,attr" json:"mode"`
		Model string `xml:"model" json:"model"`
		Topology *struct { Sockets int `xml:"sockets,attr" json:"sockets"`; Cores int `xml:"cores,attr" json:"cores"`; Threads int `xml:"threads,attr" json:"threads"` } `xml:"topology" json:"topology"`
	} `xml:"cpu" json:"cpu"`
}
type xmlPart struct {
	start, end int
	raw        string
}

// Locate direct children with an XML tokenizer, preserving all unrelated bytes.
func xmlParts(content, parent, child string) ([]xmlPart, error) {
	decoder := xml.NewDecoder(strings.NewReader(content))
	stack := []string{}
	parts := []xmlPart{}
	start := -1
	for {
		offset := int(decoder.InputOffset())
		token, err := decoder.Token()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, err
		}
		switch element := token.(type) {
		case xml.StartElement:
			if strings.Join(stack, "/") == parent && element.Name.Local == child {
				start = offset
			}
			stack = append(stack, element.Name.Local)
		case xml.EndElement:
			if len(stack) > 0 {
				stack = stack[:len(stack)-1]
			}
			if start >= 0 && strings.Join(stack, "/") == parent && element.Name.Local == child {
				end := int(decoder.InputOffset())
				parts = append(parts, xmlPart{start, end, content[start:end]})
				start = -1
			}
		}
	}
	return parts, nil
}
func replaceXMLChild(content, parent, child, replacement string) (string, error) {
	parts, err := xmlParts(content, parent, child)
	if err != nil {
		return "", err
	}
	if len(parts) != 1 {
		return "", apierr.New(apierr.CodeConflict, "无法唯一识别硬件配置: "+child, nil)
	}
	p := parts[0]
	return content[:p.start] + replacement + content[p.end:], nil
}
func parseHardware(ctx context.Context, content, root string) (HardwareInventory, error) {
	var parsed struct {
		UUID   string `xml:"uuid"`
		VCPU   int    `xml:"vcpu"`
		Memory struct {
			Unit  string `xml:"unit,attr"`
			Value int    `xml:",chardata"`
		} `xml:"memory"`
		Devices struct {
			Disks []struct {
				Device string `xml:"device,attr"`
				Source struct {
					File string `xml:"file,attr"`
				} `xml:"source"`
				Target struct {
					Dev string `xml:"dev,attr"`
					Bus string `xml:"bus,attr"`
				} `xml:"target"`
			} `xml:"disk"`
			NICs []HardwareNIC `xml:"interface"`
		} `xml:"devices"`
	}
	if err := xml.Unmarshal([]byte(content), &parsed); err != nil {
		return HardwareInventory{}, err
	}
	memory := parsed.Memory.Value
	switch strings.ToLower(parsed.Memory.Unit) {
	case "kib", "":
		memory /= 1024
	case "gib":
		memory *= 1024
	case "mib":
	default:
		return HardwareInventory{}, apierr.New(apierr.CodeConflict, "未知内存单位", nil)
	}
	result := HardwareInventory{UUID: parsed.UUID, VCPU: parsed.VCPU, MemoryMiB: memory, Disks: []HardwareDisk{}, NICs: parsed.Devices.NICs}
	result.CDROMs = []HardwareCDROM{}
	if err := xml.Unmarshal([]byte(content), &result.System); err != nil { return result, err }
	if result.NICs == nil {
		result.NICs = []HardwareNIC{}
	}
	for _, d := range parsed.Devices.Disks {
		if d.Device == "cdrom" {
			result.CDROMs = append(result.CDROMs, HardwareCDROM{Target:d.Target.Dev, Bus:d.Target.Bus, Mounted:d.Source.File != "", Source:d.Source.File})
		}
		if d.Device != "disk" {
			continue
		}
		item := HardwareDisk{Target: d.Target.Dev, Bus: d.Target.Bus}
		relative, err := filepath.Rel(root, d.Source.File)
		if err == nil {
			if _, err = storage.SafePath(root, relative); err == nil {
				item.Managed = true
				item.RelativePath = relative
				_, item.SizeBytes, err = storage.DiskInfo(ctx, d.Source.File)
				if err != nil {
					return result, err
				}
			}
		}
		result.Disks = append(result.Disks, item)
	}
	for i := range result.NICs {
		nic := &result.NICs[i]
		nic.Address = strings.ToLower(nic.MAC.Address)
		nic.ModelName = nic.Model.Type
		nic.NetworkName = nic.Source.Network
		if nic.NetworkName == "" {
			nic.NetworkName = nic.Source.Bridge
		}
	}
	return result, nil
}
func (c *Client) HardwareInventory(ctx context.Context, name, root string) (HardwareInventory, error) {
	content, err := c.run(ctx, "dumpxml", name, "--inactive")
	if err != nil {
		return HardwareInventory{}, err
	}
	return parseHardware(ctx, content, root)
}

func buildNIC(change HardwareChange) (string, error) {
	mac, err := net.ParseMAC(change.MAC)
	if err != nil || len(mac) != 6 || mac[0]&1 != 0 {
		return "", apierr.New(apierr.CodeInvalidArgument, "MAC 必须为单播以太网地址", err)
	}
	if change.Model != "virtio" && change.Model != "e1000e" {
		return "", apierr.New(apierr.CodeInvalidArgument, "网卡型号不受支持", nil)
	}
	n := change.Network
	nic := HardwareNIC{}
	nic.MAC.Address = strings.ToLower(change.MAC)
	nic.Model.Type = change.Model
	if n.NetworkType == "LIBVIRT_NETWORK" {
		if !domainxml.ValidName(n.Network) {
			return "", apierr.New(apierr.CodeInvalidArgument, "网络名无效", nil)
		}
		nic.Type = "network"
		nic.Source.Network = n.Network
	} else if n.NetworkType == "BRIDGE" || n.NetworkType == "OVS" {
		if !domainxml.ValidName(n.NetworkBridge) {
			return "", apierr.New(apierr.CodeInvalidArgument, "网桥名无效", nil)
		}
		nic.Type = "bridge"
		nic.Source.Bridge = n.NetworkBridge
		if n.NetworkType == "OVS" {
			nic.VirtualPort = &struct {
				Type string `xml:"type,attr"`
			}{Type: "openvswitch"}
		}
	} else {
		return "", apierr.New(apierr.CodeInvalidArgument, "网络类型无效", nil)
	}
	if n.VLANID < 0 || n.VLANID > 4094 {
		return "", apierr.New(apierr.CodeInvalidArgument, "VLAN 无效", nil)
	}
	if n.VLANID > 0 {
		if n.NetworkType != "OVS" {
			return "", apierr.New(apierr.CodeInvalidArgument, "VLAN 仅允许 OVS 网络", nil)
		}
		nic.VLAN = &struct {
			Tag struct {
				ID int `xml:"id,attr"`
			} `xml:"tag"`
		}{}
		nic.VLAN.Tag.ID = n.VLANID
	}
	raw, err := xml.Marshal(struct {
		XMLName xml.Name `xml:"interface"`
		HardwareNIC
	}{HardwareNIC: nic})
	return string(raw), err
}
func buildDisk(change HardwareChange, path string) (string, error) {
	if change.Bus != "virtio" && change.Bus != "sata" {
		return "", apierr.New(apierr.CodeInvalidArgument, "仅支持 VirtIO/SATA 磁盘", nil)
	}
	prefix := "vd"
	if change.Bus == "sata" {
		prefix = "sd"
	}
	if len(change.Target) != 3 || !strings.HasPrefix(change.Target, prefix) || change.Target[2] < 'a' || change.Target[2] > 'z' {
		return "", apierr.New(apierr.CodeInvalidArgument, "磁盘设备名无效", nil)
	}
	var device struct {
		XMLName xml.Name `xml:"disk"`
		Type    string   `xml:"type,attr"`
		Device  string   `xml:"device,attr"`
		Driver  struct {
			Name string `xml:"name,attr"`
			Type string `xml:"type,attr"`
		} `xml:"driver"`
		Source struct {
			File string `xml:"file,attr"`
		} `xml:"source"`
		Target struct {
			Dev string `xml:"dev,attr"`
			Bus string `xml:"bus,attr"`
		} `xml:"target"`
	}
	device.Type = "file"
	device.Device = "disk"
	device.Driver.Name = "qemu"
	device.Driver.Type = "qcow2"
	device.Source.File = path
	device.Target.Dev = change.Target
	device.Target.Bus = change.Bus
	raw, err := xml.Marshal(device)
	return string(raw), err
}

func (c *Client) ChangeHardware(ctx context.Context, name, root string, change HardwareChange) (HardwareInventory, error) {
	if change.Live {
		return c.hotAddNIC(ctx, name, root, change)
	}
	fail := func(message string) (HardwareInventory, error) {
		return HardwareInventory{}, apierr.New(apierr.CodeConflict, message, nil)
	}
	if !domainxml.ValidName(name) {
		return fail("域名无效")
	}
	state, err := c.DomainState(ctx, name)
	if err != nil {
		return HardwareInventory{}, err
	}
	if state != StateShutoff {
		return fail("硬件变更必须等待虚拟机正常关机")
	}
	content, err := c.run(ctx, "dumpxml", name, "--inactive")
	if err != nil {
		return HardwareInventory{}, err
	}
	before, err := parseHardware(ctx, content, root)
	if err != nil {
		return before, err
	}
	if change.UUID == "" || before.UUID != change.UUID {
		return fail("域 UUID 已变化，拒绝操作")
	}
	snapshots, err := c.run(ctx, "snapshot-list", name, "--name")
	if err != nil {
		return before, err
	}
	if strings.TrimSpace(snapshots) != "" {
		return fail("存在快照，需先处理快照一致性再变更硬件")
	}
	updated := content
	switch change.Operation {
	case "cdrom-set", "cdrom-remove":
		updated, err = replaceCDROM(content, change.Target, change.MediaPath, change.Operation == "cdrom-remove")
		if err != nil { return before, err }
		updated, err = opticalBootOrder(updated, change.Operation == "cdrom-remove")
		if err != nil { return before, err }
	case "compute":
		if change.VCPU < 1 || change.VCPU > 128 || change.MemoryMiB < 128 || change.MemoryMiB > 1048576 {
			return fail("CPU 或内存超出范围")
		}
		for _, unsupported := range []string{"<numa", "<hostdev", "<vcpus>", "<vcpupin", "<emulatorpin", "cpuset="} {
			if strings.Contains(content, unsupported) {
				return fail("复杂 CPU/直通配置需人工核对")
			}
		}
		updated, err = replaceXMLChild(updated, "domain", "vcpu", fmt.Sprintf("<vcpu placement='static'>%d</vcpu>", change.VCPU))
		if err != nil {
			return before, err
		}
		updated, err = replaceXMLChild(updated, "domain", "memory", fmt.Sprintf("<memory unit='MiB'>%d</memory>", change.MemoryMiB))
		if err != nil {
			return before, err
		}
		current, _ := xmlParts(updated, "domain", "currentMemory")
		if len(current) > 0 {
			updated, err = replaceXMLChild(updated, "domain", "currentMemory", fmt.Sprintf("<currentMemory unit='MiB'>%d</currentMemory>", change.MemoryMiB))
			if err != nil {
				return before, err
			}
		}
		cpus, _ := xmlParts(updated, "domain", "cpu")
		topology := fmt.Sprintf("<topology sockets='1' cores='%d' threads='1'/>", change.VCPU)
		if len(cpus) == 1 {
			parts, _ := xmlParts(updated, "domain/cpu", "topology")
			if len(parts) == 1 {
				p := parts[0]
				updated = updated[:p.start] + topology + updated[p.end:]
			} else {
				p := cpus[0]
				cpu := strings.Replace(p.raw, "</cpu>", topology+"</cpu>", 1)
				if strings.HasSuffix(p.raw, "/>") {
					cpu = strings.TrimSuffix(p.raw, "/>") + ">" + topology + "</cpu>"
				}
				updated = updated[:p.start] + cpu + updated[p.end:]
			}
		} else if len(cpus) == 0 {
			updated = strings.Replace(updated, "<devices>", "<cpu mode='host-model'>"+topology+"</cpu><devices>", 1)
		}
	case "disk-add", "disk-attach", "disk-detach", "disk-resize":
		path, err := storage.SafePathAllowMissing(root, change.RelativePath)
		if err != nil {
			return before, err
		}
		if change.SizeGiB < 1 || change.SizeGiB > 2048 {
			return fail("磁盘容量超出范围")
		}
		found := false
		for _, d := range before.Disks {
			if d.RelativePath == change.RelativePath && d.Target != change.Target {
				return fail("磁盘文件已挂载在其他设备号")
			}
			if d.Target == change.Target {
				found = true
				if !d.Managed || d.RelativePath != change.RelativePath {
					return fail("磁盘路径或设备发生变化")
				}
			}
		}
		if change.Operation == "disk-detach" {
			if len(before.Disks) > 0 && before.Disks[0].Target == change.Target {
				return fail("禁止卸载系统盘")
			}
			if !found {
				return before, nil
			}
			parts, _ := xmlParts(content, "domain/devices", "disk")
			for _, p := range parts {
				var d struct {
					Target struct {
						Dev string `xml:"dev,attr"`
					} `xml:"target"`
				}
				_ = xml.Unmarshal([]byte(p.raw), &d)
				if d.Target.Dev == change.Target {
					updated = content[:p.start] + content[p.end:]
					break
				}
			}
		} else if change.Operation == "disk-resize" {
			if !found {
				return fail("目标磁盘未挂载")
			}
			format, size, err := storage.DiskInfo(ctx, path)
			if err != nil {
				return before, err
			}
			if format != "QCOW2" || int64(change.SizeGiB)*1024*1024*1024 < size {
				return fail("仅允许 QCOW2 扩容，禁止缩小")
			}
			if int64(change.SizeGiB)*1024*1024*1024 > size {
				output, err := exec.CommandContext(ctx, "qemu-img", "resize", "--", path, strconv.Itoa(change.SizeGiB)+"G").CombinedOutput()
				if err != nil {
					return before, apierr.New(apierr.CodeOperationFailed, "扩容失败: "+string(output), err)
				}
			}
		} else {
			if !found {
				if len(before.Disks) >= 9 {
					return fail("最多支持 9 块磁盘")
				}
				raw, err := buildDisk(change, path)
				if err != nil {
					return before, err
				}
				parts, _ := xmlParts(content, "domain/devices", "disk")
				for _, p := range parts {
					if strings.Contains(p.raw, "dev='"+change.Target+"'") || strings.Contains(p.raw, "dev=\""+change.Target+"\"") {
						return fail("设备号已占用")
					}
				}
				if change.Operation == "disk-add" {
					if err = storage.CreateDisk(ctx, path, change.SizeGiB); err != nil {
						return before, err
					}
				}
				updated = strings.Replace(content, "</devices>", raw+"</devices>", 1)
			}
			format, size, err := storage.DiskInfo(ctx, path)
			if err != nil {
				return before, err
			}
			if format != "QCOW2" || size != int64(change.SizeGiB)*1024*1024*1024 {
				return fail("文件格式或容量不符合目标，拒绝重复分配")
			}
		}
	case "nic-add", "nic-remove":
		mac, err := net.ParseMAC(change.MAC)
		if err != nil || len(mac) != 6 {
			return fail("MAC 无效")
		}
		found := false
		for _, n := range before.NICs {
			if n.Address == strings.ToLower(change.MAC) {
				found = true
				if change.Operation == "nic-add" && n.NetworkName != change.Network.Network && n.NetworkName != change.Network.NetworkBridge {
					return fail("MAC 已绑定其他网络")
				}
			}
		}
		if change.Operation == "nic-add" && !found {
			if len(before.NICs) >= 8 {
				return fail("最多支持 8 张网卡")
			}
			raw, err := buildNIC(change)
			if err != nil {
				return before, err
			}
			updated = strings.Replace(content, "</devices>", raw+"</devices>", 1)
		}
		if change.Operation == "nic-remove" {
			if !found {
				return before, nil
			}
			parts, _ := xmlParts(content, "domain/devices", "interface")
			for _, p := range parts {
				var n HardwareNIC
				_ = xml.Unmarshal([]byte(p.raw), &n)
				if strings.EqualFold(n.MAC.Address, change.MAC) {
					updated = content[:p.start] + content[p.end:]
					break
				}
			}
		}
	default:
		return fail("不支持的硬件操作")
	}
	if updated != content {
		if err = c.DefineDomain(ctx, updated); err != nil {
			return before, err
		}
	}
	actual, err := c.HardwareInventory(ctx, name, root)
	if err != nil {
		return before, err
	}
	if change.Operation == "cdrom-set" {
		verified := false
		for _, drive := range actual.CDROMs { if drive.Target == change.Target && drive.Source == change.MediaPath { verified = true } }
		if !verified { return actual, apierr.New(apierr.CodeConflict, "节点未确认 ISO 光驱配置", nil) }
	}
	return actual, nil
}

func (c *Client) hotAddNIC(ctx context.Context, name, root string, change HardwareChange) (HardwareInventory, error) {
	fail := func(msg string) (HardwareInventory, error) {
		return HardwareInventory{}, apierr.New(apierr.CodeConflict, msg, nil)
	}
	if !domainxml.ValidName(name) || change.Operation != "nic-add" {
		return fail("热变更仅支持新增网卡")
	}
	state, err := c.DomainState(ctx, name)
	if err != nil {
		return HardwareInventory{}, err
	}
	if state != StateRunning {
		return fail("虚拟机未处于运行状态")
	}
	raw, err := buildNIC(change)
	if err != nil {
		return HardwareInventory{}, err
	}
	// Compare both definitions; retry repairs a partially completed attach using the same MAC.
	matched := func(content string) (bool, error) {
		inventory, err := parseHardware(ctx, content, root)
		if err != nil {
			return false, err
		}
		if change.UUID == "" || inventory.UUID != change.UUID {
			return false, apierr.New(apierr.CodeConflict, "域 UUID 不匹配", nil)
		}
		for _, n := range inventory.NICs {
			if n.Address == strings.ToLower(change.MAC) {
				if n.ModelName != change.Model || (n.NetworkName != change.Network.Network && n.NetworkName != change.Network.NetworkBridge) {
					return false, apierr.New(apierr.CodeConflict, "网卡 MAC 已用于其他配置", nil)
				}
				return true, nil
			}
		}
		if len(inventory.NICs) >= 8 {
			return false, apierr.New(apierr.CodeConflict, "最多支持 8 个网卡", nil)
		}
		return false, nil
	}
	snapshots, err := c.run(ctx, "snapshot-list", name, "--name")
	if err != nil {
		return HardwareInventory{}, err
	}
	if strings.TrimSpace(snapshots) != "" {
		return fail("存在快照，请先处理快照一致性后热接入")
	}
	for _, args := range [][]string{{"dumpxml", name, "--inactive"}, {"dumpxml", name}} {
		content, err := c.run(ctx, args...)
		if err != nil {
			return HardwareInventory{}, err
		}
		if _, err := matched(content); err != nil {
			return HardwareInventory{}, err
		}
	}
	for _, mode := range []string{"--config", "--live"} {
		args := []string{"dumpxml", name}
		if mode == "--config" {
			args = append(args, "--inactive")
		}
		content, err := c.run(ctx, args...)
		if err != nil {
			return HardwareInventory{}, err
		}
		found, err := matched(content)
		if err != nil {
			return HardwareInventory{}, err
		}
		if !found {
			file, err := os.CreateTemp("", "cloudvirt-nic-*.xml")
			if err != nil {
				return HardwareInventory{}, err
			}
			path := file.Name()
			_, err = file.WriteString(raw)
			closeErr := file.Close()
			if err == nil {
				err = closeErr
			}
			if err == nil {
				_, err = c.run(ctx, "attach-device", name, path, mode)
			}
			os.Remove(path)
			if err != nil {
				return HardwareInventory{}, err
			}
		}
	}
	for _, args := range [][]string{{"dumpxml", name, "--inactive"}, {"dumpxml", name}} {
		content, err := c.run(ctx, args...)
		if err != nil {
			return HardwareInventory{}, err
		}
		found, err := matched(content)
		if err != nil {
			return HardwareInventory{}, err
		}
		if !found {
			return fail("热接入尚未在运行与持久配置中同时确认，请核对原任务")
		}
	}
	return c.HardwareInventory(ctx, name, root)
}
