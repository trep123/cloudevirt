package storage

import (
	"os"
	"path/filepath"
	"testing"
)

// TestSafePathRejectsTraversal 校验目录穿越被拒绝。
func TestSafePathRejectsTraversal(t *testing.T) {
	root := t.TempDir()
	cases := []string{
		"../outside.qcow2",
		"nested/../../outside.qcow2",
		"/etc/passwd",
		"",
		"   ",
	}
	for _, relative := range cases {
		t.Run(relative, func(t *testing.T) {
			if _, err := SafePath(root, relative); err == nil {
				t.Errorf("应拒绝路径: %q", relative)
			}
		})
	}
}

// TestSafePathAcceptsNestedFile 校验合法相对路径可通过。
func TestSafePathAcceptsNestedFile(t *testing.T) {
	root := t.TempDir()
	target := filepath.Join(root, "nested", "disk.qcow2")
	if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
		t.Fatalf("创建目录失败: %v", err)
	}
	if err := os.WriteFile(target, []byte("x"), 0o600); err != nil {
		t.Fatalf("写入文件失败: %v", err)
	}

	resolved, err := SafePath(root, "nested/disk.qcow2")
	if err != nil {
		t.Fatalf("合法路径不应被拒绝: %v", err)
	}
	if resolved != target {
		t.Errorf("解析结果错误: got=%s want=%s", resolved, target)
	}
}

// TestSafePathRejectsSymlinkEscape 校验符号链接越界被拒绝。
func TestSafePathRejectsSymlinkEscape(t *testing.T) {
	root := t.TempDir()
	outside := filepath.Join(t.TempDir(), "secret.qcow2")
	if err := os.WriteFile(outside, []byte("secret"), 0o600); err != nil {
		t.Fatalf("写入文件失败: %v", err)
	}
	if err := os.Symlink(outside, filepath.Join(root, "link.qcow2")); err != nil {
		t.Fatalf("创建链接失败: %v", err)
	}

	if _, err := SafePath(root, "link.qcow2"); err == nil {
		t.Error("指向外部的符号链接应被拒绝")
	}
}

// TestInspectRequiresExistingFile 校验不存在的文件返回 NOT_FOUND。
func TestInspectRequiresExistingFile(t *testing.T) {
	root := t.TempDir()
	if _, err := Inspect(root, "missing.qcow2"); err == nil {
		t.Error("不存在的文件应返回错误")
	}
}

// TestChecksumAndSize 校验流式校验和与大小统计。
func TestChecksumAndSize(t *testing.T) {
	path := filepath.Join(t.TempDir(), "sample.img")
	content := []byte("cloudvirt-sample-content")
	if err := os.WriteFile(path, content, 0o600); err != nil {
		t.Fatalf("写入文件失败: %v", err)
	}

	checksum, size, err := checksumAndSize(path)
	if err != nil {
		t.Fatalf("计算不应失败: %v", err)
	}
	if size != int64(len(content)) {
		t.Errorf("大小错误: got=%d want=%d", size, len(content))
	}
	if len(checksum) != 64 {
		t.Errorf("校验和长度错误: %d", len(checksum))
	}
}

// TestRemoveDeletesFileInsideRoot 校验删除仅限根目录内。
func TestRemoveDeletesFileInsideRoot(t *testing.T) {
	root := t.TempDir()
	target := filepath.Join(root, "old.qcow2")
	if err := os.WriteFile(target, []byte("x"), 0o600); err != nil {
		t.Fatalf("写入文件失败: %v", err)
	}

	if err := Remove(root, "old.qcow2"); err != nil {
		t.Fatalf("删除不应失败: %v", err)
	}
	if _, err := os.Stat(target); !os.IsNotExist(err) {
		t.Error("文件应已被删除")
	}
	if err := Remove(root, "../outside.qcow2"); err == nil {
		t.Error("删除越界路径应失败")
	}
}
