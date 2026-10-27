package httpapi

import (
	"net/http"
	"time"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/storage"
)

// diskListResponse 是磁盘清单响应。
type diskListResponse struct {
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
		files, err := storage.ListDiskFiles(request.Context(), deps.DiskDir)
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		if files == nil {
			files = []storage.DiskFile{}
		}
		writeJSON(writer, http.StatusOK, diskListResponse{
			Disks: files, SampledAt: time.Now().UTC(),
		})
	}
}
