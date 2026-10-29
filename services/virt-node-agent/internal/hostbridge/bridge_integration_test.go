package hostbridge

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

// Opt-in kernel validation. All links live in a new, disposable network namespace.
// A test-only sysfs fixture represents its veth as a physical NIC; production never does this.
func TestKernelBridgeInIsolatedNamespace(t *testing.T) {
	if os.Getenv("CLOUDVIRT_BRIDGE_NETNS_TEST") != "1" {
		t.Skip("set CLOUDVIRT_BRIDGE_NETNS_TEST=1 as root for isolated kernel validation")
	}
	name := fmt.Sprintf("cvbr-check-%d", os.Getpid())
	command := func(args ...string) {
		t.Helper()
		if out, e := exec.Command("ip", args...).CombinedOutput(); e != nil {
			t.Fatalf("ip %v: %v: %s", args, e, out)
		}
	}
	command("netns", "add", name)
	defer func() {
		if out, e := exec.Command("ip", "netns", "delete", name).CombinedOutput(); e != nil {
			t.Errorf("namespace cleanup: %v %s", e, out)
		}
	}()
	command("netns", "exec", name, "ip", "link", "add", "eth1", "type", "veth", "peer", "name", "ethpeer")
	root := t.TempDir()
	if e := os.MkdirAll(filepath.Join(root, "sys", "eth1", "device"), 0700); e != nil {
		t.Fatal(e)
	}
	m := &Manager{Dir: filepath.Join(root, "state"), Sysfs: filepath.Join(root, "sys"), Run: func(ctx context.Context, binary string, args ...string) ([]byte, error) {
		return run(ctx, "ip", append([]string{"netns", "exec", name, binary}, args...)...)
	}}
	s := Spec{Type: "BRIDGE", Bridge: "br-data", Uplink: "eth1"}
	if e := m.Create(context.Background(), s); e != nil {
		t.Fatal(e)
	}
	if e := m.Create(context.Background(), s); e != nil {
		t.Fatalf("replay: %v", e)
	}
	command("netns", "exec", name, "ip", "link", "set", "dev", "eth1", "nomaster")
	command("netns", "exec", name, "ip", "link", "delete", "dev", "br-data")
	m.Restore(context.Background())
	if e := m.verify(context.Background(), s); e != nil {
		t.Fatalf("restore: %v", e)
	}
}
