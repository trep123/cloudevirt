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
		id := RequestIDFromContext(r.Context())
		name := r.PathValue("name")
		fail := func(err error) { writeAPIError(w, deps.Logger, err, id) }
		if !domainxml.ValidName(name) {
			fail(apierr.New(apierr.CodeInvalidArgument, "������Ч", nil))
			return
		}
		provider, ok := deps.Virtualizer.(interface {
			DomainDisplay(context.Context, string) (libvirt.DisplayConfig, error)
			ConfigureDisplay(context.Context, string, libvirt.DisplayConfig) (libvirt.DisplayConfig, error)
		})
		if !ok {
			fail(apierr.New(apierr.CodeConflict, "�ڵ�δ�ṩ�Կ���������", nil))
			return
		}
		var config libvirt.DisplayConfig
		var err error
		if r.Method == http.MethodPost {
			decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 2048))
			decoder.DisallowUnknownFields()
			if err = decoder.Decode(&config); err != nil {
				fail(apierr.New(apierr.CodeInvalidArgument, "��ʾ������Ч", err))
				return
			}
			if !includesCapability(creationCapabilities(deps, r.Context()), "video_models", config.Model) {
				fail(apierr.New(apierr.CodeInvalidArgument, "�ڵ㲻֧�ִ��Կ�", nil))
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
