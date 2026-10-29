package httpapi

import (
	"context"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"net/http"
	"os/exec"
)

func creationCapabilities(deps Dependencies, ctx context.Context) map[string]any {
	caps := map[string]any{"creation_schema": 1, "image_clone": true, "iso_install": true, "start_control": true, "multi_disk": true, "multi_nic": true, "cloud_init": false, "pci_passthrough": false, "cpu_modes": []string{}, "firmware": []string{"bios"}, "secure_boot": false, "tpm_emulator": false, "performance_limits": true, "numa": false, "hugepages": false}
	if provider, ok := deps.Virtualizer.(interface {
		CreationCapabilities(context.Context) (map[string]any, error)
	}); ok {
		extra, err := provider.CreationCapabilities(ctx)
		if err == nil {
			for key, value := range extra {
				caps[key] = value
			}
		} else {
			caps["hardware_probe_failed"] = true
		}
	}
	_, err := exec.LookPath("genisoimage")
	caps["cloud_init"] = err == nil
	caps["static_networks"] = err == nil
	return caps
}
func creationCapabilitiesHandler(deps Dependencies) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, creationCapabilities(deps, r.Context()))
	}
}
func includesCapability(caps map[string]any, key, value string) bool {
	values, _ := caps[key].([]string)
	for _, item := range values {
		if item == value {
			return true
		}
	}
	return false
}
func checkHardwareCapabilities(deps Dependencies, ctx context.Context, payload createDomainRequest) error {
	h := payload.Hardware
	caps := creationCapabilities(deps, ctx)
	if payload.Initialization != nil && caps["cloud_init"] != true {
		return apierr.New(apierr.CodeInvalidArgument, "节点未安装 genisoimage，无法生成初始化介质", nil)
	}
	mode := h.CPUMode
	if mode == "" && (h.Sockets != 0 || h.Cores != 0 || h.Threads != 0) {
		mode = "host-model"
	}
	if mode != "" && !includesCapability(caps, "cpu_modes", mode) {
		return apierr.New(apierr.CodeInvalidArgument, "节点不支持所选 CPU 模式", nil)
	}
	if h.Firmware != "" && !includesCapability(caps, "firmware", h.Firmware) {
		return apierr.New(apierr.CodeInvalidArgument, "节点不支持所选固件", nil)
	}
	if h.SecureBoot && caps["secure_boot"] != true {
		return apierr.New(apierr.CodeInvalidArgument, "节点未检测到 Secure Boot 固件", nil)
	}
	if h.TPM && caps["tpm_emulator"] != true {
		return apierr.New(apierr.CodeInvalidArgument, "节点不支持 TPM 模拟器", nil)
	}
	return nil
}
