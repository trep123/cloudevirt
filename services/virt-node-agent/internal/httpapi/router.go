// Package httpapi �ṩ�ڵ� Agent �� HTTP ·�ɡ��м������Ӧ�ṹ��
//
// �����������֤��/api/v1 �µĽӿڱ���Я���������ơ�
package httpapi

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"time"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/auth"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/host"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/libvirt"
)

// errNoDomainLister ��ʾδע�����ѯ������
var errNoDomainLister = apierr.New(apierr.CodeInternalError, "���ѯ����δ��ʼ��", nil)

// errNoVirtualizer ��ʾδע�������������
var errNoVirtualizer = apierr.New(apierr.CodeInternalError, "���������δ��ʼ��", nil)

// healthResponse �ǽ��������Ӧ�塣
type healthResponse struct {
	Status  string `json:"status"`
	Version string `json:"version"`
}

// DomainLister �����ѯ���������ڲ����滻��
type DomainLister interface {
	ListDomains(ctx context.Context) ([]libvirt.Domain, error)
}

// Dependencies ��·��������ⲿ������
type Dependencies struct {
	Version          string
	Token            string
	StoragePaths     []string
	ImageDir         string
	DiskDir          string
	AllowDestructive bool
	Domains          DomainLister
	Virtualizer      DomainOperator
	Networks         NetworkLister
	Logger           *slog.Logger
}

// NewRouter ע��ȫ��·�ɲ����ش�������
func NewRouter(deps Dependencies) http.Handler {
	logger := deps.Logger
	if logger == nil {
		logger = slog.Default()
	}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(writer http.ResponseWriter, request *http.Request) {
		writeJSON(writer, http.StatusOK, healthResponse{Status: "ok", Version: deps.Version})
		logger.Info("�������", "remote_addr", request.RemoteAddr, "result", "ok")
	})

	api := http.NewServeMux()
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
	api.HandleFunc("POST /api/v1/domains/{name}/display", displayHandler(deps))
	api.HandleFunc("GET /api/v1/domains/{name}/addresses", domainAddressesHandler(deps))
	api.HandleFunc("GET /api/v1/domains/{name}/interfaces", domainInterfacesHandler(deps))
	api.HandleFunc("GET /api/v1/networks", networkListHandler(deps))
	api.HandleFunc("GET /api/v1/disks", diskListHandler(deps))
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
	// ����̨ WebSocket ʹ�ö�ǩ��ƾ֤����ʹ�þ�̬����ͷ
	mux.HandleFunc("GET /vnc", vncProxyHandler(deps))
	return RequestIDMiddleware(mux)
}

// storagePayload �ǵ���·���Ĵ洢��Ϣ��
type storagePayload struct {
	Path       string `json:"path"`
	TotalBytes uint64 `json:"total_bytes"`
	FreeBytes  uint64 `json:"free_bytes"`
}

// resourcesResponse ����Դ�ɼ���Ӧ�塣
type resourcesResponse struct {
	CPULogical         int              `json:"cpu_logical"`
	MemoryTotalMiB     int64            `json:"memory_total_mib"`
	MemoryAvailableMiB int64            `json:"memory_available_mib"`
	Storage            []storagePayload `json:"storage"`
	SampledAt          time.Time        `json:"sampled_at"`
}

// resourcesHandler �ɼ���������Դ��
func resourcesHandler(deps Dependencies) http.HandlerFunc {
	return func(writer http.ResponseWriter, request *http.Request) {
		requestID := RequestIDFromContext(request.Context())
		resources, err := host.Collect(deps.StoragePaths)
		if err != nil {
			// �ɼ�ʧ�ܣ���洢Ŀ¼�����ڣ�������־������ֻ�����ȶ�������
			deps.Logger.Error("��Դ�ɼ�ʧ��", "error", err, "request_id", requestID)
			writeAPIError(writer, deps.Logger, apierr.New(
				apierr.CodeOperationFailed, "��Դ�ɼ�ʧ��", err,
			), requestID)
			return
		}
		payload := resourcesResponse{
			CPULogical:         resources.CPULogical,
			MemoryTotalMiB:     resources.MemoryTotalMiB,
			MemoryAvailableMiB: resources.MemoryAvailableMiB,
			SampledAt:          resources.SampledAt,
		}
		for _, item := range resources.Storage {
			payload.Storage = append(payload.Storage, storagePayload{
				Path:       item.Path,
				TotalBytes: item.TotalBytes,
				FreeBytes:  item.FreeBytes,
			})
		}
		writeJSON(writer, http.StatusOK, payload)
	}
}

// domainPayload �ǵ��������Ϣ��
type domainPayload struct {
	Name  string `json:"name"`
	State string `json:"state"`
}

// domainsResponse �����б���Ӧ�塣
type domainsResponse struct {
	Domains   []domainPayload `json:"domains"`
	SampledAt time.Time       `json:"sampled_at"`
}

// domainsHandler �������б���״̬��
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

// writeJSON д�� JSON ��Ӧ��ͳһ���� Content-Type��
func writeJSON(writer http.ResponseWriter, status int, payload any) {
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(status)
	if err := json.NewEncoder(writer).Encode(payload); err != nil {
		slog.Error("��Ӧ���л�ʧ��", "error", err)
	}
}
