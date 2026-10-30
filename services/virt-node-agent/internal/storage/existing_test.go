package storage

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

func TestExistingDiskInspectionNeverChangesSource(t *testing.T) {
	if _, err := exec.LookPath("qemu-img"); err != nil {
		t.Skip("qemu-img required")
	}
	root := t.TempDir()
	path := filepath.Join(root, "installed.qcow2")
	if err := exec.Command("qemu-img", "create", "-f", "qcow2", path, "1G").Run(); err != nil {
		t.Fatal(err)
	}
	before, _ := os.ReadFile(path)
	info, err := InspectExistingDisk(context.Background(), root, "installed.qcow2")
	if err != nil || info.VirtualSizeBytes != 1024*1024*1024 {
		t.Fatal(info, err)
	}
	after, _ := os.ReadFile(path)
	if string(before) != string(after) {
		t.Fatal("source modified")
	}
	if _, err := InspectExistingDisk(context.Background(), root, "../escape.qcow2"); err == nil {
		t.Fatal("accepted traversal")
	}
	child := filepath.Join(root, "dependent.qcow2")
	if err := exec.Command("qemu-img", "create", "-f", "qcow2", "-F", "qcow2", "-b", path, child).Run(); err != nil {
		t.Fatal(err)
	}
	if _, err := InspectExistingDisk(context.Background(), root, "dependent.qcow2"); err == nil {
		t.Fatal("accepted external backing")
	}
}
