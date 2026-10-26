// Package config 负责节点 Agent 的配置读取与校验。
//
// 配置在进程启动时一次性加载并校验，任何必填项缺失或取值非法都会返回明确错误，
// 由调用方终止启动，避免运行到一半才发现配置错误。
package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

// 默认值与校验阈值。
const (
	defaultListen            = "127.0.0.1:9100"
	defaultImageDir          = "/var/lib/cloudvirt/images"
	defaultDiskDir           = "/var/lib/cloudvirt/disks"
	defaultMaxRequestSeconds = 120

	// MinTokenLength 是 Agent 共享令牌的最小长度，过短视为配置错误。
	MinTokenLength = 32
)

// Config 是节点 Agent 的运行时配置，加载完成后只读。
type Config struct {
	// Listen 是 HTTP 监听地址，默认绑定本机地址，禁止在生产环境开放到公网。
	Listen string
	// Token 是与管理后端共享的静态令牌。
	Token string
	// ImageDir 是镜像根目录，所有镜像路径必须位于该目录内。
	ImageDir string
	// DiskDir 是虚拟磁盘根目录，所有磁盘路径必须位于该目录内。
	DiskDir string
	// MaxRequestSeconds 是单个请求的最长处理时间。
	MaxRequestSeconds int
	// AllowDestructive 是宿主机侧的额外安全开关，不能替代后端授权。
	AllowDestructive bool
	// Version 是 Agent 版本，用于与管理后端做兼容性检测。
	Version string
}

// Load 从环境变量加载配置并执行校验。
//
// 返回的错误信息面向运维，明确指出缺失或非法项，便于直接修复。
func Load() (Config, error) {
	cfg := Config{
		Listen:           envOrDefault("CLOUDVIRT_AGENT_LISTEN", defaultListen),
		Token:            os.Getenv("CLOUDVIRT_AGENT_TOKEN"),
		ImageDir:         envOrDefault("CLOUDVIRT_IMAGE_DIR", defaultImageDir),
		DiskDir:          envOrDefault("CLOUDVIRT_DISK_DIR", defaultDiskDir),
		AllowDestructive: envBool("CLOUDVIRT_ALLOW_DESTRUCTIVE"),
		Version:          envOrDefault("CLOUDVIRT_AGENT_VERSION", "0.1.0"),
	}
	if len(cfg.Token) < MinTokenLength {
		return Config{}, fmt.Errorf(
			"CLOUDVIRT_AGENT_TOKEN 缺失或长度不足 %d 字符，请配置至少 %d 字节的随机令牌",
			MinTokenLength, MinTokenLength)
	}

	seconds, err := envInt("CLOUDVIRT_MAX_REQUEST_SECONDS", defaultMaxRequestSeconds)
	if err != nil {
		return Config{}, err
	}
	if seconds <= 0 {
		return Config{}, fmt.Errorf("CLOUDVIRT_MAX_REQUEST_SECONDS 必须为正整数，当前为 %d", seconds)
	}
	cfg.MaxRequestSeconds = seconds

	if strings.TrimSpace(cfg.ImageDir) == "" || strings.TrimSpace(cfg.DiskDir) == "" {
		return Config{}, fmt.Errorf("CLOUDVIRT_IMAGE_DIR 与 CLOUDVIRT_DISK_DIR 不能为空")
	}

	return cfg, nil
}

// envOrDefault 读取环境变量，未设置或为空白时返回默认值。
func envOrDefault(name, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(name)); value != "" {
		return value
	}
	return fallback
}

// envBool 解析布尔型环境变量，接受 1/true/yes/on（大小写不敏感）。
func envBool(name string) bool {
	switch strings.ToLower(strings.TrimSpace(os.Getenv(name))) {
	case "1", "true", "yes", "on":
		return true
	default:
		return false
	}
}

// envInt 解析整数型环境变量，未设置时返回默认值，格式非法时返回错误。
func envInt(name string, fallback int) (int, error) {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return fallback, nil
	}
	value, err := strconv.Atoi(raw)
	if err != nil {
		return 0, fmt.Errorf("%s 必须为整数，当前为 %q", name, raw)
	}
	return value, nil
}
