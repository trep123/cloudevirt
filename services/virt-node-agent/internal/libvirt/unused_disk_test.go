package libvirt

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

func emptyVirsh(t *testing.T) *Client {
	t.Helper()
	p := filepath.Join(t.TempDir(), "virsh")
	if e := os.WriteFile(p, []byte("#!/bin/sh\nexit 0\n"), 0700); e != nil {
		t.Fatal(e)
	}
	return &Client{Binary: p, Timeout: 5 * time.Second}
}
func TestUnusedDiskDeletionAndReplay(t *testing.T) {
	c := emptyVirsh(t)
	root := t.TempDir()
	p := filepath.Join(root, "test.qcow2")
	os.WriteFile(p, []byte("test"), 0600)
	if e := c.RemoveUnusedDisk(context.Background(), root, "test.qcow2"); e != nil {
		t.Fatal(e)
	}
	if _, e := os.Stat(p); !os.IsNotExist(e) {
		t.Fatal("file retained")
	}
	if e := c.RemoveUnusedDisk(context.Background(), root, "test.qcow2"); e != nil {
		t.Fatal(e)
	}
}
func TestReferencedDiskNeverUnlinked(t *testing.T) {
	for _, source := range []string{"live", "inactive", "snapshot"} {
		t.Run(source, func(t *testing.T) {
			root := t.TempDir()
			target := filepath.Join(root, "test.qcow2")
			os.WriteFile(target, []byte("test"), 0600)
			fixture := filepath.Join(t.TempDir(), "source.xml")
			os.WriteFile(fixture, []byte(fmt.Sprintf(`<domain><devices><disk><source file="%s"/></disk></devices></domain>`, target)), 0600)
			script := fmt.Sprintf("#!/bin/sh\ncase \"$*\" in\n*'list --all --name'*) echo cv-other;;\n*'snapshot-list'*) echo snap1;;\n*'snapshot-dumpxml'*) %s;;\n*'--inactive'*) %s;;\n*'dumpxml'*) %s;;\nesac\n", xmlCommand(source == "snapshot", fixture), xmlCommand(source == "inactive", fixture), xmlCommand(source == "live", fixture))
			bin := filepath.Join(t.TempDir(), "virsh")
			os.WriteFile(bin, []byte(script), 0700)
			c := &Client{Binary: bin, Timeout: 5 * time.Second}
			if e := c.RemoveUnusedDisk(context.Background(), root, "test.qcow2"); e == nil {
				t.Fatal("reference ignored")
			}
			if _, e := os.Stat(target); e != nil {
				t.Fatal("referenced file removed")
			}
		})
	}
}
func xmlCommand(match bool, file string) string {
	if match {
		return fmt.Sprintf("cat %q", file)
	}
	return "echo '<domain/>'"
}
func TestBackingChainProtectsParent(t *testing.T) {
	if _, e := exec.LookPath("qemu-img"); e != nil {
		t.Skip("qemu-img unavailable")
	}
	root := t.TempDir()
	base := filepath.Join(root, "base.qcow2")
	child := filepath.Join(root, "child.qcow2")
	for _, args := range [][]string{{"create", "-f", "qcow2", base, "1M"}, {"create", "-f", "qcow2", "-F", "qcow2", "-b", base, child}} {
		if out, e := exec.Command("qemu-img", args...).CombinedOutput(); e != nil {
			t.Fatalf("%v %s", e, out)
		}
	}
	c := emptyVirsh(t)
	if e := c.RemoveUnusedDisk(context.Background(), root, "base.qcow2"); e == nil {
		t.Fatal("backing parent removed")
	}
	if e := c.RemoveUnusedDisk(context.Background(), root, "child.qcow2"); e != nil {
		t.Fatal(e)
	}
	if e := c.RemoveUnusedDisk(context.Background(), root, "base.qcow2"); e != nil {
		t.Fatal(e)
	}
}
func TestPoolDirectorySelectionAndTraversal(t *testing.T) {
	c := emptyVirsh(t)
	root := t.TempDir()
	target := filepath.Join(root, "nested", "chosen")
	if e := c.CreateDirectoryPoolAt(context.Background(), "cv-custom", root, target); e != nil {
		t.Fatal(e)
	}
	if f, e := os.Stat(target); e != nil || !f.IsDir() {
		t.Fatal("directory not created")
	}
	if e := c.CreateDirectoryPoolAt(context.Background(), "cv-custom", root, filepath.Join(root, "..", "outside")); e == nil {
		t.Fatal("path escape accepted")
	}
	outside := t.TempDir()
	if e := os.Symlink(outside, filepath.Join(root, "escape")); e != nil {
		t.Fatal(e)
	}
	if e := c.CreateDirectoryPoolAt(context.Background(), "cv-symlink", root, filepath.Join(root, "escape", "new")); e == nil {
		t.Fatal("symlink escape accepted")
	}
	if _, e := os.Stat(filepath.Join(outside, "new")); !os.IsNotExist(e) {
		t.Fatal("directory created outside root")
	}
}
