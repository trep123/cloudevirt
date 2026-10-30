package httpapi

import (
	"context"
	"path/filepath"
	"strings"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/libvirt"
)

// diskRootForPool maps an authorized control-plane pool name to an active libvirt
// directory pool whose target remains beneath an operator-approved storage root.
func diskRootForPool(ctx context.Context, deps Dependencies, name string) (string, error) {
	if name == "" {
		return deps.DiskDir, nil
	}
	if !strings.HasPrefix(name, "cv-") || strings.ContainsAny(name, "/\\\x00") {
		return "", apierr.New(apierr.CodeInvalidArgument, "存储池名称无效", nil)
	}
	lister, ok := deps.Virtualizer.(interface {
		ListStoragePools(context.Context) ([]libvirt.StoragePool, error)
	})
	if !ok {
		return "", apierr.New(apierr.CodeConflict, "节点不支持存储池查询", nil)
	}
	pools, err := lister.ListStoragePools(ctx)
	if err != nil {
		return "", err
	}
	for _, pool := range pools {
		if pool.Name != name {
			continue
		}
		if pool.Type != "dir" || !pool.Active || !filepath.IsAbs(pool.Target.Path) {
			return "", apierr.New(apierr.CodeConflict, "存储池未激活或不是目录类型", nil)
		}
		path := filepath.Clean(pool.Target.Path)
		resolved, err := filepath.EvalSymlinks(path)
		if err != nil || resolved != path {
			return "", apierr.New(apierr.CodeInvalidArgument, "存储池目录不允许符号链接", err)
		}
		roots := deps.StorageRoots
		if len(roots) == 0 {
			roots = []string{deps.DiskDir}
		}
		for _, root := range roots {
			base, err := filepath.EvalSymlinks(root)
			if err != nil || base != filepath.Clean(root) {
				continue
			}
			rel, err := filepath.Rel(base, path)
			if err == nil && rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
				return path, nil
			}
		}
		return "", apierr.New(apierr.CodeInvalidArgument, "存储池目录不在节点允许范围内", nil)
	}
	return "", apierr.New(apierr.CodeConflict, "存储池不存在或尚未激活", nil)
}
