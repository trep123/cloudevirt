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
		message := "系统盘检查失败，请查看节点 Agent 日志"
		if failure, ok := err.(*exec.ExitError); ok {
			detail := strings.ToLower(string(failure.Stderr))
			if strings.Contains(detail, "permission denied") || strings.Contains(detail, "operation not permitted") {
				message = "节点 Agent 无权读取系统盘，请检查文件读取权限及上级目录穿越权限（root 可读取不代表 Agent 可读取）"
			} else if strings.Contains(detail, "lock") || strings.Contains(detail, "another process") {
				message = "系统盘被其他进程锁定，请先关闭使用该磁盘的虚拟机；禁止强制共享可写系统盘"
			}
		} else if _, ok := err.(*exec.Error); ok {
			message = "节点无法执行 qemu-img，请检查 qemu-utils 安装"
		}
		return FileInfo{}, apierr.New(apierr.CodeConflict, message, err)
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
