package libvirt

import (
	"os"
	"path/filepath"
	"testing"
)

// TestNormalizeState 校验 virsh 输出映射为平台状态。
func TestNormalizeState(t *testing.T) {
	cases := map[string]string{
		"running":      StateRunning,
		"idle":         StateRunning,
		"shut off":     StateShutoff,
		"shutoff":      StateShutoff,
		"paused":       StatePaused,
		"crashed":      StateCrashed,
		"  RUNNING \n": StateRunning,
		"weird-state":  StateUnknown,
		"":             StateUnknown,
	}
	for raw, expected := range cases {
		t.Run(raw, func(t *testing.T) {
			if got := NormalizeState(raw); got != expected {
				t.Errorf("状态映射错误: raw=%q got=%s want=%s", raw, got, expected)
			}
		})
	}
}

// TestDomainStateRejectsEmptyName 校验空域名被拒绝，避免拼接空参数。
func TestDomainStateRejectsEmptyName(t *testing.T) {
	client := NewClient(0)
	if _, err := client.DomainState(t.Context(), "   "); err == nil {
		t.Fatal("空域名应返回错误")
	}
}

// TestParseDomainAddresses 校验 domifaddr 输出解析。
func TestParseDomainAddresses(t *testing.T) {
	output := " Name       MAC address          Protocol     Address\n" +
		"-------------------------------------------------------------------------------\n" +
		" vnet0      52:54:00:aa:bb:cc    ipv4         192.168.122.10/24\n" +
		" vnet0      52:54:00:aa:bb:cc    ipv6         fd00::10/64\n"
	addresses := parseDomainAddresses(output)
	if len(addresses) != 2 {
		t.Fatalf("地址数量错误: %d", len(addresses))
	}
	if addresses[0].Address != "192.168.122.10" || addresses[0].Prefix != "24" {
		t.Errorf("IPv4 解析错误: %+v", addresses[0])
	}
	if addresses[1].Protocol != "ipv6" || addresses[1].Address != "fd00::10" {
		t.Errorf("IPv6 解析错误: %+v", addresses[1])
	}
}

// TestParseDHCPLeases 校验 dnsmasq 租约解析。
func TestParseDHCPLeases(t *testing.T) {
	path := filepath.Join(t.TempDir(), "leases")
	content := "1793153280 32:26:7a:a7:bd:03 192.168.150.105 * 01:32:26:7a:a7:bd:03\n"
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
	leases := parseDHCPLeases(path)
	if leases["32:26:7a:a7:bd:03"] != "192.168.150.105" {
		t.Fatalf("租约解析错误: %+v", leases)
	}
}

// TestNewClientDefaults 校验默认客户端参数。
func TestNewClientDefaults(t *testing.T) {
	client := NewClient(0)
	if client.Binary != DefaultBinary || client.URI != DefaultURI {
		t.Errorf("默认参数错误: %+v", client)
	}
	if client.Timeout <= 0 {
		t.Errorf("超时必须为正值: %v", client.Timeout)
	}
}
