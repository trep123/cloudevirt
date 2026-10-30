package libvirt

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestSSHTargetsUseBoundUnexpiredLeasesOnly(t *testing.T) {
	root := t.TempDir()
	binary := filepath.Join(root, "virsh")
	script := `#!/bin/sh
case "$3" in
domstate) echo running;;
domiflist) printf 'Interface Type Source Model MAC\nvnet0 network default virtio 52:54:00:11:22:33\n';;
domifaddr) printf 'Name MAC Protocol Address\nvnet0 52:54:00:11:22:33 ipv4 192.0.2.50/24\nvnet1 52:54:00:aa:bb:cc ipv4 192.0.2.99/24\n';;
*) exit 1;;
esac
`
	if err := os.WriteFile(binary, []byte(script), 0700); err != nil {
		t.Fatal(err)
	}
	leases := filepath.Join(root, "leases")
	if err := os.WriteFile(leases, []byte("0 52:54:00:11:22:33 192.0.2.51 vm *\n1 52:54:00:11:22:33 192.0.2.52 expired *\n0 52:54:00:aa:bb:cc 192.0.2.53 other *\n0 52:54:00:11:22:33 127.0.0.1 loopback *\n"), 0600); err != nil {
		t.Fatal(err)
	}
	client := &Client{Binary: binary, URI: "qemu:///system", Timeout: 5 * time.Second, LeaseFile: leases}
	addresses, err := client.DomainSSHTargets(context.Background(), "cv-test")
	if err != nil || len(addresses) != 2 || addresses[0] != "192.0.2.50" || addresses[1] != "192.0.2.51" {
		t.Fatalf("unexpected SSH targets: %v %v", addresses, err)
	}
}
