package storage

import (
	"os"
	"path/filepath"
	"testing"
)

func TestUploadOffsetReplayAndPublication(t *testing.T) {
	root, id := t.TempDir(), "0123456789abcdef0123456789abcdef"
	data := []byte("image-content")
	first, err := WriteImageChunk(root, id, ".qcow2", 0, int64(len(data)), data[:5])
	if err != nil || first.Offset != 5 {
		t.Fatalf("first chunk: %+v %v", first, err)
	}
	repeat, err := WriteImageChunk(root, id, ".qcow2", 0, int64(len(data)), data[:5])
	if err != nil || repeat.Offset != 5 {
		t.Fatalf("replayed chunk: %+v %v", repeat, err)
	}
	if _, err := WriteImageChunk(root, id, ".qcow2", 0, int64(len(data)), []byte("wrong")); err == nil {
		t.Fatal("different replay accepted")
	}
	if _, err := PublishImageUpload(root, id, ".qcow2", int64(len(data))); err == nil {
		t.Fatal("incomplete image published")
	}
	if _, err := WriteImageChunk(root, id, ".qcow2", 5, int64(len(data)), data[5:]); err != nil {
		t.Fatal(err)
	}
	published, err := PublishImageUpload(root, id, ".qcow2", int64(len(data)))
	if err != nil || !published.Published {
		t.Fatalf("publish: %+v %v", published, err)
	}
	actual, err := os.ReadFile(filepath.Join(root, published.RelativePath))
	if err != nil || string(actual) != string(data) {
		t.Fatalf("content mismatch: %v", err)
	}
	if _, err := PublishImageUpload(root, id, ".qcow2", int64(len(data))); err != nil {
		t.Fatalf("publish retry failed: %v", err)
	}
	if err := CancelImageUpload(root, id, ".qcow2"); err == nil {
		t.Fatal("published image removed through cancellation")
	}
	if _, err := WriteImageChunk(root, id, ".qcow2", 0, int64(len(data)), data); err == nil {
		t.Fatal("published image overwritten")
	}
}

func TestUploadRejectsTraversalAndOversizeBeforeCreatingFiles(t *testing.T) {
	root := t.TempDir()
	for _, id := range []string{"../etc/passwd", "../../", "bad-id", ""} {
		if _, err := WriteImageChunk(root, id, ".qcow2", 0, 4, []byte("data")); err == nil {
			t.Fatalf("unsafe id accepted: %s", id)
		}
	}
	id := "0123456789abcdef0123456789abcdef"
	if _, err := WriteImageChunk(root, id, ".qcow2", 0, MaxImageBytes+1, []byte("data")); err == nil {
		t.Fatal("oversize accepted")
	}
	if _, err := WriteImageChunk(root, id, ".qcow2", 0, UploadChunkBytes+1, make([]byte, UploadChunkBytes+1)); err == nil {
		t.Fatal("oversize chunk accepted")
	}
	if _, err := WriteImageChunk(root, id, ".qcow2", -1, 4, []byte("data")); err == nil {
		t.Fatal("negative offset accepted")
	}
	entries, err := os.ReadDir(root)
	if err != nil || len(entries) != 0 {
		t.Fatalf("invalid input created files: %v", err)
	}
}

func TestUploadRejectsSymlinkAndCancellationCleansOnlyPartial(t *testing.T) {
	root, id := t.TempDir(), "0123456789abcdef0123456789abcdef"
	other := filepath.Join(root, "preserve.qcow2")
	if err := os.WriteFile(other, []byte("keep"), 0o600); err != nil {
		t.Fatal(err)
	}
	partial := filepath.Join(root, ".upload-"+id+".part")
	if err := os.Symlink(other, partial); err != nil {
		t.Fatal(err)
	}
	if _, err := WriteImageChunk(root, id, ".qcow2", 0, 4, []byte("data")); err == nil {
		t.Fatal("symlink accepted")
	}
	if err := os.Remove(partial); err != nil {
		t.Fatal(err)
	}
	if _, err := WriteImageChunk(root, id, ".qcow2", 0, 8, []byte("data")); err != nil {
		t.Fatal(err)
	}
	if err := CancelImageUpload(root, id, ".qcow2"); err != nil {
		t.Fatal(err)
	}
	content, err := os.ReadFile(other)
	if err != nil || string(content) != "keep" {
		t.Fatal("unrelated file changed")
	}
	if _, err := os.Stat(partial); !os.IsNotExist(err) {
		t.Fatal("partial file not removed")
	}
}
