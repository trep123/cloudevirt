package config

import (
	"strings"
	"testing"
)

// TestLoadRejectsWeakToken 校验令牌缺失或过短时启动失败。
func TestLoadRejectsWeakToken(t *testing.T) {
	cases := []struct {
		name  string
		token string
	}{
		{name: "TokenMissing", token: ""},
		{name: "TokenTooShort", token: strings.Repeat("a", MinTokenLength-1)},
	}

	for _, item := range cases {
		t.Run(item.name, func(t *testing.T) {
			t.Setenv("CLOUDVIRT_AGENT_TOKEN", item.token)
			if _, err := Load(); err == nil {
				t.Fatalf("令牌长度为 %d 时应返回错误", len(item.token))
			}
		})
	}
}

// TestLoadDefaults 校验合法配置下默认值与解析结果正确。
func TestLoadDefaults(t *testing.T) {
	t.Setenv("CLOUDVIRT_AGENT_TOKEN", strings.Repeat("b", MinTokenLength))

	cfg, err := Load()
	if err != nil {
		t.Fatalf("合法配置不应返回错误: %v", err)
	}
	if cfg.Listen != defaultListen {
		t.Errorf("监听地址默认值错误: got=%q want=%q", cfg.Listen, defaultListen)
	}
	if cfg.MaxRequestSeconds != defaultMaxRequestSeconds {
		t.Errorf("请求超时默认值错误: got=%d want=%d", cfg.MaxRequestSeconds, defaultMaxRequestSeconds)
	}
	if cfg.ImageDir != defaultImageDir || cfg.DiskDir != defaultDiskDir {
		t.Errorf("目录默认值错误: image=%q disk=%q", cfg.ImageDir, cfg.DiskDir)
	}
	if cfg.AllowDestructive {
		t.Error("未设置时 AllowDestructive 应为 false")
	}
}

// TestLoadRejectsInvalidTimeout 校验非法超时配置被拒绝。
func TestLoadRejectsInvalidTimeout(t *testing.T) {
	t.Setenv("CLOUDVIRT_AGENT_TOKEN", strings.Repeat("c", MinTokenLength))
	t.Setenv("CLOUDVIRT_MAX_REQUEST_SECONDS", "not-a-number")

	if _, err := Load(); err == nil {
		t.Fatal("超时值非数字时应返回错误")
	}
}
