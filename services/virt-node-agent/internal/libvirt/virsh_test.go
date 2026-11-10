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

// writeFakeVirsh 写入一个按参数回显机器可读名称列表的假 virsh。
func writeFakeVirsh(t *testing.T, body string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "virsh")
	if err := os.WriteFile(path, []byte("#!/bin/sh\n"+body+"\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	return path
}

// TestExistsUsesMachineReadableListing 校验存在性判断只依赖 `--name` 枚举，
// 不解析会随 libvirt 版本或语言环境变化的错误文本。
func TestExistsUsesMachineReadableListing(t *testing.T) {
	client := NewClient(0)
	client.Binary = writeFakeVirsh(t, `case "$*" in
*net-list*) printf 'default\nbr0\n' ;;
*list*) printf 'cv-alpha\ncv-beta\n' ;;
*) exit 99 ;;
esac`)

	ctx := t.Context()
	if ok, err := client.DomainExists(ctx, "cv-alpha"); err != nil || !ok {
		t.Errorf("已定义域应存在: ok=%v err=%v", ok, err)
	}
	if ok, err := client.DomainExists(ctx, "cv-gamma"); err != nil || ok {
		t.Errorf("未定义域不应存在: ok=%v err=%v", ok, err)
	}
	if ok, err := client.NetworkExists(ctx, "default"); err != nil || !ok {
		t.Errorf("已定义网络应存在: ok=%v err=%v", ok, err)
	}
	if ok, err := client.NetworkExists(ctx, "missing"); err != nil || ok {
		t.Errorf("未定义网络不应存在: ok=%v err=%v", ok, err)
	}
}

// TestExistsRejectsEmptyName 校验空名称被拒绝，避免误匹配空行。
func TestExistsRejectsEmptyName(t *testing.T) {
	client := NewClient(0)
	client.Binary = writeFakeVirsh(t, `printf 'cv-alpha\n\n'`)
	ctx := t.Context()
	if _, err := client.DomainExists(ctx, "  "); err == nil {
		t.Error("空域名应返回错误")
	}
	if _, err := client.NetworkExists(ctx, ""); err == nil {
		t.Error("空网络名应返回错误")
	}
}

// TestExistsPropagatesCommandFailure 校验 virsh 自身失败时返回错误，
// 而不是被误判为“不存在”。
func TestExistsPropagatesCommandFailure(t *testing.T) {
	client := NewClient(0)
	client.Binary = writeFakeVirsh(t, `echo 'connection refused' >&2; exit 1`)
	ctx := t.Context()
	if _, err := client.DomainExists(ctx, "cv-alpha"); err == nil {
		t.Error("命令失败应返回错误")
	}
}
