package httpapi

import (
	"context"
	"encoding/json"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/domainxml"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/libvirt"
	"net/http"
	"os"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/storage"
)

func hardwareHandler(deps Dependencies) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		diskReferenceMutation.RLock()
		defer diskReferenceMutation.RUnlock()
		id := RequestIDFromContext(r.Context())
		fail := func(err error) { writeAPIError(w, deps.Logger, err, id) }
		name := r.PathValue("name")
		unlock := lockCreation(name)
		defer unlock()
		if !domainxml.ValidName(name) {
			fail(apierr.New(apierr.CodeInvalidArgument, "域名无效", nil))
			return
		}
		diskRoot, rootErr := diskRootForPool(r.Context(), deps, r.URL.Query().Get("storage_pool"))
		if rootErr != nil {
			fail(rootErr)
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
			if payload.Operation == "cdrom-set" {
				root, e := imageRootForPool(r.Context(), deps, payload.ImageStoragePool)
				if e != nil { fail(e); return }
				path, e := storage.SafePath(root, payload.ImageRelativePath)
				if e != nil { fail(e); return }
				file, e := os.Open(path)
				if e != nil { fail(apierr.New(apierr.CodeConflict, "ISO 无法读取", e)); return }
				signature := make([]byte, 5)
				_, e = file.ReadAt(signature, 32769)
				file.Close()
				if e != nil || string(signature) != "CD001" { fail(apierr.New(apierr.CodeInvalidArgument, "安装介质不是有效 ISO9660 镜像", e)); return }
				payload.MediaPath = path
			}
			result, err = provider.ChangeHardware(r.Context(), name, diskRoot, payload)
		} else {
			result, err = provider.HardwareInventory(r.Context(), name, diskRoot)
		}
		if err != nil {
			fail(err)
			return
		}
		writeJSON(w, http.StatusOK, result)
	}
}
