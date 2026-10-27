package httpapi

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/libvirt"
)

// TestDomainInterfacesHandler 校验域网卡接口返回。
func TestDomainInterfacesHandler(t *testing.T) {
	deps := Dependencies{Virtualizer: &fakeOperator{interfaces: []libvirt.DomainInterface{
		{Name: "vnet0", Type: "bridge", Source: "ovsbr0", Model: "virtio", MAC: "52:54:00:aa:bb:cc"},
	}}}
	request := httptest.NewRequest(http.MethodGet, "/api/v1/domains/cv-test/interfaces", nil)
	request.SetPathValue("name", "cv-test")
	recorder := httptest.NewRecorder()

	domainInterfacesHandler(deps)(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("状态码错误: %d", recorder.Code)
	}
	var body domainInterfacesResponse
	if err := json.Unmarshal(recorder.Body.Bytes(), &body); err != nil {
		t.Fatalf("响应解析失败: %v", err)
	}
	if len(body.Interfaces) != 1 || body.Interfaces[0].Source != "ovsbr0" {
		t.Fatalf("接口内容错误: %+v", body.Interfaces)
	}
}
