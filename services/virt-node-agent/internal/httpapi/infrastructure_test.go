package httpapi

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/libvirt"
)

type fakeInfrastructure struct {
	fakeOperator
	changes int
}

func (f *fakeInfrastructure) ListStoragePools(context.Context) ([]libvirt.StoragePool, error) {
	return []libvirt.StoragePool{}, nil
}
func (f *fakeInfrastructure) CreateDirectoryPool(context.Context, string, string) error {
	f.changes++
	return nil
}
func (f *fakeInfrastructure) ListSnapshots(context.Context, string) ([]libvirt.Snapshot, error) {
	return []libvirt.Snapshot{}, nil
}
func (f *fakeInfrastructure) SnapshotAction(context.Context, string, string, string, string) error {
	f.changes++
	return nil
}

func TestInfrastructureRequiresToken(t *testing.T) {
	deps := testDependencies()
	for _, path := range []string{"/api/v1/storage-pools", "/api/v1/domains/cv-test/snapshots"} {
		recorder := httptest.NewRecorder()
		NewRouter(deps).ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, path, nil))
		if recorder.Code != http.StatusUnauthorized {
			t.Fatalf("unprotected endpoint %s: %d", path, recorder.Code)
		}
	}
}

func TestSnapshotDestructiveGate(t *testing.T) {
	for _, action := range []string{"revert", "delete"} {
		deps := testDependencies()
		fake := &fakeInfrastructure{}
		deps.Virtualizer = fake
		request := httptest.NewRequest(http.MethodPost, "/api/v1/domains/cv-test/snapshots", strings.NewReader(`{"name":"cv-snapshot","action":"`+action+`"}`))
		request.Header.Set("Authorization", "Bearer "+deps.Token)
		recorder := httptest.NewRecorder()
		NewRouter(deps).ServeHTTP(recorder, request)
		if recorder.Code < 400 || fake.changes != 0 {
			t.Fatalf("destructive gate bypassed for %s", action)
		}
	}
}

func TestInfrastructureRejectsArbitraryHostPath(t *testing.T) {
	deps := testDependencies()
	fake := &fakeInfrastructure{}
	deps.Virtualizer = fake
	request := httptest.NewRequest(http.MethodPost, "/api/v1/storage-pools", strings.NewReader(`{"name":"cv-pool","path":"/etc"}`))
	request.Header.Set("Authorization", "Bearer "+deps.Token)
	recorder := httptest.NewRecorder()
	NewRouter(deps).ServeHTTP(recorder, request)
	if recorder.Code != http.StatusBadRequest || fake.changes != 0 {
		t.Fatal("unexpected path accepted")
	}
}
