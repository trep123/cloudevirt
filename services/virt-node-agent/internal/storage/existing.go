package storage

import (
	"context"
	"encoding/json"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"os"
	"os/exec"
	"strings"
)

// InspectExistingDisk checks a standalone qcow2 without reading/hashing its entire contents.
func InspectExistingDisk(ctx context.Context, root, relative string) (FileInfo, error) {
	for _, part := range strings.Split(relative, "/") {
		if strings.HasPrefix(part, ".") {
			return FileInfo{}, apierr.New(apierr.CodeInvalidArgument, "禁止使用节点内部保留路径", nil)
		}
	}
	path, err := SafePath(root, relative)
	if err != nil {
		return FileInfo{}, err
	}
	stat, err := os.Stat(path)
	if err != nil || !stat.Mode().IsRegular() {
		return FileInfo{}, apierr.New(apierr.CodeInvalidArgument, "系统盘必须为普通文件", err)
	}
	out, err := exec.CommandContext(ctx, "qemu-img", "info", "--output=json", "--", path).Output()
	if err != nil {
		return FileInfo{}, apierr.New(apierr.CodeConflict, "系统盘不可读取或正被占用", err)
	}
	var meta qemuImgOutput
	if err = json.Unmarshal(out, &meta); err != nil {
		return FileInfo{}, err
	}
	if strings.ToUpper(meta.Format) != "QCOW2" || meta.BackingFilename != "" || meta.FormatSpecific.Data.DataFile != "" || meta.VirtualSizeBytes <= 0 {
		return FileInfo{}, apierr.New(apierr.CodeInvalidArgument, "仅可直接使用独立 QCOW2 系统盘，不支持 backing/data-file 依赖", nil)
	}
	return FileInfo{Path: relative, Format: "QCOW2", SizeBytes: stat.Size(), VirtualSizeBytes: meta.VirtualSizeBytes}, nil
}
