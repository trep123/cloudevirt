package httpapi

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/libvirt"
)

// TestDomainAddressesHandler 校验地址接口返回 IPv4 与 IPv6。
func TestDomainAddressesHandler(t *testing.T) {
	deps := Dependencies{
		Virtualizer: &fakeOperator{addresses: []libvirt.DomainAddress{
			{Interface: "vnet0", MAC: "52:54:00:aa:bb:cc", Protocol: "ipv4", Address: "192.168.122.10", Prefix: "24"},
			{Interface: "vnet0", MAC: "52:54:00:aa:bb:cc", Protocol: "ipv6", Address: "fd00::10", Prefix: "64"},
		}},
	}
	request := httptest.NewRequest(http.MethodGet, "/api/v1/domains/cv-test/addresses", nil)
	request.SetPathValue("name", "cv-test")
	recorder := httptest.NewRecorder()

	domainAddressesHandler(deps)(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("状态码错误: %d", recorder.Code)
	}
	var body domainAddressResponse
	if err := json.Unmarshal(recorder.Body.Bytes(), &body); err != nil {
		t.Fatalf("响应解析失败: %v", err)
	}
	if len(body.Addresses) != 2 {
		t.Fatalf("地址数量错误: %d", len(body.Addresses))
	}
	if body.Addresses[1].Protocol != "ipv6" {
		t.Errorf("IPv6 协议错误: %+v", body.Addresses[1])
	}
}
