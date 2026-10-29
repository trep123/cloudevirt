// Package hostbridge implements the narrowly scoped root network helper.
// The public agent stays unprivileged; only its group can reach the Unix socket.
package hostbridge

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"
)

const Socket = "/run/cloudvirt-network/network.sock"

type Spec struct {
	Type   string `json:"type"`
	Bridge string `json:"bridge"`
	Uplink string `json:"uplink"`
}
type Interface struct {
	Name     string `json:"name"`
	MAC      string `json:"mac"`
	State    string `json:"state"`
	Eligible bool   `json:"eligible"`
	Reason   string `json:"reason"`
}
type address struct {
	Local string `json:"local"`
}
type link struct {
	Name      string    `json:"ifname"`
	MAC       string    `json:"address"`
	State     string    `json:"operstate"`
	Master    string    `json:"master"`
	Addresses []address `json:"addr_info"`
	Info      struct {
		Kind string `json:"info_kind"`
	} `json:"linkinfo"`
}
type route struct {
	Dev  string  `json:"dev"`
	Dst  string  `json:"dst"`
	Next []route `json:"nexthops"`
}
type Runner func(context.Context, string, ...string) ([]byte, error)
type Manager struct {
	Dir, Sysfs string
	Run        Runner
	Protected  map[string]bool
	mu         sync.Mutex
}

var validName = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_-]{0,14}$`)

func New() *Manager {
	protected := map[string]bool{}
	for _, name := range strings.Fields(strings.ReplaceAll(os.Getenv("CLOUDVIRT_PROTECTED_INTERFACES"), ",", " ")) {
		protected[name] = true
	}
	return &Manager{Dir: "/var/lib/cloudvirt/network", Sysfs: "/sys/class/net", Run: run, Protected: protected}
}
func run(ctx context.Context, name string, args ...string) ([]byte, error) {
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	out, err := exec.CommandContext(ctx, name, args...).CombinedOutput()
	if err != nil {
		return nil, fmt.Errorf("%s: %w: %.500s", name, err, out)
	}
	return out, nil
}
func (m *Manager) snapshot(ctx context.Context) ([]link, []route, error) {
	var links []link
	var routes []route
	b, err := m.Run(ctx, "ip", "-j", "-d", "address", "show")
	if err != nil {
		return nil, nil, err
	}
	if err = json.Unmarshal(b, &links); err != nil {
		return nil, nil, err
	}
	for _, args := range [][]string{{"-j", "route", "show", "table", "all"}, {"-6", "-j", "route", "show", "table", "all"}} {
		b, err = m.Run(ctx, "ip", args...)
		if err != nil {
			return nil, nil, err
		}
		var rs []route
		if err = json.Unmarshal(b, &rs); err != nil {
			return nil, nil, err
		}
		routes = append(routes, rs...)
	}
	return links, routes, nil
}
func harmlessDestination(dst string) bool {
	ip := net.ParseIP(dst)
	if ip == nil {
		if a, _, err := net.ParseCIDR(dst); err == nil {
			ip = a
		}
	}
	return ip != nil && ip.To4() == nil && (ip.IsLinkLocalUnicast() || ip.IsMulticast())
}
func routeUses(rs []route, name string) bool {
	for _, r := range rs {
		if r.Dev == name && !harmlessDestination(r.Dst) {
			return true
		}
		if routeUses(r.Next, name) {
			return true
		}
	}
	return false
}
func unsafe(l link, rs []route, owned string) string {
	if l.Master != "" && l.Master != owned {
		return "已加入网桥、聚合或其他主接口"
	}
	for _, a := range l.Addresses {
		ip := net.ParseIP(a.Local)
		if ip == nil || ip.To4() != nil || !ip.IsLinkLocalUnicast() {
			return "接口已配置地址，可能承担节点管理通信"
		}
	}
	if routeUses(rs, l.Name) {
		return "接口承载管理或业务路由"
	}
	return ""
}
func (m *Manager) inventory(ctx context.Context) ([]Interface, error) {
	links, rs, err := m.snapshot(ctx)
	if err != nil {
		return nil, err
	}
	out := []Interface{}
	reserved := map[string]bool{}
	files, err := filepath.Glob(filepath.Join(m.Dir, "*.json"))
	if err != nil {
		return nil, err
	}
	for _, path := range files {
		b, e := os.ReadFile(path)
		if e != nil {
			return nil, e
		}
		var s Spec
		if e = json.Unmarshal(b, &s); e != nil {
			return nil, e
		}
		reserved[s.Uplink] = true
	}
	for _, l := range links {
		if _, err = os.Stat(filepath.Join(m.Sysfs, l.Name, "device")); err != nil {
			continue
		}
		reason := unsafe(l, rs, "")
		if m.Protected[l.Name] {
			reason = "已指定为管理接口"
		}
		if reason == "" && reserved[l.Name] {
			reason = "已被托管网桥预留"
		}
		out = append(out, Interface{Name: l.Name, MAC: l.MAC, State: l.State, Eligible: reason == "", Reason: reason})
	}
	return out, nil
}
func (m *Manager) Inventory(ctx context.Context) ([]Interface, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.inventory(ctx)
}
func (m *Manager) bridgeTypes(ctx context.Context) []string {
	types := []string{"BRIDGE"}
	if _, e := m.Run(ctx, "ovs-vsctl", "--timeout=3", "show"); e == nil {
		types = append(types, "OVS")
	}
	return types
}
func (m *Manager) file(s Spec) string { return filepath.Join(m.Dir, s.Bridge+".json") }
func (m *Manager) validate(ctx context.Context, s Spec, owned bool) error {
	if m.Protected[s.Uplink] {
		return fmt.Errorf("管理接口禁止桥接")
	}
	if !validName.MatchString(s.Bridge) || !validName.MatchString(s.Uplink) || s.Bridge == s.Uplink || (s.Type != "BRIDGE" && s.Type != "OVS") {
		return fmt.Errorf("网桥参数无效")
	}
	if _, err := os.Stat(filepath.Join(m.Sysfs, s.Uplink, "device")); err != nil {
		return fmt.Errorf("仅允许桥接实际物理网卡")
	}
	links, rs, err := m.snapshot(ctx)
	if err != nil {
		return err
	}
	found := false
	for _, l := range links {
		if l.Name == s.Uplink {
			found = true
			allow := ""
			if owned {
				allow = s.Bridge
				if s.Type == "OVS" && l.Master == "ovs-system" {
					b, e := m.Run(ctx, "ovs-vsctl", "--timeout=8", "port-to-br", s.Uplink)
					if e != nil || strings.TrimSpace(string(b)) != s.Bridge {
						return fmt.Errorf("OVS physical port ownership mismatch")
					}
					allow = "ovs-system"
				}
			}
			if reason := unsafe(l, rs, allow); reason != "" {
				return fmt.Errorf("拒绝桥接 %s：%s", s.Uplink, reason)
			}
		}
		if l.Name == s.Bridge {
			if !owned {
				return fmt.Errorf("网桥已存在，不能接管外部网桥")
			}
			if reason := unsafe(l, rs, ""); reason != "" {
				return fmt.Errorf("网桥已承担地址或路由，禁止重配：%s", reason)
			}
			kind := "bridge"
			if s.Type == "OVS" {
				kind = "openvswitch"
			}
			if l.Info.Kind != kind {
				return fmt.Errorf("已有设备类型与托管网桥不符")
			}
		}
	}
	if !found {
		return fmt.Errorf("物理网卡已不存在")
	}
	return nil
}
func (m *Manager) apply(ctx context.Context, s Spec) error {
	command := func(n string, a ...string) error { _, e := m.Run(ctx, n, a...); return e }
	links, _, err := m.snapshot(ctx)
	if err != nil {
		return err
	}
	exists := false
	for _, l := range links {
		if l.Name == s.Bridge {
			exists = true
		}
	}
	if s.Type == "OVS" {
		if err = command("ovs-vsctl", "--timeout=8", "--may-exist", "add-br", s.Bridge); err != nil {
			return err
		}
		if err = command("ovs-vsctl", "--timeout=8", "--may-exist", "add-port", s.Bridge, s.Uplink); err != nil {
			return err
		}
	} else {
		if !exists {
			if err = command("ip", "link", "add", "name", s.Bridge, "type", "bridge"); err != nil {
				return err
			}
		}
		if err = command("ip", "link", "set", "dev", s.Uplink, "master", s.Bridge); err != nil {
			return err
		}
	}
	for _, n := range []string{s.Uplink, s.Bridge} {
		if err = command("ip", "link", "set", "dev", n, "up"); err != nil {
			return err
		}
	}
	return m.verify(ctx, s)
}
func (m *Manager) verify(ctx context.Context, s Spec) error {
	links, _, err := m.snapshot(ctx)
	if err != nil {
		return err
	}
	bridgeUp := false
	port := false
	for _, l := range links {
		if l.Name == s.Bridge {
			bridgeUp = true
		}
		if l.Name == s.Uplink && s.Type == "BRIDGE" {
			port = l.Master == s.Bridge
		}
	}
	if s.Type == "OVS" {
		b, e := m.Run(ctx, "ovs-vsctl", "--timeout=8", "port-to-br", s.Uplink)
		if e != nil {
			return e
		}
		port = strings.TrimSpace(string(b)) == s.Bridge
	}
	if !bridgeUp || !port {
		return fmt.Errorf("网桥或物理端口核验失败；配置已保留，请核对后重试")
	}
	return nil
}
func (m *Manager) Create(ctx context.Context, s Spec) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if !validName.MatchString(s.Bridge) {
		return fmt.Errorf("网桥名称无效")
	}
	path := m.file(s)
	owned := false
	if b, err := os.ReadFile(path); err == nil {
		var old Spec
		if json.Unmarshal(b, &old) != nil || old != s {
			return fmt.Errorf("托管配置冲突")
		}
		owned = true
	} else if !os.IsNotExist(err) {
		return err
	}
	if err := m.validate(ctx, s, owned); err != nil {
		return err
	}
	files, err := filepath.Glob(filepath.Join(m.Dir, "*.json"))
	if err != nil {
		return err
	}
	for _, p := range files {
		if p == path {
			continue
		}
		b, e := os.ReadFile(p)
		if e != nil {
			return e
		}
		var old Spec
		if json.Unmarshal(b, &old) != nil {
			return fmt.Errorf("已有托管配置损坏")
		}
		if old.Uplink == s.Uplink {
			return fmt.Errorf("物理网卡已被另一个托管网桥预留")
		}
	}
	if s.Type == "OVS" {
		if _, err = m.Run(ctx, "ovs-vsctl", "--timeout=8", "show"); err != nil {
			return fmt.Errorf("Open vSwitch 服务不可用：%w", err)
		}
	}
	if !owned {
		if err = os.MkdirAll(m.Dir, 0700); err != nil {
			return err
		}
		b, _ := json.Marshal(s)
		f, e := os.CreateTemp(m.Dir, ".bridge-*.tmp")
		if e != nil {
			return e
		}
		defer os.Remove(f.Name())
		_, e = f.Write(b)
		if e == nil {
			e = f.Sync()
		}
		ce := f.Close()
		if e != nil {
			return e
		}
		if ce != nil {
			return ce
		}
		if e = os.Rename(f.Name(), path); e != nil {
			return e
		}
		d, e := os.Open(m.Dir)
		if e != nil {
			return e
		}
		e = d.Sync()
		d.Close()
		if e != nil {
			return e
		}
	}
	// Keep desired state on any partial failure: never delete a bridge that might be in use.
	return m.apply(ctx, s)
}
func (m *Manager) Restore(ctx context.Context) {
	files, err := filepath.Glob(filepath.Join(m.Dir, "*.json"))
	if err != nil {
		slog.Error("读取网桥配置失败", "error", err)
		return
	}
	for _, p := range files {
		b, e := os.ReadFile(p)
		if e != nil {
			continue
		}
		var s Spec
		if json.Unmarshal(b, &s) != nil {
			continue
		}
		if e = m.Create(ctx, s); e != nil {
			slog.Error("恢复托管网桥失败", "bridge", s.Bridge, "error", e)
		}
	}
}
func Serve() error {
	m := New()
	m.Restore(context.Background())
	if err := os.Remove(Socket); err != nil && !os.IsNotExist(err) {
		return err
	}
	listener, err := net.Listen("unix", Socket)
	if err != nil {
		return err
	}
	defer listener.Close()
	if err = os.Chmod(Socket, 0660); err != nil {
		return err
	}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /api/v1/node/physical-interfaces", func(w http.ResponseWriter, r *http.Request) {
		v, e := m.Inventory(r.Context())
		if e != nil {
			failure(w, e)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{"interfaces": v, "sampled_at": time.Now().UTC(), "bridge_types": m.bridgeTypes(r.Context())})
	})
	mux.HandleFunc("POST /api/v1/node/bridges", func(w http.ResponseWriter, r *http.Request) {
		var s Spec
		d := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096))
		d.DisallowUnknownFields()
		if e := d.Decode(&s); e != nil {
			failure(w, e)
			return
		}
		if e := m.Create(r.Context(), s); e != nil {
			failure(w, e)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{"type": s.Type, "bridge": s.Bridge, "uplink": s.Uplink, "verified": true})
	})
	return (&http.Server{Handler: mux, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 30 * time.Second, WriteTimeout: 30 * time.Second}).Serve(listener)
}
func failure(w http.ResponseWriter, e error) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusConflict)
	json.NewEncoder(w).Encode(map[string]any{"error": map[string]string{"code": "CONFLICT", "message": fmt.Sprintf("%.500s", e.Error())}})
}
