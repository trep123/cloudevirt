package httpapi

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/libvirt"
)

// fakeOperator 记录调用并返回可控结果。
type fakeOperator struct {
	exists     bool
	state      string
	dumpXML    string
	existsErr  error
	defineErr  error
	startErr   error
	defineCall int
	startCall  int
}

func (f *fakeOperator) DomainExists(ctx context.Context, name string) (bool, error) {
	return f.exists, f.existsErr
}

func (f *fakeOperator) DefineDomain(ctx context.Context, content string) error {
	f.defineCall++
	return f.defineErr
}

func (f *fakeOperator) StartDomain(ctx context.Context, name string) error {
	f.startCall++
	return f.startErr
}

func (f *fakeOperator) DumpXML(ctx context.Context, name string) (string, error) {
	return f.dumpXML, nil
}

func (f *fakeOperator) DomainState(ctx context.Context, name string) (string, error) {
	return f.state, nil
}

func createPayload(t *testing.T) string {
	t.Helper()
	body := map[string]any{
		"name":               "cv-test01",
		"uuid":               "0f6f2b1e-3333-4a44-9f55-000000000003",
		"vcpu":               2,
		"memory_mib":         512,
		"disk_relative_path": "cv-test01.qcow2",
		"disk_gib":           1,
	}
	encoded, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("构造请求失败: %v", err)
	}
	return string(encoded)
}

// fakeDump 构造 dumpxml 风格响应（内存以 KiB 表示）。
func fakeDump() string {
	return `<domain type="kvm">
  <name>cv-test01</name>
  <uuid>0f6f2b1e-3333-4a44-9f55-000000000003</uuid>
  <memory unit="KiB">524288</memory>
  <vcpu>2</vcpu>
  <devices>
    <disk type="file" device="disk">
      <source file="/tmp/cv-test01.qcow2"/>
      <target dev="vda" bus="virtio"/>
    </disk>
  </devices>
</domain>`
}

// TestCreateDomainRejectsTraversal 校验越界磁盘路径被拒绝。
func TestCreateDomainRejectsTraversal(t *testing.T) {
	deps := testDependencies()
	deps.DiskDir = t.TempDir()
	deps.Virtualizer = &fakeOperator{}
	router := NewRouter(deps)

	body := strings.Replace(createPayload(t), "cv-test01.qcow2", "../escape.qcow2", 1)
	request := httptest.NewRequest(http.MethodPost, "/api/v1/domains", strings.NewReader(body))
	request.Header.Set("Authorization", "Bearer "+deps.Token)
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("越界路径应返回 400: got=%d body=%s", recorder.Code, recorder.Body.String())
	}
}

// TestCreateDomainRejectsInvalidSpec 校验非法规格被拒绝。
func TestCreateDomainRejectsInvalidSpec(t *testing.T) {
	deps := testDependencies()
	deps.DiskDir = t.TempDir()
	deps.Virtualizer = &fakeOperator{}
	router := NewRouter(deps)

	body := strings.Replace(createPayload(t), `"vcpu":2`, `"vcpu":0`, 1)
	request := httptest.NewRequest(http.MethodPost, "/api/v1/domains", strings.NewReader(body))
	request.Header.Set("Authorization", "Bearer "+deps.Token)
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("非法规格应返回 400: got=%d", recorder.Code)
	}
}

// TestCreateDomainIdempotent 校验同名域已存在时不重复定义。
func TestCreateDomainIdempotent(t *testing.T) {
	operator := &fakeOperator{exists: true, state: libvirt.StateRunning, dumpXML: fakeDump()}
	deps := testDependencies()
	deps.DiskDir = t.TempDir()
	deps.Virtualizer = operator
	router := NewRouter(deps)

	request := httptest.NewRequest(http.MethodPost, "/api/v1/domains", strings.NewReader(createPayload(t)))
	request.Header.Set("Authorization", "Bearer "+deps.Token)
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("已存在应返回 200: got=%d body=%s", recorder.Code, recorder.Body.String())
	}
	if operator.defineCall != 0 || operator.startCall != 0 {
		t.Errorf("不应重复定义或启动域: define=%d start=%d", operator.defineCall, operator.startCall)
	}
	var payload createDomainResponse
	if err := json.Unmarshal(recorder.Body.Bytes(), &payload); err != nil {
		t.Fatalf("响应不是合法 JSON: %v", err)
	}
	if payload.Created {
		t.Error("幂等路径 created 应为 false")
	}
	if payload.MemoryMiB != 512 {
		t.Errorf("内存应按 KiB 归一化为 MiB: got=%d", payload.MemoryMiB)
	}
}

// TestCreateDomainLibvirtFailure 校验 libvirt 失败映射为稳定错误码。
func TestCreateDomainLibvirtFailure(t *testing.T) {
	operator := &fakeOperator{defineErr: apierr.New(apierr.CodeLibvirtUnavailable, "virsh 执行失败", nil)}
	deps := testDependencies()
	deps.DiskDir = t.TempDir()
	deps.Virtualizer = operator
	router := NewRouter(deps)

	request := httptest.NewRequest(http.MethodPost, "/api/v1/domains", strings.NewReader(createPayload(t)))
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

// TestCreateDomainRequiresVirtualizer 校验未注入依赖时返回内部错误。
func TestCreateDomainRequiresVirtualizer(t *testing.T) {
	deps := testDependencies()
	deps.DiskDir = t.TempDir()
	deps.Virtualizer = nil
	router := NewRouter(deps)

	request := httptest.NewRequest(http.MethodPost, "/api/v1/domains", strings.NewReader(createPayload(t)))
	request.Header.Set("Authorization", "Bearer "+deps.Token)
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusInternalServerError {
		t.Fatalf("缺少依赖应返回 500: got=%d", recorder.Code)
	}
}
