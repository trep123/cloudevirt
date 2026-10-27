package httpapi

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/libvirt"
)

// fakeLister 用于测试替换真实 virsh 调用。
type fakeLister struct {
	domains []libvirt.Domain
	err     error
}

func (f fakeLister) ListDomains(ctx context.Context) ([]libvirt.Domain, error) {
	return f.domains, f.err
}

func testDependencies() Dependencies {
	return Dependencies{
		Version:      "0.1.0",
		Token:        strings.Repeat("t", 32),
		StoragePaths: nil,
		Domains:      fakeLister{},
		Logger:       slog.Default(),
	}
}

// TestHealthDoesNotRequireToken 校验健康检查免认证。
func TestHealthDoesNotRequireToken(t *testing.T) {
	router := NewRouter(testDependencies())

	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/health", nil))

	if recorder.Code != http.StatusOK {
		t.Fatalf("状态码错误: got=%d want=200", recorder.Code)
	}
}

// TestProtectedEndpointsRequireToken 校验业务接口必须携带令牌。
func TestProtectedEndpointsRequireToken(t *testing.T) {
	cases := []string{"/api/v1/node/resources", "/api/v1/domains"}
	for _, path := range cases {
		t.Run(path, func(t *testing.T) {
			router := NewRouter(testDependencies())
			recorder := httptest.NewRecorder()
			router.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, path, nil))

			if recorder.Code != http.StatusUnauthorized {
				t.Fatalf("未携带令牌应返回 401: got=%d", recorder.Code)
			}
			if !strings.Contains(recorder.Body.String(), "UNAUTHORIZED") {
				t.Errorf("响应应包含错误码: %s", recorder.Body.String())
			}
		})
	}
}

// TestWrongTokenIsRejected 校验错误令牌被拒绝。
func TestWrongTokenIsRejected(t *testing.T) {
	router := NewRouter(testDependencies())
	request := httptest.NewRequest(http.MethodGet, "/api/v1/domains", nil)
	request.Header.Set("Authorization", "Bearer wrong-token-value")

	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusUnauthorized {
		t.Fatalf("错误令牌应返回 401: got=%d", recorder.Code)
	}
}

// TestResourcesEndpointUsesRealSampler 校验资源接口返回真实采集值。
func TestResourcesEndpointUsesRealSampler(t *testing.T) {
	deps := testDependencies()
	deps.StoragePaths = []string{t.TempDir()}
	router := NewRouter(deps)

	request := httptest.NewRequest(http.MethodGet, "/api/v1/node/resources", nil)
	request.Header.Set("Authorization", "Bearer "+deps.Token)
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("状态码错误: got=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var payload resourcesResponse
	if err := json.Unmarshal(recorder.Body.Bytes(), &payload); err != nil {
		t.Fatalf("响应不是合法 JSON: %v", err)
	}
	if payload.CPULogical <= 0 || payload.MemoryTotalMiB <= 0 {
		t.Errorf("采集值不应为 0: %+v", payload)
	}
	if len(payload.Storage) != 1 || payload.Storage[0].TotalBytes == 0 {
		t.Errorf("存储采集异常: %+v", payload.Storage)
	}
	if payload.SampledAt.IsZero() {
		t.Error("采样时间不能为空")
	}
}

// TestDomainsEndpointReturnsStates 校验域列表返回归一化状态。
func TestDomainsEndpointReturnsStates(t *testing.T) {
	deps := testDependencies()
	deps.Domains = fakeLister{domains: []libvirt.Domain{{Name: "vm-1", State: libvirt.StateRunning}}}
	router := NewRouter(deps)

	request := httptest.NewRequest(http.MethodGet, "/api/v1/domains", nil)
	request.Header.Set("Authorization", "Bearer "+deps.Token)
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("状态码错误: got=%d", recorder.Code)
	}
	var payload domainsResponse
	if err := json.Unmarshal(recorder.Body.Bytes(), &payload); err != nil {
		t.Fatalf("响应不是合法 JSON: %v", err)
	}
	if len(payload.Domains) != 1 || payload.Domains[0].State != libvirt.StateRunning {
		t.Errorf("域列表错误: %+v", payload.Domains)
	}
}

// TestLibvirtFailureMapsToStableCode 校验 libvirt 不可用映射为 503。
func TestLibvirtFailureMapsToStableCode(t *testing.T) {
	deps := testDependencies()
	deps.Domains = fakeLister{err: apierr.New(apierr.CodeLibvirtUnavailable, "virsh 执行失败", nil)}
	router := NewRouter(deps)

	request := httptest.NewRequest(http.MethodGet, "/api/v1/domains", nil)
	request.Header.Set("Authorization", "Bearer "+deps.Token)
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusServiceUnavailable {
		t.Fatalf("libvirt 不可用应返回 503: got=%d", recorder.Code)
	}
	if !strings.Contains(recorder.Body.String(), "LIBVIRT_UNAVAILABLE") {
		t.Errorf("响应应包含错误码: %s", recorder.Body.String())
	}
}

// TestRequestIDIsEchoed 校验 request_id 生成与复用。
func TestRequestIDIsEchoed(t *testing.T) {
	router := NewRouter(testDependencies())
	request := httptest.NewRequest(http.MethodGet, "/health", nil)
	request.Header.Set("X-Request-ID", "trace-abcdef-123456")

	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	if recorder.Header().Get("X-Request-ID") != "trace-abcdef-123456" {
		t.Errorf("合法 request_id 应被复用: %q", recorder.Header().Get("X-Request-ID"))
	}
}
