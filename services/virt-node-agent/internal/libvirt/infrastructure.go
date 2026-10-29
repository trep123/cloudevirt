package libvirt

import (
	"context"
	"encoding/xml"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/domainxml"
)

type StoragePool struct {
	XMLName    xml.Name `xml:"pool" json:"-"`
	Name       string   `xml:"name" json:"name"`
	UUID       string   `xml:"uuid" json:"uuid"`
	Type       string   `xml:"type,attr" json:"type"`
	Capacity   uint64   `xml:"capacity" json:"capacity_bytes"`
	Allocation uint64   `xml:"allocation" json:"allocation_bytes"`
	Available  uint64   `xml:"available" json:"available_bytes"`
	Target     struct {
		Path string `xml:"path" json:"path"`
	} `xml:"target" json:"target"`
	Active bool `xml:"-" json:"active"`
}

func (c *Client) ListStoragePools(ctx context.Context) ([]StoragePool, error) {
	names, err := c.run(ctx, "pool-list", "--all", "--name")
	if err != nil {
		return nil, err
	}
	active, err := c.run(ctx, "pool-list", "--name")
	if err != nil {
		return nil, err
	}
	activeSet := map[string]bool{}
	for _, name := range strings.Fields(active) {
		activeSet[name] = true
	}
	pools := []StoragePool{}
	for _, name := range strings.Split(names, "\n") {
		name = strings.TrimSpace(name)
		if name == "" {
			continue
		}
		if activeSet[name] {
			if _, err := c.run(ctx, "pool-refresh", name); err != nil {
				return nil, err
			}
		}
		raw, err := c.run(ctx, "pool-dumpxml", name)
		if err != nil {
			return nil, err
		}
		var pool StoragePool
		if err := xml.Unmarshal([]byte(raw), &pool); err != nil {
			return nil, err
		}
		pool.Active = activeSet[name]
		pools = append(pools, pool)
	}
	return pools, nil
}

// CreateDirectoryPool only creates a child of the configured managed disk root.
// It never accepts a client-supplied host path, device or mount command.
func (c *Client) CreateDirectoryPool(ctx context.Context, name, root string) error {
	return c.CreateDirectoryPoolAt(ctx, name, root, filepath.Join(root, name))
}

func (c *Client) CreateDirectoryPoolAt(ctx context.Context, name, root, target string) error {
	if !domainxml.ValidName(name) || !strings.HasPrefix(name, "cv-") {
		return apierr.New(apierr.CodeInvalidArgument, "存储池名称必须以 cv- 开头", nil)
	}
	base, err := filepath.EvalSymlinks(root)
	if err != nil {
		return err
	}
	relative, err := filepath.Rel(filepath.Clean(root), filepath.Clean(target))
	if err != nil || !filepath.IsAbs(target) || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return apierr.New(apierr.CodeInvalidArgument, "存储目录越出允许范围", err)
	}
	target = filepath.Join(base, relative)
	pools, err := c.ListStoragePools(ctx)
	if err != nil {
		return err
	}
	found := false
	for _, pool := range pools {
		if pool.Name != name && filepath.Clean(pool.Target.Path) == target {
			return apierr.New(apierr.CodeConflict, "该目录已被其他存储池使用", nil)
		}
		if pool.Name != name {
			continue
		}
		if pool.Type != "dir" || pool.Target.Path != target {
			return apierr.New(apierr.CodeOperationFailed, "同名存储池配置不一致", nil)
		}
		found = true
	}
	if !found {
		rooted, err := os.OpenRoot(base)
		if err != nil {
			return err
		}
		defer rooted.Close()
		if err = rooted.MkdirAll(relative, 0770); err != nil {
			return apierr.New(apierr.CodeOperationFailed, "无法创建目录，请检查节点存储权限与路径", err)
		}
		resolved, err := filepath.EvalSymlinks(target)
		if err != nil || resolved != target {
			return apierr.New(apierr.CodeInvalidArgument, "存储目录不允许符号链接", err)
		}
		info, err := os.Lstat(target)
		if err != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
			return apierr.New(apierr.CodeOperationFailed, "存储池目录不安全", err)
		}
		// Go's FileMode represents setgid separately from Unix permission bits.
		if _, err := c.run(ctx, "pool-define-as", name, "dir", "--target", target); err != nil {
			return err
		}
	}
	for _, pool := range pools {
		if pool.Name == name && pool.Active {
			_, err = c.run(ctx, "pool-autostart", name)
			return err
		}
	}
	if _, err := c.run(ctx, "pool-start", name); err != nil {
		return err
	}
	_, err = c.run(ctx, "pool-autostart", name)
	return err
}

type Snapshot struct {
	Name      string `xml:"name" json:"name"`
	State     string `xml:"state" json:"state"`
	CreatedAt int64  `xml:"creationTime" json:"created_at"`
	Parent    string `xml:"parent>name" json:"parent"`
	Disks     []struct {
		Snapshot string `xml:"snapshot,attr"`
	} `xml:"disks>disk" json:"-"`
	Supported bool `xml:"-" json:"supported"`
}

func (c *Client) ListSnapshots(ctx context.Context, name string) ([]Snapshot, error) {
	if !domainxml.ValidName(name) {
		return nil, apierr.New(apierr.CodeInvalidArgument, "域名无效", nil)
	}
	raw, err := c.run(ctx, "snapshot-list", name, "--name")
	if err != nil {
		return nil, err
	}
	snapshots := []Snapshot{}
	for _, snapshotName := range strings.Split(raw, "\n") {
		snapshotName = strings.TrimSpace(snapshotName)
		if snapshotName == "" {
			continue
		}
		content, err := c.run(ctx, "snapshot-dumpxml", name, snapshotName)
		if err != nil {
			return nil, err
		}
		var snapshot Snapshot
		if err := xml.Unmarshal([]byte(content), &snapshot); err != nil {
			return nil, err
		}
		snapshot.Supported = strings.HasPrefix(snapshot.Name, "cv-") && snapshot.State == "shutoff"
		for _, disk := range snapshot.Disks {
			if disk.Snapshot == "external" {
				snapshot.Supported = false
			}
		}
		snapshots = append(snapshots, snapshot)
	}
	return snapshots, nil
}

// SnapshotAction intentionally supports only offline internal qcow2 snapshots.
func (c *Client) SnapshotAction(ctx context.Context, domain, name, action, diskRoot string) error {
	if !domainxml.ValidName(domain) || !strings.HasPrefix(domain, "cv-") ||
		!domainxml.ValidName(name) || !strings.HasPrefix(name, "cv-") {
		return apierr.New(apierr.CodeInvalidArgument, "仅支持 CloudVirt 管理的域和快照名称", nil)
	}
	state, err := c.DomainState(ctx, domain)
	if err != nil {
		return err
	}
	if state != StateShutoff {
		return apierr.New(apierr.CodeOperationFailed, "快照操作必须先关闭虚拟机", nil)
	}
	// Validate actual domain disks again at the execution boundary.
	raw, err := c.DumpXML(ctx, domain)
	if err != nil {
		return err
	}
	var definition struct {
		Disks []struct {
			Device string `xml:"device,attr"`
			Driver struct {
				Type string `xml:"type,attr"`
			} `xml:"driver"`
			Source struct {
				File string `xml:"file,attr"`
			} `xml:"source"`
			Target struct {
				Dev string `xml:"dev,attr"`
			} `xml:"target"`
		} `xml:"devices>disk"`
	}
	if err := xml.Unmarshal([]byte(raw), &definition); err != nil {
		return err
	}
	root, err := filepath.EvalSymlinks(diskRoot)
	if err != nil {
		return err
	}
	diskCount := 0
	for _, disk := range definition.Disks {
		if disk.Device != "disk" {
			continue
		}
		diskCount++
		path, err := filepath.EvalSymlinks(disk.Source.File)
		if err != nil {
			return err
		}
		relative, err := filepath.Rel(root, path)
		if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) ||
			disk.Driver.Type != "qcow2" {
			return apierr.New(apierr.CodeOperationFailed, "仅支持受管目录中的 qcow2 磁盘", err)
		}
	}
	if diskCount == 0 {
		return apierr.New(apierr.CodeOperationFailed, "虚拟机没有可快照磁盘", nil)
	}
	snapshots, err := c.ListSnapshots(ctx, domain)
	if err != nil {
		return err
	}
	var target *Snapshot
	for i := range snapshots {
		if snapshots[i].Name == name {
			target = &snapshots[i]
		}
	}
	switch action {
	case "create":
		if target != nil {
			if !target.Supported {
				return apierr.New(apierr.CodeOperationFailed, "同名快照类型不受支持", nil)
			}
			return nil
		}
		_, err = c.run(ctx, "snapshot-create-as", domain, name, "--atomic")
	case "revert", "delete":
		if target == nil {
			if action == "delete" {
				return nil
			}
			return apierr.New(apierr.CodeOperationFailed, "快照不存在", nil)
		}
		if !target.Supported {
			return apierr.New(apierr.CodeOperationFailed, "不支持恢复或删除此类型快照", nil)
		}
		if action == "delete" {
			for _, snapshot := range snapshots {
				if snapshot.Parent == name {
					return apierr.New(apierr.CodeOperationFailed, "请先删除子快照", nil)
				}
			}
		}
		_, err = c.run(ctx, "snapshot-"+action, domain, name)
	default:
		err = fmt.Errorf("不支持的快照操作")
	}
	return err
}
