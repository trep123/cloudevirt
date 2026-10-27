package libvirt

import (
	"context"
	"encoding/xml"
	"testing"
)

func TestInfrastructureRejectsUnsafeNamesBeforeCommandExecution(t *testing.T) {
	client := &Client{Binary: "must-not-execute"}
	for _, name := range []string{"../../etc", "--help", "pool", "cv-../x"} {
		if err := client.CreateDirectoryPool(context.Background(), name, t.TempDir()); err == nil {
			t.Fatalf("unsafe storage pool name accepted: %s", name)
		}
	}
	if err := client.SnapshotAction(context.Background(), "production-domain", "cv-snap", "revert", t.TempDir()); err == nil {
		t.Fatal("unmanaged domain accepted")
	}
}

func TestPoolXMLCapacityAndSnapshotParentParsing(t *testing.T) {
	var pool StoragePool
	if err := xml.Unmarshal([]byte(`<pool type="dir"><name>cv-pool</name><capacity unit="bytes">1024</capacity><allocation unit="bytes">512</allocation><available unit="bytes">512</available><target><path>/managed/cv-pool</path></target></pool>`), &pool); err != nil {
		t.Fatal(err)
	}
	if pool.Type != "dir" || pool.Capacity != 1024 || pool.Allocation != 512 || pool.Target.Path != "/managed/cv-pool" {
		t.Fatalf("incorrect pool parse: %+v", pool)
	}
	var snapshot Snapshot
	if err := xml.Unmarshal([]byte(`<domainsnapshot><name>cv-snap</name><state>shutoff</state><creationTime>123</creationTime><parent><name>cv-parent</name></parent><disks><disk name="vda" snapshot="internal"/></disks></domainsnapshot>`), &snapshot); err != nil {
		t.Fatal(err)
	}
	if snapshot.Parent != "cv-parent" || snapshot.CreatedAt != 123 || len(snapshot.Disks) != 1 || snapshot.Disks[0].Snapshot != "internal" {
		t.Fatalf("incorrect snapshot parse: %+v", snapshot)
	}
}
