package httpapi

import (
	"context"
	"encoding/json"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/domainxml"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/libvirt"
	"net/http"
)

func displayHandler(deps Dependencies) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		diskReferenceMutation.RLock()
		defer diskReferenceMutation.RUnlock()
		id := RequestIDFromContext(r.Context())
		name := r.PathValue("name")
		unlock := lockCreation(name)
		defer unlock()
		fail := func(err error) { writeAPIError(w, deps.Logger, err, id) }
		if !domainxml.ValidName(name) {
			fail(apierr.New(apierr.CodeInvalidArgument, "域名无效", nil))
			return
		}
		provider, ok := deps.Virtualizer.(interface {
			DomainDisplay(context.Context, string) (libvirt.DisplayConfig, error)
			ConfigureDisplay(context.Context, string, libvirt.DisplayConfig) (libvirt.DisplayConfig, error)
		})
		if !ok {
			fail(apierr.New(apierr.CodeConflict, "节点未提供显卡配置能力", nil))
			return
		}
		var config libvirt.DisplayConfig
		var err error
		if r.Method == http.MethodPost {
			decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 2048))
			decoder.DisallowUnknownFields()
			if err = decoder.Decode(&config); err != nil {
				fail(apierr.New(apierr.CodeInvalidArgument, "显示配置无效", err))
				return
			}
			if !includesCapability(creationCapabilities(deps, r.Context()), "video_models", config.Model) {
				fail(apierr.New(apierr.CodeInvalidArgument, "节点不支持此显卡", nil))
				return
			}
			if config.Clipboard && creationCapabilities(deps, r.Context())["clipboard"] != true {
				fail(apierr.New(apierr.CodeInvalidArgument, "节点不支持剪贴板通道", nil))
				return
			}
			config, err = provider.ConfigureDisplay(r.Context(), name, config)
		} else {
			config, err = provider.DomainDisplay(r.Context(), name)
		}
		if err != nil {
			fail(err)
			return
		}
		writeJSON(w, http.StatusOK, config)
	}
}
