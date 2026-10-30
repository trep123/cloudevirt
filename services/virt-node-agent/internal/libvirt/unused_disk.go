package libvirt

import (
	"context"
	"encoding/json"
	"encoding/xml"
	"errors"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/storage"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

func diskSources(raw string) ([]string, error) {
	d := xml.NewDecoder(strings.NewReader(raw))
	paths := []string{}
	for {
		tok, e := d.Token()
		if e == io.EOF {
			return paths, nil
		}
		if e != nil {
			return nil, e
		}
		if tag, ok := tok.(xml.StartElement); ok && tag.Name.Local == "source" {
			for _, a := range tag.Attr {
				if a.Name.Local == "file" {
					paths = append(paths, a.Value)
				}
			}
		}
	}
}
func (c *Client) CheckUnusedDisk(ctx context.Context, root, relative string) error {
	path, err := storage.SafePath(root, relative)
	if err != nil {
		var e *apierr.Error
		if errors.As(err, &e) && e.Code == apierr.CodeNotFound {
			return nil
		}
		return err
	}
	info, err := os.Lstat(filepath.Join(root, relative))
	if err != nil {
		return err
	}
	if !info.Mode().IsRegular() {
		return apierr.New(apierr.CodeConflict, "只能删除受管普通磁盘文件，禁止符号链接或目录", nil)
	}
	target, err := os.Stat(path)
	if err != nil {
		return err
	}
	same := func(p string) bool { f, e := os.Stat(p); return e == nil && os.SameFile(target, f) }
	inspect := map[string]bool{}
	names, err := c.run(ctx, "list", "--all", "--name")
	if err != nil {
		return err
	}
	for _, name := range strings.Fields(names) {
		// Live and persistent definitions can reference different disks.
		current, e := c.run(ctx, "dumpxml", name)
		if e != nil {
			return e
		}
		if e = collectDiskReferences(current, same, inspect); e != nil {
			return e
		}
		inactive, e := c.run(ctx, "dumpxml", name, "--inactive")
		if e != nil {
			return apierr.New(apierr.CodeConflict, "无法核对持久域定义，暂不删除磁盘", e)
		}
		if e = collectDiskReferences(inactive, same, inspect); e != nil {
			return e
		}
		snapshots, e := c.run(ctx, "snapshot-list", name, "--name")
		if e != nil {
			return e
		}
		for _, snapshot := range strings.Fields(snapshots) {
			raw, e := c.run(ctx, "snapshot-dumpxml", name, snapshot)
			if e != nil {
				return e
			}
			if e = collectDiskReferences(raw, same, inspect); e != nil {
				return e
			}
		}
	}
	err = filepath.WalkDir(root, func(p string, d os.DirEntry, e error) error {
		if e != nil {
			return e
		}
		if !d.IsDir() && strings.HasSuffix(strings.ToLower(p), ".qcow2") && !same(p) {
			if d.Type()&os.ModeSymlink != 0 {
				return apierr.New(apierr.CodeConflict, "磁盘目录存在无法核验的符号链接", nil)
			}
			inspect[p] = true
		}
		return nil
	})
	if err != nil {
		return err
	}
	for p := range inspect {
		if same(p) {
			continue
		}
		out, e := exec.CommandContext(ctx, "qemu-img", "info", "-U", "--backing-chain", "--output=json", "--", p).CombinedOutput()
		if e != nil {
			return apierr.New(apierr.CodeConflict, "无法核对磁盘依赖，请先处理节点磁盘或镜像错误", e)
		}
		var chain []struct {
			File    string `json:"filename"`
			Backing string `json:"full-backing-filename"`
			Data    struct {
				Data struct {
					File string `json:"data-file"`
				} `json:"data"`
			} `json:"format-specific"`
		}
		if e = json.Unmarshal(out, &chain); e != nil {
			return e
		}
		for _, item := range chain {
			for _, ref := range []string{item.File, item.Backing, item.Data.Data.File} {
				if ref == "" {
					continue
				}
				if !filepath.IsAbs(ref) {
					ref = filepath.Join(filepath.Dir(p), ref)
				}
				if same(ref) {
					return apierr.New(apierr.CodeConflict, "磁盘仍被其他磁盘的 backing/data-file 链引用", nil)
				}
			}
		}
	}
	return nil
}

func collectDiskReferences(raw string, same func(string) bool, inspect map[string]bool) error {
	refs, err := diskSources(raw)
	if err != nil {
		return err
	}
	for _, ref := range refs {
		if same(ref) {
			return apierr.New(apierr.CodeConflict, "磁盘仍被虚拟机、持久配置或快照引用", nil)
		}
		inspect[ref] = true
	}
	return nil
}

func (c *Client) RemoveUnusedDisk(ctx context.Context, root, relative string) error {
	if err := c.CheckUnusedDisk(ctx, root, relative); err != nil {
		return err
	}
	rooted, err := os.OpenRoot(root)
	if err != nil {
		return err
	}
	defer rooted.Close()
	if err = rooted.Remove(relative); err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
}
