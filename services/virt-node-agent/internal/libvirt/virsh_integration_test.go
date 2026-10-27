//go:build integration

package libvirt

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// TestListDomainsAgainstRealLibvirt 需要本机 virsh 与 qemu:///system 可用：
// go test -tags integration ./internal/libvirt
func TestListDomainsAgainstRealLibvirt(t *testing.T) {
	if _, err := exec.LookPath(DefaultBinary); err != nil {
		t.Skip("未安装 virsh，跳过集成测试")
	}

	name := "cloudvirt-agent-it"
	xml := `<domain type="kvm">
  <name>` + name + `</name>
  <memory unit="MiB">128</memory>
  <vcpu>1</vcpu>
  <os><type arch="x86_64" machine="q35">hvm</type></os>
</domain>`
	path := filepath.Join(t.TempDir(), "domain.xml")
	if err := os.WriteFile(path, []byte(xml), 0o600); err != nil {
		t.Fatalf("写入域定义失败: %v", err)
	}

	ctx := context.Background()
	define := exec.CommandContext(ctx, DefaultBinary, "-c", DefaultURI, "define", path)
	if output, err := define.CombinedOutput(); err != nil {
		t.Fatalf("定义域失败: %v output=%s", err, strings.TrimSpace(string(output)))
	}
	t.Cleanup(func() {
		cleanup := exec.CommandContext(context.Background(), DefaultBinary, "-c", DefaultURI, "undefine", name)
		_ = cleanup.Run()
	})

	client := NewClient(20 * time.Second)
	domains, err := client.ListDomains(ctx)
	if err != nil {
		t.Fatalf("查询域列表失败: %v", err)
	}

	found := ""
	for _, domain := range domains {
		if domain.Name == name {
			found = domain.State
		}
	}
	if found == "" {
		t.Fatalf("域列表中未找到 %s: %+v", name, domains)
	}
	if found != StateShutoff && found != StateRunning {
		t.Errorf("状态应为已知值: got=%s", found)
	}
}
