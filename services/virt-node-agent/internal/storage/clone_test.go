package storage

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

func TestCloneIndependentImageAndRefusesOverwrite(t *testing.T) {
	if _, err := exec.LookPath("qemu-img"); err != nil {
		t.Skip("requires qemu-img")
	}
	root := t.TempDir()
	source := filepath.Join(root, "source.raw")
	data := make([]byte, 1024*1024)
	copy(data, []byte("cloudvirt-original-image"))
	if err := os.WriteFile(source, data, 0600); err != nil {
		t.Fatal(err)
	}
	info, err := Inspect(root, "source.raw")
	if err != nil {
		t.Fatal(err)
	}
	target := filepath.Join(root, "target.qcow2")
	if err := CloneImage(context.Background(), root, "source.raw", info.ChecksumSHA256, "RAW", target, 1); err != nil {
		t.Fatal(err)
	}
	format, size, err := DiskInfo(context.Background(), target)
	if err != nil || format != "QCOW2" || size != 1024*1024*1024 {
		t.Fatalf("bad clone %s %d %v", format, size, err)
	}
	after, err := Inspect(root, "source.raw")
	if err != nil || after.ChecksumSHA256 != info.ChecksumSHA256 {
		t.Fatal("source changed", err)
	}
	if err := CloneImage(context.Background(), root, "source.raw", info.ChecksumSHA256, "RAW", target, 2); err == nil {
		t.Fatal("overwrote existing disk")
	}
	if err := CloneImage(context.Background(), root, "source.raw", "0000000000000000000000000000000000000000000000000000000000000000", "RAW", filepath.Join(root, "bad.qcow2"), 1); err == nil {
		t.Fatal("accepted changed image")
	}
}

func TestCloneRetainedDiskIsIndependent(t *testing.T) {
	if _, err := exec.LookPath("qemu-img"); err != nil {
		t.Skip("requires qemu-img")
	}
	root := t.TempDir()
	source := filepath.Join(root, "old.qcow2")
	if out, err := exec.Command("qemu-img", "create", "-f", "qcow2", source, "1G").CombinedOutput(); err != nil {
		t.Fatalf("%s: %v", out, err)
	}
	before, err := Inspect(root, "old.qcow2")
	if err != nil {
		t.Fatal(err)
	}
	target := filepath.Join(root, "new.qcow2")
	if err := CloneRetainedDisk(context.Background(), root, "old.qcow2", target, 2); err != nil {
		t.Fatal(err)
	}
	after, err := Inspect(root, "old.qcow2")
	if err != nil || after.ChecksumSHA256 != before.ChecksumSHA256 {
		t.Fatal("source changed", err)
	}
	if _, err := Inspect(root, "new.qcow2"); err != nil {
		t.Fatal("clone not standalone", err)
	}
	if err := CloneRetainedDisk(context.Background(), root, "../escape", target, 2); err == nil {
		t.Fatal("accepted traversal")
	}
	if err := CloneRetainedDisk(context.Background(), root, "old.qcow2", target, 2); err == nil {
		t.Fatal("accepted overwrite")
	}
}
