package libvirt

import (
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
