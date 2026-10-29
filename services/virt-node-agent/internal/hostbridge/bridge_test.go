package hostbridge

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

type fakeHost struct {
	links  []link
	routes []route
	writes []string
	fail   string
}

func fakeManager(t *testing.T) (*Manager, *fakeHost) {
	t.Helper()
	root := t.TempDir()
	if e := os.MkdirAll(filepath.Join(root, "sys", "eth1", "device"), 0700); e != nil {
		t.Fatal(e)
	}
	f := &fakeHost{links: []link{{Name: "eth1", State: "DOWN"}}}
	m := &Manager{Dir: filepath.Join(root, "state"), Sysfs: filepath.Join(root, "sys")}
	m.Run = func(ctx context.Context, n string, args ...string) ([]byte, error) {
		cmd := n + " " + strings.Join(args, " ")
		if strings.Contains(cmd, "address show") {
			return json.Marshal(f.links)
		}
		if strings.Contains(cmd, "route show") {
			return json.Marshal(f.routes)
		}
		if strings.Contains(cmd, "port-to-br") {
			return []byte("br-data\n"), nil
		}
		if strings.HasSuffix(cmd, " show") {
			return []byte("ok"), nil
		}
		f.writes = append(f.writes, cmd)
		if f.fail != "" && strings.Contains(cmd, f.fail) {
			return nil, errors.New("injected failure")
		}
		if strings.Contains(cmd, "link add name") || strings.Contains(cmd, "add-br") {
			l := link{Name: "br-data"}
			l.Info.Kind = "bridge"
			if n == "ovs-vsctl" {
				l.Info.Kind = "openvswitch"
			}
			exists := false
			for _, v := range f.links {
				if v.Name == l.Name {
					exists = true
				}
			}
			if !exists {
				f.links = append(f.links, l)
			}
		}
		if strings.Contains(cmd, "master br-data") || strings.Contains(cmd, "add-port") {
			f.links[0].Master = "br-data"
			if n == "ovs-vsctl" {
				f.links[0].Master = "ovs-system"
			}
		}
		return []byte(""), nil
	}
	return m, f
}
func TestManagementAndOccupiedInterfacesNeverMutate(t *testing.T) {
	for _, c := range []struct {
		name string
		l    link
		rs   []route
	}{
		{name: "IPv4 management address", l: link{Name: "eth1", Addresses: []address{{Local: "192.168.100.100"}}}},
		{name: "IPv6 management address", l: link{Name: "eth1", Addresses: []address{{Local: "2001:db8::1"}}}},
		{name: "existing bridge", l: link{Name: "eth1", Master: "br-mgmt"}},
		{name: "bond slave", l: link{Name: "eth1", Master: "bond0"}},
		{name: "default route", l: link{Name: "eth1"}, rs: []route{{Dev: "eth1", Dst: "default"}}},
		{name: "static route", l: link{Name: "eth1"}, rs: []route{{Dev: "eth1", Dst: "10.0.0.0/8"}}},
		{name: "multipath route", l: link{Name: "eth1"}, rs: []route{{Dst: "default", Next: []route{{Dev: "eth1"}}}}},
	} {
		t.Run(c.name, func(t *testing.T) {
			m, f := fakeManager(t)
			f.links = []link{c.l}
			f.routes = c.rs
			ports, e := m.Inventory(context.Background())
			if e != nil || len(ports) != 1 || ports[0].Eligible {
				t.Fatalf("unsafe inventory: %+v %v", ports, e)
			}
			if e = m.Create(context.Background(), Spec{Type: "BRIDGE", Bridge: "br-data", Uplink: "eth1"}); e == nil {
				t.Fatal("unsafe bridge accepted")
			}
			if len(f.writes) != 0 {
				t.Fatalf("unsafe commands: %v", f.writes)
			}
			if _, e = os.Stat(m.Dir); !os.IsNotExist(e) {
				t.Fatal("unsafe intent was persisted")
			}
		})
	}
}
func TestLinuxAndOVSReplayAndRestore(t *testing.T) {
	for _, kind := range []string{"BRIDGE", "OVS"} {
		t.Run(kind, func(t *testing.T) {
			m, f := fakeManager(t)
			s := Spec{Type: kind, Bridge: "br-data", Uplink: "eth1"}
			if e := m.Create(context.Background(), s); e != nil {
				t.Fatal(e)
			}
			if e := m.Create(context.Background(), s); e != nil {
				t.Fatalf("idempotent replay: %v", e)
			}
			f.links = []link{{Name: "eth1"}}
			m.Restore(context.Background())
			if e := m.verify(context.Background(), s); e != nil {
				t.Fatalf("reboot restore: %v", e)
			}
		})
	}
}
func TestPartialFailureKeepsIntentAndCanRetry(t *testing.T) {
	m, f := fakeManager(t)
	f.fail = "dev eth1 up"
	s := Spec{Type: "BRIDGE", Bridge: "br-data", Uplink: "eth1"}
	if e := m.Create(context.Background(), s); e == nil {
		t.Fatal("failure ignored")
	}
	if _, e := os.Stat(m.file(s)); e != nil {
		t.Fatal("intent lost")
	}
	f.fail = ""
	if e := m.Create(context.Background(), s); e != nil {
		t.Fatal(e)
	}
}
func TestExistingUnmanagedBridgeCannotBeAdopted(t *testing.T) {
	m, f := fakeManager(t)
	l := link{Name: "br-data"}
	l.Info.Kind = "bridge"
	f.links = append(f.links, l)
	if e := m.Create(context.Background(), Spec{Type: "BRIDGE", Bridge: "br-data", Uplink: "eth1"}); e == nil || len(f.writes) > 0 {
		t.Fatal("external bridge adopted")
	}
}
func TestMalformedNameAndUnavailableInventoryFailClosed(t *testing.T) {
	m, f := fakeManager(t)
	if e := m.Create(context.Background(), Spec{Type: "BRIDGE", Bridge: "../escape", Uplink: "eth1"}); e == nil || len(f.writes) > 0 {
		t.Fatal("invalid name accepted")
	}
	m.Run = func(context.Context, string, ...string) ([]byte, error) {
		return nil, errors.New("netlink unavailable")
	}
	if _, e := m.Inventory(context.Background()); e == nil {
		t.Fatal("inventory silently succeeded")
	}
	if e := m.Create(context.Background(), Spec{Type: "BRIDGE", Bridge: "br-data", Uplink: "eth1"}); e == nil {
		t.Fatal("bridge created without safety inventory")
	}
}
func TestLinkLocalIPv6IsNotAManagementAddress(t *testing.T) {
	m, f := fakeManager(t)
	f.links[0].Addresses = []address{{Local: "fe80::1"}}
	f.routes = []route{{Dev: "eth1", Dst: "fe80::/64"}}
	if e := m.Create(context.Background(), Spec{Type: "BRIDGE", Bridge: "br-data", Uplink: "eth1"}); e != nil {
		t.Fatal(e)
	}
}

func TestExplicitProtectionAlsoBlocksAnUnconfiguredManagementNIC(t *testing.T) {
	m, f := fakeManager(t)
	m.Protected = map[string]bool{"eth1": true}
	ports, e := m.Inventory(context.Background())
	if e != nil || ports[0].Eligible {
		t.Fatal("protected interface advertised as free")
	}
	if e = m.Create(context.Background(), Spec{Type: "BRIDGE", Bridge: "br-data", Uplink: "eth1"}); e == nil || len(f.writes) != 0 {
		t.Fatal("protected interface mutated")
	}
}
