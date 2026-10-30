package libvirt

import (
	"context"
	"fmt"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/domainxml"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestHotNICVerifiesBothPlanesAndRepairsPartialAttach(t *testing.T) {
	root := t.TempDir()
	base := `<domain><uuid>hot-test</uuid><vcpu>1</vcpu><memory unit="MiB">128</memory><devices></devices></domain>`
	for _, name := range []string{"persistent.xml", "live.xml"} {
		if err := os.WriteFile(filepath.Join(root, name), []byte(base), 0600); err != nil {
			t.Fatal(err)
		}
	}
	script := `#!/usr/bin/env python3
import sys,pathlib
root=pathlib.Path(__file__).parent
args=sys.argv[3:]
if args[0]=='domstate': print('running')
elif args[0]=='snapshot-list': pass
elif args[0]=='dumpxml': print((root/('persistent.xml' if '--inactive' in args else 'live.xml')).read_text())
elif args[0]=='attach-device':
 mode=args[3]
 with (root/'calls').open('a') as f:f.write(mode+'\n')
 if mode=='--live' and (root/'fail-live').exists():
  (root/'fail-live').unlink();sys.exit(1)
 path=root/('persistent.xml' if mode=='--config' else 'live.xml')
 path.write_text(path.read_text().replace('</devices>',pathlib.Path(args[2]).read_text()+'</devices>'))
else: sys.exit(2)
`
	binary := filepath.Join(root, "virsh")
	if err := os.WriteFile(binary, []byte(script), 0700); err != nil {
		t.Fatal(err)
	}
	os.WriteFile(filepath.Join(root, "fail-live"), []byte("1"), 0600)
	c := &Client{Binary: binary, Timeout: 5 * time.Second}
	change := HardwareChange{Live: true, Operation: "nic-add", UUID: "hot-test", MAC: "02:00:00:00:01:01", Model: "virtio", Network: domainxml.NetworkSpec{NetworkType: "LIBVIRT_NETWORK", Network: "default"}}
	if _, err := c.ChangeHardware(context.Background(), "vm-hot", root, change); err == nil {
		t.Fatal("partial failure incorrectly accepted")
	}
	for i := 0; i < 2; i++ {
		inventory, err := c.ChangeHardware(context.Background(), "vm-hot", root, change)
		if err != nil || len(inventory.NICs) != 1 {
			t.Fatal(inventory, err)
		}
	}
	calls, _ := os.ReadFile(filepath.Join(root, "calls"))
	if strings.Count(string(calls), "--config") != 1 || strings.Count(string(calls), "--live") != 2 {
		t.Fatal(fmt.Sprintf("unexpected retries %s", calls))
	}
	for _, name := range []string{"persistent.xml", "live.xml"} {
		raw, _ := os.ReadFile(filepath.Join(root, name))
		if strings.Count(string(raw), change.MAC) != 1 {
			t.Fatalf("duplicate or missing MAC in %s", name)
		}
	}
	change.Operation = "disk-add"
	if _, err := c.ChangeHardware(context.Background(), "vm-hot", root, change); err == nil {
		t.Fatal("accepted hot disk operation")
	}
}
