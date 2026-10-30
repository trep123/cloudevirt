package storage

import (
	"context"
	"fmt"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
)

var baseLocks sync.Map

// Linked clones depend on a private read-only full base snapshot, never on a mutable uploaded source.
func CloneLinked(ctx context.Context, root, relative, checksum, format, target string, sizeGiB int) error {
	if format != "" && len(checksum) != 64 {
		return apierr.New(apierr.CodeConflict, "源镜像摘要缺失", nil)
	}
	info, err := InspectContext(ctx, root, relative)
	if err != nil {
		return err
	}
	if checksum != "" && (!strings.EqualFold(info.ChecksumSHA256, checksum) || !strings.EqualFold(info.Format, format)) {
		return apierr.New(apierr.CodeConflict, "源镜像已变化", nil)
	}
	if (info.Format != "QCOW2" && info.Format != "RAW") || int64(sizeGiB)*1024*1024*1024 < info.VirtualSizeBytes {
		return apierr.New(apierr.CodeInvalidArgument, "链接克隆格式或容量无效", nil)
	}
	cache := filepath.Join(filepath.Dir(target), ".bases")
	if meta, e := os.Lstat(cache); e == nil && (!meta.IsDir() || meta.Mode()&os.ModeSymlink != 0) {
		return apierr.New(apierr.CodeConflict, "基础盘缓存目录不可验证", nil)
	}
	if err := os.MkdirAll(cache, 0755); err != nil {
		return err
	}
	base := filepath.Join(cache, info.ChecksumSHA256+".qcow2")
	lock, _ := baseLocks.LoadOrStore(base, &sync.Mutex{})
	m := lock.(*sync.Mutex)
	m.Lock()
	if _, err := os.Lstat(base); os.IsNotExist(err) {
		err = cloneInspected(ctx, root, relative, info, base, int((info.VirtualSizeBytes+1024*1024*1024-1)/(1024*1024*1024)))
		if err == nil {
			err = os.Chmod(base, 0444)
		}
		if err != nil {
			m.Unlock()
			return err
		}
	} else if err != nil {
		m.Unlock()
		return err
	}
	stat, err := os.Lstat(base)
	if err != nil || !stat.Mode().IsRegular() || stat.Mode().Perm()&0222 != 0 {
		m.Unlock()
		return apierr.New(apierr.CodeConflict, "链接克隆基础盘不可验证或可写", err)
	}
	m.Unlock()
	tmp, err := os.CreateTemp(filepath.Dir(target), ".linked-*.qcow2")
	if err != nil {
		return err
	}
	name := tmp.Name()
	tmp.Close()
	defer os.Remove(name)
	if out, err := exec.CommandContext(ctx, "qemu-img", "create", "-f", "qcow2", "-F", "qcow2", "-b", base, name, fmt.Sprintf("%dG", sizeGiB)).CombinedOutput(); err != nil {
		return apierr.New(apierr.CodeOperationFailed, "创建链接克隆失败: "+string(out), err)
	}
	if err := os.Chmod(name, 0600); err != nil {
		return err
	}
	file, err := os.Open(name)
	if err != nil {
		return err
	}
	err = file.Sync()
	file.Close()
	if err != nil {
		return err
	}
	if err := os.Link(name, target); err != nil {
		return apierr.New(apierr.CodeConflict, "链接克隆目标已存在或发布失败", err)
	}
	return nil
}
