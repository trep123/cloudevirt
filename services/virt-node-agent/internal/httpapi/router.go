// Package httpapi 提供节点 Agent 的 HTTP 路由、中间件与响应结构。
//
// 健康检查免认证；/api/v1 下的接口必须携带共享令牌。
package httpapi

import (
	"context"
	"encoding/json"
	"log/slog"
	"net"
	"net/http"
	"time"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/auth"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/host"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/libvirt"
)

// errNoDomainLister 表示未注入域查询依赖。
var errNoDomainLister = apierr.New(apierr.CodeInternalError, "域查询依赖未初始化", nil)

// errNoVirtualizer 表示未注入域操作依赖。
var errNoVirtualizer = apierr.New(apierr.CodeInternalError, "域操作依赖未初始化", nil)

// healthResponse 是健康检查响应体。
type healthResponse struct {
	Status  string `json:"status"`
	Version string `json:"version"`
}

// DomainLister 是域查询依赖，便于测试替换。
type DomainLister interface {
	ListDomains(ctx context.Context) ([]libvirt.Domain, error)
}

// Dependencies 是路由所需的外部依赖。
type Dependencies struct {
	SSHDial          func(string, string, time.Duration) (net.Conn, error)
	Version          string
	Token            string
	StoragePaths     []string
	ImageDir         string
	DiskDir          string
	StorageRoots     []string
	AllowDestructive bool
	Domains          DomainLister
	Virtualizer      DomainOperator
	Networks         NetworkLister
	Logger           *slog.Logger
}

// NewRouter 注册全部路由并返回处理器。
func NewRouter(deps Dependencies) http.Handler {
	logger := deps.Logger
	if logger == nil {
		logger = slog.Default()
	}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(writer http.ResponseWriter, request *http.Request) {
		writeJSON(writer, http.StatusOK, healthResponse{Status: "ok", Version: deps.Version})
		logger.Info("健康检查", "remote_addr", request.RemoteAddr, "result", "ok")
	})

	api := http.NewServeMux()
	api.HandleFunc("GET /api/v1/node/physical-interfaces", bridgeProxyHandler(deps))
	api.HandleFunc("POST /api/v1/node/bridges", bridgeProxyHandler(deps))
	api.HandleFunc("GET /api/v1/node/capabilities", creationCapabilitiesHandler(deps))
	api.HandleFunc("POST /api/v1/console-sessions/{id}/lease", consoleLeaseHandler(deps))
	api.HandleFunc("DELETE /api/v1/console-sessions/{id}", consoleLeaseHandler(deps))
	api.HandleFunc("GET /api/v1/images/uploads/{id}", imageUploadHandler(deps))
	api.HandleFunc("PUT /api/v1/images/uploads/{id}", imageUploadHandler(deps))
	api.HandleFunc("POST /api/v1/images/uploads/{id}/complete", imageUploadHandler(deps))
	api.HandleFunc("DELETE /api/v1/images/uploads/{id}", imageUploadHandler(deps))
	api.HandleFunc("GET /api/v1/storage-pools", infrastructureHandler(deps, false))
	api.HandleFunc("POST /api/v1/storage-pools", infrastructureHandler(deps, false))
	api.HandleFunc("GET /api/v1/domains/{name}/snapshots", infrastructureHandler(deps, true))
	api.HandleFunc("POST /api/v1/domains/{name}/snapshots", infrastructureHandler(deps, true))
	api.HandleFunc("GET /api/v1/node/resources", resourcesHandler(deps))
	api.HandleFunc("GET /api/v1/domains", domainsHandler(deps))
	api.HandleFunc("GET /api/v1/domains/{name}/display", displayHandler(deps))
	api.HandleFunc("GET /api/v1/domains/{name}/hardware", hardwareHandler(deps))
	api.HandleFunc("POST /api/v1/domains/{name}/hardware", hardwareHandler(deps))
	api.HandleFunc("POST /api/v1/domains/{name}/display", displayHandler(deps))
	api.HandleFunc("GET /api/v1/domains/{name}/addresses", domainAddressesHandler(deps))
	api.HandleFunc("GET /api/v1/domains/{name}/ssh-targets", sshTargetsHandler(deps))
	api.HandleFunc("GET /api/v1/domains/{name}/interfaces", domainInterfacesHandler(deps))
	api.HandleFunc("GET /api/v1/networks", networkListHandler(deps))
	api.HandleFunc("POST /api/v1/disks/inspect", inspectExistingDiskHandler(deps))
	api.HandleFunc("GET /api/v1/disks", diskListHandler(deps))
	api.HandleFunc("DELETE /api/v1/disks", unusedDiskHandler(deps))
	api.HandleFunc("POST /api/v1/domains", createDomainHandler(deps))
	api.HandleFunc("POST /api/v1/domains/{name}/start", domainActionHandler(deps, "start"))
	api.HandleFunc("POST /api/v1/domains/{name}/shutdown", domainActionHandler(deps, "shutdown"))
	api.HandleFunc("POST /api/v1/domains/{name}/force-stop", domainActionHandler(deps, "force-stop"))
	api.HandleFunc("POST /api/v1/domains/{name}/reboot", domainActionHandler(deps, "reboot"))
	api.HandleFunc("DELETE /api/v1/domains/{name}", deleteDomainHandler(deps))
	api.HandleFunc("POST /api/v1/images/inspect", inspectImageHandler(deps))
	api.HandleFunc("DELETE /api/v1/images", deleteImageHandler(deps))

	protected := auth.TokenMiddleware(deps.Token, api)
	mux.Handle("/api/", protected)
	mux.Handle("/api/v1/", protected)
	// 控制台 WebSocket 使用短签名凭证，不使用静态令牌头
	mux.HandleFunc("GET /ssh", sshProxyHandler(deps))
	mux.HandleFunc("GET /vnc", vncProxyHandler(deps))
	return RequestIDMiddleware(mux)
}

// storagePayload 是单个路径的存储信息。
type storagePayload struct {
	FilesystemID string `json:"filesystem_id,omitempty"`
	Path         string `json:"path"`
	TotalBytes   uint64 `json:"total_bytes"`
	FreeBytes    uint64 `json:"free_bytes"`
}

// resourcesResponse 是资源采集响应体。
type resourcesResponse struct {
	CPUUsagePercent    *float64         `json:"cpu_usage_percent"`
	CPUSampledAt       *time.Time       `json:"cpu_sampled_at"`
	CPULogical         int              `json:"cpu_logical"`
	MemoryTotalMiB     int64            `json:"memory_total_mib"`
	MemoryAvailableMiB int64            `json:"memory_available_mib"`
	Storage            []storagePayload `json:"storage"`
	SampledAt          time.Time        `json:"sampled_at"`
}

// resourcesHandler 采集宿主机资源。
func resourcesHandler(deps Dependencies) http.HandlerFunc {
	return func(writer http.ResponseWriter, request *http.Request) {
		requestID := RequestIDFromContext(request.Context())
		resources, err := host.Collect(deps.StoragePaths)
		if err != nil {
			// 采集失败（如存储目录不存在）记入日志，对外只返回稳定错误码
			deps.Logger.Error("资源采集失败", "error", err, "request_id", requestID)
			writeAPIError(writer, deps.Logger, apierr.New(
				apierr.CodeOperationFailed, "资源采集失败", err,
			), requestID)
			return
		}
		payload := resourcesResponse{
			CPUUsagePercent:    resources.CPUUsagePercent,
			CPUSampledAt:       resources.CPUSampledAt,
			CPULogical:         resources.CPULogical,
			MemoryTotalMiB:     resources.MemoryTotalMiB,
			MemoryAvailableMiB: resources.MemoryAvailableMiB,
			SampledAt:          resources.SampledAt,
		}
		for _, item := range resources.Storage {
			payload.Storage = append(payload.Storage, storagePayload{
				FilesystemID: item.FilesystemID,
				Path:         item.Path,
				TotalBytes:   item.TotalBytes,
				FreeBytes:    item.FreeBytes,
			})
		}
		writeJSON(writer, http.StatusOK, payload)
	}
}

// domainPayload 是单个域的信息。
type domainPayload struct {
	Name  string `json:"name"`
	State string `json:"state"`
}

// domainsResponse 是域列表响应体。
type domainsResponse struct {
	Domains   []domainPayload `json:"domains"`
	SampledAt time.Time       `json:"sampled_at"`
}

// domainsHandler 返回域列表与状态。
func domainsHandler(deps Dependencies) http.HandlerFunc {
	return func(writer http.ResponseWriter, request *http.Request) {
		requestID := RequestIDFromContext(request.Context())
		if deps.Domains == nil {
			writeAPIError(writer, deps.Logger, errNoDomainLister, requestID)
			return
		}
		domains, err := deps.Domains.ListDomains(request.Context())
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		payload := domainsResponse{Domains: []domainPayload{}, SampledAt: time.Now().UTC()}
		for _, item := range domains {
			payload.Domains = append(payload.Domains, domainPayload{Name: item.Name, State: item.State})
		}
		writeJSON(writer, http.StatusOK, payload)
	}
}

// writeJSON 写入 JSON 响应，统一设置 Content-Type。
func writeJSON(writer http.ResponseWriter, status int, payload any) {
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(status)
	if err := json.NewEncoder(writer).Encode(payload); err != nil {
		slog.Error("响应序列化失败", "error", err)
	}
}
