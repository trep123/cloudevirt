package httpapi

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/storage"
)

// diskListResponse 是磁盘清单响应。
type diskListResponse struct {
	Directory string             `json:"directory"`
	Disks     []storage.DiskFile `json:"disks"`
	SampledAt time.Time          `json:"sampled_at"`
}

// diskListHandler 列出磁盘目录下的文件，供后端做孤儿检测。
func diskListHandler(deps Dependencies) http.HandlerFunc {
	return func(writer http.ResponseWriter, request *http.Request) {
		requestID := RequestIDFromContext(request.Context())
		if deps.DiskDir == "" {
			writeAPIError(writer, deps.Logger, apierr.New(
				apierr.CodeInternalError, "磁盘目录未配置", nil,
			), requestID)
			return
		}
		diskRoot, err := diskRootForPool(request.Context(), deps, request.URL.Query().Get("storage_pool"))
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		files, err := storage.ListDiskFiles(request.Context(), diskRoot)
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		if files == nil {
			files = []storage.DiskFile{}
		}
		writeJSON(writer, http.StatusOK, diskListResponse{
			Directory: diskRoot, Disks: files, SampledAt: time.Now().UTC(),
		})
	}
}

func inspectExistingDiskHandler(deps Dependencies) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			Relative string `json:"relative_path"`
			StoragePool string `json:"storage_pool"`
		}
		d := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096))
		d.DisallowUnknownFields()
		fail := func(err error) { writeAPIError(w, deps.Logger, err, RequestIDFromContext(r.Context())) }
		if err := d.Decode(&body); err != nil || body.Relative == "" {
			fail(apierr.New(apierr.CodeInvalidArgument, "请指定系统盘相对路径", err))
			return
		}
		diskReferenceMutation.RLock()
		defer diskReferenceMutation.RUnlock()
		diskRoot, rootErr := diskRootForPool(r.Context(), deps, body.StoragePool)
		if rootErr != nil {
			fail(rootErr)
			return
		}
		checker, ok := deps.Virtualizer.(interface {
			CheckUnusedDisk(context.Context, string, string) error
		})
		if !ok {
			fail(apierr.New(apierr.CodeConflict, "节点不支持磁盘引用检查", nil))
			return
		}
		if err := checker.CheckUnusedDisk(r.Context(), diskRoot, body.Relative); err != nil {
			fail(err)
			return
		}
		info, err := storage.InspectExistingDisk(r.Context(), diskRoot, body.Relative)
		if err != nil {
			fail(err)
			return
		}
		writeJSON(w, 200, info)
	}
}
