package storage

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

// createQcow2 用 qemu-img 生成一个具备虚拟容量的 qcow2 文件。
func createQcow2(t *testing.T, path string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	out, err := exec.Command("qemu-img", "create", "-f", "qcow2", path, "2G").CombinedOutput()
	if err != nil {
		t.Fatalf("qemu-img create 失败: %v %s", err, out)
	}
}

// TestListDiskFilesWalksNestedRelativePaths 校验递归遍历返回相对路径，
// 使固定同名 system.qcow2 能按 vms/user-*/<uuid>/ 精确区分。
func TestListDiskFilesWalksNestedRelativePaths(t *testing.T) {
	if _, err := exec.LookPath("qemu-img"); err != nil {
		t.Skip("requires qemu-img")
	}
	root := t.TempDir()
	first := "vms/user-1/aaaa/system.qcow2"
	second := "vms/user-1/bbbb/system.qcow2"
	createQcow2(t, filepath.Join(root, first))
	createQcow2(t, filepath.Join(root, second))
	// 隐藏目录与符号链接都应被跳过，避免越界或重复计数。
	createQcow2(t, filepath.Join(root, ".hidden/skip.qcow2"))
	if err := os.Symlink(filepath.Join(root, first), filepath.Join(root, "link.qcow2")); err != nil {
		t.Fatal(err)
	}

	files, err := ListDiskFiles(context.Background(), root)
	if err != nil {
		t.Fatalf("列目录失败: %v", err)
	}

	byRel := map[string]DiskFile{}
	for _, file := range files {
		byRel[file.RelativePath] = file
	}
	if len(files) != 2 {
		t.Fatalf("应只返回两个嵌套磁盘文件: %+v", byRel)
	}
	for _, rel := range []string{first, second} {
		file, ok := byRel[rel]
		if !ok {
			t.Fatalf("缺少相对路径 %q: %+v", rel, byRel)
		}
		if file.Name != "system.qcow2" {
			t.Errorf("basename 错误: %q", file.Name)
		}
		if file.VirtualSizeBytes <= 0 {
			t.Errorf("虚拟容量应大于 0: %+v", file)
		}
	}
}

// TestListDiskFilesMissingRoot 校验目录不存在时返回稳定错误。
func TestListDiskFilesMissingRoot(t *testing.T) {
	if _, err := ListDiskFiles(context.Background(), filepath.Join(t.TempDir(), "nope")); err == nil {
		t.Fatal("目录不存在应返回错误")
	}
}
