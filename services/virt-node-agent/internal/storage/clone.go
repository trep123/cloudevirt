package storage

import (
	"context"
	"fmt"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

// CloneImage publishes an independent image atomically. Never overwrite a prior disk.
func CloneImage(ctx context.Context, imageRoot, relative, checksum, format, target string, sizeGiB int) error {
	info, err := InspectContext(ctx, imageRoot, relative)
	if err != nil {
		return err
	}
	if len(checksum) != 64 || !strings.EqualFold(info.ChecksumSHA256, checksum) || !strings.EqualFold(info.Format, format) {
		return apierr.New(apierr.CodeConflict, "源镜像格式或摘要已变化，请重新登记", nil)
	}
	return cloneInspected(ctx, imageRoot, relative, info, target, sizeGiB)
}

// CloneRetainedDisk creates an independent copy without changing the retained source.
func CloneRetainedDisk(ctx context.Context, root, relative, target string, sizeGiB int) error {
	info, err := InspectContext(ctx, root, relative)
	if err != nil {
		return err
	}
	return cloneInspected(ctx, root, relative, info, target, sizeGiB)
}

func cloneInspected(ctx context.Context, imageRoot, relative string, info FileInfo, target string, sizeGiB int) error {
	format := info.Format
	if info.Format != "QCOW2" && info.Format != "RAW" {
		return apierr.New(apierr.CodeInvalidArgument, "仅支持独立 QCOW2/RAW 系统镜像", nil)
	}
	if sizeGiB <= 0 || int64(sizeGiB)*1024*1024*1024 < info.VirtualSizeBytes {
		return apierr.New(apierr.CodeInvalidArgument, "系统盘不能小于镜像虚拟容量", nil)
	}
	if _, err := os.Lstat(target); !os.IsNotExist(err) {
		return apierr.New(apierr.CodeConflict, "目标磁盘已存在或不可访问；先核对原任务", err)
	}
	source, err := SafePath(imageRoot, relative)
	if err != nil {
		return err
	}
	temporary, err := os.CreateTemp(filepath.Dir(target), ".clone-*.qcow2")
	if err != nil {
		return err
	}
	name := temporary.Name()
	temporary.Close()
	defer os.Remove(name)
	commandCtx, cancel := context.WithTimeout(ctx, 30*time.Minute)
	defer cancel()
	if err := exec.CommandContext(commandCtx, "qemu-img", "convert", "-f", strings.ToLower(format), "-O", "qcow2", "--", source, name).Run(); err != nil {
		return apierr.New(apierr.CodeOperationFailed, "独立复制系统镜像失败", err)
	}
	if err := exec.CommandContext(commandCtx, "qemu-img", "resize", "-f", "qcow2", "--", name, fmt.Sprintf("%dG", sizeGiB)).Run(); err != nil {
		return apierr.New(apierr.CodeOperationFailed, "系统盘扩容失败", err)
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
		return apierr.New(apierr.CodeConflict, "磁盘发布失败，目标可能已存在", err)
	}
	return nil
}
