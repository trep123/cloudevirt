package httpapi

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/libvirt"
)

type poolRootOperator struct {
	fakeInfrastructure
	pools []libvirt.StoragePool
}

func (f *poolRootOperator) ListStoragePools(context.Context) ([]libvirt.StoragePool, error) {
	return f.pools, nil
}

func TestDiskRootForPoolHonorsApprovedRoots(t *testing.T) {
	base := t.TempDir()
	root := filepath.Join(base, "approved")
	inside := filepath.Join(root, "tenant-a")
	outside := filepath.Join(base, "outside")
	for _, path := range []string{inside, outside} {
		if err := os.MkdirAll(path, 0700); err != nil {
			t.Fatal(err)
		}
	}
	operator := &poolRootOperator{pools: []libvirt.StoragePool{{
		Name: "cv-tenant", Type: "dir", Active: true,
	}}}
	operator.pools[0].Target.Path = inside
	deps := testDependencies()
	deps.Virtualizer = operator
	deps.StorageRoots = []string{root}
	path, err := diskRootForPool(context.Background(), deps, "cv-tenant")
	if err != nil || path != inside {
		t.Fatalf("approved root rejected: %q, %v", path, err)
	}
	imageRoot, err := imageRootForPool(context.Background(), deps, "cv-tenant")
	if err != nil || imageRoot != inside { t.Fatalf("image root ignored pool: %q, %v", imageRoot, err) }
	legacy, err := imageRootForPool(context.Background(), deps, "")
	if err != nil || legacy != deps.ImageDir { t.Fatal("legacy image root changed") }
	operator.pools[0].Target.Path = outside
	if _, err := diskRootForPool(context.Background(), deps, "cv-tenant"); err == nil {
		t.Fatal("unapproved path accepted")
	}
	link := filepath.Join(root, "linked")
	if err := os.Symlink(outside, link); err != nil {
		t.Fatal(err)
	}
	operator.pools[0].Target.Path = link
	if _, err := diskRootForPool(context.Background(), deps, "cv-tenant"); err == nil {
		t.Fatal("symlink escape accepted")
	}
	operator.pools[0].Target.Path = inside
	operator.pools[0].Active = false
	if _, err := diskRootForPool(context.Background(), deps, "cv-tenant"); err == nil {
		t.Fatal("inactive pool accepted")
	}
}
