// Package libvirt 封装宿主机上的域查询操作。
//
// 首版通过 virsh 命令行实现，所有调用使用固定可执行文件与参数数组，
// 不接受调用方传入可执行文件路径或任意命令参数。
package libvirt

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os/exec"
	"strings"
	"time"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
)

// 观测状态取值，与管理后端保持一致。
const (
	StateRunning = "RUNNING"
	StateShutoff = "SHUTOFF"
	StatePaused  = "PAUSED"
	StateCrashed = "CRASHED"
	StateUnknown = "UNKNOWN"
)

// 默认值。
const (
	DefaultBinary  = "virsh"
	DefaultURI     = "qemu:///system"
	DefaultTimeout = 20 * time.Second
)

// Domain 是域的简要信息。
type Domain struct {
	Name  string
	State string
}

// Client 通过 virsh 查询域信息。
type Client struct {
	// Binary 是固定可执行文件名，禁止由外部输入指定。
	Binary string
	// URI 是 libvirt 连接地址。
	URI string
	// Timeout 是单次命令超时。
	Timeout time.Duration
}

// NewClient 创建默认客户端。
func NewClient(timeout time.Duration) *Client {
	if timeout <= 0 {
		timeout = DefaultTimeout
	}
	return &Client{Binary: DefaultBinary, URI: DefaultURI, Timeout: timeout}
}

// ListDomains 返回全部域（含未启动）的名称与归一化状态。
func (c *Client) ListDomains(ctx context.Context) ([]Domain, error) {
	output, err := c.run(ctx, "list", "--all", "--name")
	if err != nil {
		return nil, err
	}
	var domains []Domain
	for _, name := range strings.Split(output, "\n") {
		name = strings.TrimSpace(name)
		if name == "" {
			continue
		}
		state, err := c.DomainState(ctx, name)
		if err != nil {
			return nil, err
		}
		domains = append(domains, Domain{Name: name, State: state})
	}
	return domains, nil
}

// DomainState 查询单个域的状态并归一化为平台取值。
func (c *Client) DomainState(ctx context.Context, name string) (string, error) {
	if strings.TrimSpace(name) == "" {
		return "", apierr.New(apierr.CodeInvalidArgument, "域名不能为空", nil)
	}
	output, err := c.run(ctx, "domstate", name)
	if err != nil {
		return "", err
	}
	return NormalizeState(output), nil
}

// NormalizeState 把 virsh 输出映射为平台状态，无法识别时返回 UNKNOWN。
//
// 未知状态一律映射为 UNKNOWN，不得默认当作关机。
func NormalizeState(raw string) string {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "running", "idle", "blocked":
		return StateRunning
	case "shut off", "shutdown", "shutoff":
		return StateShutoff
	case "paused":
		return StatePaused
	case "crashed", "dying":
		return StateCrashed
	default:
		return StateUnknown
	}
}

// run 执行 virsh 命令并返回标准输出，失败时映射为稳定错误码。
func (c *Client) run(ctx context.Context, args ...string) (string, error) {
	fullArgs := append([]string{"-c", c.URI}, args...)
	commandCtx, cancel := context.WithTimeout(ctx, c.Timeout)
	defer cancel()

	var stdout, stderr bytes.Buffer
	command := exec.CommandContext(commandCtx, c.Binary, fullArgs...)
	command.Stdout = &stdout
	command.Stderr = &stderr

	runErr := command.Run()
	if commandCtx.Err() != nil && errors.Is(commandCtx.Err(), context.DeadlineExceeded) {
		return "", apierr.New(apierr.CodeCommandTimeout, "virsh 命令执行超时", commandCtx.Err())
	}
	if runErr != nil {
		message := strings.TrimSpace(stderr.String())
		if message == "" {
			message = runErr.Error()
		}
		return "", apierr.New(apierr.CodeLibvirtUnavailable, fmt.Sprintf("virsh 执行失败: %s", message), runErr)
	}
	return stdout.String(), nil
}
