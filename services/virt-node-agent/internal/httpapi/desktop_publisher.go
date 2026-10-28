package httpapi

import (
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/domainxml"
)

type desktopProcess struct {
	command  *exec.Cmd
	domain   string
	expires  time.Time
	alive    bool
	stopping bool
	done     chan struct{}
}
type DesktopPublisher struct {
	mu        sync.Mutex
	processes map[string]*desktopProcess
	stop      chan struct{}
	base      string
	script    string
	limit     int
}

func NewDesktopPublisher() *DesktopPublisher {
	base := os.Getenv("CLOUDVIRT_MEDIA_PUBLISH_BASE_URL")
	if base == "" {
		base = "rtsp://127.0.0.1:8554"
	}
	script := os.Getenv("CLOUDVIRT_DESKTOP_PUBLISHER_SCRIPT")
	if script == "" {
		script = "/opt/cloudvirt/services/virt-node-agent/scripts/publish_desktop.py"
	}
	limit, _ := strconv.Atoi(os.Getenv("CLOUDVIRT_DESKTOP_STREAM_LIMIT"))
	if limit < 1 || limit > 8 {
		limit = 2
	}
	publisher := &DesktopPublisher{processes: make(map[string]*desktopProcess), stop: make(chan struct{}), base: strings.TrimRight(base, "/"), script: script, limit: limit}
	go publisher.watch()
	return publisher
}
func (publisher *DesktopPublisher) watch() {
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-publisher.stop:
			return
		case now := <-ticker.C:
			publisher.mu.Lock()
			for id, process := range publisher.processes {
				if process.alive && process.expires.Before(now) {
					publisher.terminate(process)
				}
				if !process.alive && process.expires.Add(time.Minute).Before(now) {
					delete(publisher.processes, id)
				}
			}
			publisher.mu.Unlock()
		}
	}
}
func (publisher *DesktopPublisher) terminate(process *desktopProcess) {
	if !process.alive || process.stopping {
		return
	}
	process.stopping = true
	_ = process.command.Process.Signal(syscall.SIGTERM)
	go func() {
		select {
		case <-process.done:
		case <-time.After(3 * time.Second):
			_ = process.command.Process.Kill()
		}
	}()
}
func (publisher *DesktopPublisher) Close() {
	close(publisher.stop)
	publisher.mu.Lock()
	defer publisher.mu.Unlock()
	for _, process := range publisher.processes {
		publisher.terminate(process)
	}
}
func (publisher *DesktopPublisher) start(id, domain, password string, port int) error {
	publisher.mu.Lock()
	defer publisher.mu.Unlock()
	if process := publisher.processes[id]; process != nil && process.alive {
		if process.stopping {
			return apierr.New(apierr.CodeConflict, "串流正在停止", nil)
		}
		if process.domain != domain {
			return apierr.New(apierr.CodeInvalidArgument, "串流目标不匹配", nil)
		}
		process.expires = time.Now().Add(90 * time.Second)
		return nil
	}
	count := 0
	for _, process := range publisher.processes {
		if process.alive {
			count++
		}
	}
	if count >= publisher.limit {
		return apierr.New(apierr.CodeOperationFailed, "节点桌面串流数量已达上限", nil)
	}
	parsed, err := url.Parse(publisher.base)
	if err != nil || (parsed.Scheme != "rtsp" && parsed.Scheme != "rtsps") || parsed.Hostname() == "" || parsed.RawQuery != "" || parsed.Fragment != "" || parsed.Path != "" {
		return apierr.New(apierr.CodeOperationFailed, "节点媒体发布地址配置无效", nil)
	}
	data, _ := json.Marshal(map[string]any{"port": port, "password": password, "url": publisher.base + "/desktop-" + strings.ReplaceAll(id, "-", "")})
	command := exec.Command("/usr/bin/python3", "-I", publisher.script)
	command.Stdin = strings.NewReader(string(data))
	command.Stdout = io.Discard
	command.Stderr = io.Discard
	if err := command.Start(); err != nil {
		return apierr.New(apierr.CodeOperationFailed, "无法启动桌面采集进程", nil)
	}
	process := &desktopProcess{command: command, domain: domain, expires: time.Now().Add(90 * time.Second), alive: true, done: make(chan struct{})}
	publisher.processes[id] = process
	go func() {
		_ = command.Wait()
		publisher.mu.Lock()
		process.alive = false
		close(process.done)
		publisher.mu.Unlock()
	}()
	return nil
}
func desktopStreamHandler(deps Dependencies) http.HandlerFunc {
	return func(writer http.ResponseWriter, request *http.Request) {
		id := request.PathValue("id")
		if !consoleID.MatchString(id) {
			writeAPIError(writer, deps.Logger, apierr.New(apierr.CodeInvalidArgument, "串流 ID 无效", nil), RequestIDFromContext(request.Context()))
			return
		}
		publisher := deps.Publisher
		if publisher == nil {
			writeAPIError(writer, deps.Logger, apierr.New(apierr.CodeOperationFailed, "桌面发布服务未配置", nil), RequestIDFromContext(request.Context()))
			return
		}
		if request.Method == http.MethodPost && !strings.HasSuffix(request.URL.Path, "/lease") {
			var input struct {
				Domain   string `json:"domain"`
				Password string `json:"password"`
			}
			decoder := json.NewDecoder(http.MaxBytesReader(writer, request.Body, 4096))
			decoder.DisallowUnknownFields()
			if decoder.Decode(&input) != nil || !domainxml.ValidName(input.Domain) || len(input.Password) < 1 || len(input.Password) > 64 {
				writeAPIError(writer, deps.Logger, apierr.New(apierr.CodeInvalidArgument, "桌面发布参数无效", nil), RequestIDFromContext(request.Context()))
				return
			}
			if deps.Virtualizer == nil {
				writeAPIError(writer, deps.Logger, errNoVirtualizer, RequestIDFromContext(request.Context()))
				return
			}
			port, err := deps.Virtualizer.DomainVNCPort(request.Context(), input.Domain)
			if err == nil {
				err = publisher.start(id, input.Domain, input.Password, port)
			}
			if err != nil {
				writeAPIError(writer, deps.Logger, err, RequestIDFromContext(request.Context()))
				return
			}
		}
		publisher.mu.Lock()
		defer publisher.mu.Unlock()
		process := publisher.processes[id]
		if request.Method == http.MethodDelete {
			if process != nil {
				publisher.terminate(process)
			}
			state := "STOPPED"
			if process != nil && process.alive {
				state = "STOPPING"
			}
			writeJSON(writer, 200, map[string]string{"status": state})
			return
		}
		if process == nil {
			writeJSON(writer, 404, map[string]string{"status": "MISSING"})
			return
		}
		if request.Method == http.MethodPost && process.alive && !process.stopping {
			process.expires = time.Now().Add(90 * time.Second)
		}
		state := "FAILED"
		if process.alive {
			state = "RUNNING"
		}
		if process.stopping {
			state = "STOPPED"
			if process.alive {
				state = "STOPPING"
			}
		}
		writeJSON(writer, 200, map[string]any{"status": state, "expires_at": process.expires})
	}
}
