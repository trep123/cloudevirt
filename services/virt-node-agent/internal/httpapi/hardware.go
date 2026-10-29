package httpapi

import (
	"context"
	"encoding/json"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/domainxml"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/libvirt"
	"net/http"
)

func hardwareHandler(deps Dependencies) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := RequestIDFromContext(r.Context())
		fail := func(err error) { writeAPIError(w, deps.Logger, err, id) }
		name := r.PathValue("name")
		if !domainxml.ValidName(name) {
			fail(apierr.New(apierr.CodeInvalidArgument, "域名无效", nil))
			return
		}
		provider, ok := deps.Virtualizer.(interface {
			HardwareInventory(context.Context, string, string) (libvirt.HardwareInventory, error)
			ChangeHardware(context.Context, string, string, libvirt.HardwareChange) (libvirt.HardwareInventory, error)
		})
		if !ok {
			fail(apierr.New(apierr.CodeConflict, "节点尚未提供硬件管理能力", nil))
			return
		}
		var result libvirt.HardwareInventory
		var err error
		if r.Method == http.MethodPost {
			var payload libvirt.HardwareChange
			decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 8192))
			decoder.DisallowUnknownFields()
			if err = decoder.Decode(&payload); err != nil {
				fail(apierr.New(apierr.CodeInvalidArgument, "硬件参数无效", err))
				return
			}
			result, err = provider.ChangeHardware(r.Context(), name, deps.DiskDir, payload)
		} else {
			result, err = provider.HardwareInventory(r.Context(), name, deps.DiskDir)
		}
		if err != nil {
			fail(err)
			return
		}
		writeJSON(w, http.StatusOK, result)
	}
}
