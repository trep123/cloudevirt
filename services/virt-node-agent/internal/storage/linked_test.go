package storage

import (
	"context"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

func TestLinkedClonesShareImmutableBaseAndIsolateWrites(t *testing.T) {
	if _, err := exec.LookPath("qemu-img"); err != nil {
		t.Skip("qemu-img required")
	}
	if _, err := exec.LookPath("qemu-io"); err != nil {
		t.Skip("qemu-io required")
	}
	root := t.TempDir()
	data := make([]byte, 1024*1024)
	copy(data, []byte("source-data"))
	source := filepath.Join(root, "original.raw")
	if err := os.WriteFile(source, data, 0600); err != nil {
		t.Fatal(err)
	}
	info, err := Inspect(root, "original.raw")
	if err != nil {
		t.Fatal(err)
	}
	a := filepath.Join(root, "a.qcow2")
	b := filepath.Join(root, "b.qcow2")
	for _, target := range []string{a, b} {
		if err := CloneLinked(context.Background(), root, "original.raw", info.ChecksumSHA256, "RAW", target, 1); err != nil {
			t.Fatal(err)
		}
	}
	chain := func(path string) string {
		out, err := exec.Command("qemu-img", "info", "--backing-chain", "--output=json", path).Output()
		if err != nil {
			t.Fatal(err)
		}
		var rows []struct {
			File string `json:"filename"`
		}
		if err := json.Unmarshal(out, &rows); err != nil || len(rows) != 2 {
			t.Fatalf("bad chain: %s %v", out, err)
		}
		return rows[1].File
	}
	base := chain(a)
	if base != chain(b) {
		t.Fatal("base not shared")
	}
	before, err := os.ReadFile(base)
	if err != nil {
		t.Fatal(err)
	}
	stat, _ := os.Stat(base)
	if stat.Mode().Perm()&0222 != 0 {
		t.Fatal("base is writable")
	}
	if out, err := exec.Command("qemu-io", "-f", "qcow2", "-c", "write -P 0x5a 0 4096", a).CombinedOutput(); err != nil {
		t.Fatalf("overlay write: %s %v", out, err)
	}
	after, _ := os.ReadFile(base)
	if string(before) != string(after) {
		t.Fatal("overlay changed base")
	}
	original, _ := os.ReadFile(source)
	if string(original) != string(data) {
		t.Fatal("overlay changed original")
	}
	if err := os.Remove(source); err != nil {
		t.Fatal(err)
	}
	if chain(a) != base || chain(b) != base {
		t.Fatal("clones depended on mutable source")
	}
	if err := CloneLinked(context.Background(), root, "b.qcow2", "", "", filepath.Join(root, "invalid.qcow2"), 1); err == nil {
		t.Fatal("accepted layered source")
	}
}
