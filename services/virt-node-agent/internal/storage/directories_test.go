package storage

import (
	"os"
	"path/filepath"
	"testing"
)

func TestManagedDirectoriesIsolateUsersAndRejectAliases(t *testing.T) {
	root := t.TempDir()
	id := "12345678123412341234123456781234"
	one, err := EnsureManagedDirectory(root, "images/user-1/"+id)
	if err != nil { t.Fatal(err) }
	two, err := EnsureManagedDirectory(root, "images/user-2/"+id)
	if err != nil || one == two { t.Fatal("users share a directory") }
	if _, err := EnsureManagedDirectory(root, "../escape"); err == nil { t.Fatal("accepted traversal") }
	if err := os.Symlink(filepath.Join(root, "images/user-1"), filepath.Join(root, "images/user-3")); err != nil { t.Fatal(err) }
	if _, err := EnsureManagedDirectory(root, "images/user-3/"+id); err == nil { t.Fatal("accepted user directory alias") }
	progress, err := WriteImageChunk(one, id, ".iso", 0, 4, []byte("data"))
	if err != nil || progress.Offset != 4 { t.Fatalf("nested upload failed: %v", err) }
	if _, err := os.Stat(filepath.Join(root, "upload-"+id+".iso")); !os.IsNotExist(err) { t.Fatal("upload written to pool root") }
	if err := CancelImageUpload(one, id, ".iso"); err != nil { t.Fatal(err) }
}
