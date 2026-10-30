package httpapi

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/storage"
)

// inspectRequest 是镜像检查请求体。
type inspectRequest struct {
	RelativePath string `json:"relative_path"`
	StoragePool string `json:"storage_pool,omitempty"`
}

// inspectImageHandler 检查镜像文件：路径校验、格式解析与校验和。
func inspectImageHandler(deps Dependencies) http.HandlerFunc {
	return func(writer http.ResponseWriter, request *http.Request) {
		requestID := RequestIDFromContext(request.Context())
		var payload inspectRequest
		if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
			writeAPIError(writer, deps.Logger, apierr.New(
				apierr.CodeInvalidArgument, "请求体解析失败", err,
			), requestID)
			return
		}
		// Hashing a multi-GiB image belongs to a background management task.
		deadline := time.Now().Add(30 * time.Minute)
		_ = http.NewResponseController(writer).SetWriteDeadline(deadline)
		ctx, cancel := context.WithDeadline(request.Context(), deadline)
		defer cancel()
		root, err := imageRootForPool(ctx, deps, payload.StoragePool)
		if err != nil { writeAPIError(writer, deps.Logger, err, requestID); return }
		info, err := storage.InspectContext(ctx, root, payload.RelativePath)
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		writeJSON(writer, http.StatusOK, info)
	}
}

// deleteImageHandler 删除镜像文件，受宿主机破坏性开关约束。
func deleteImageHandler(deps Dependencies) http.HandlerFunc {
	return func(writer http.ResponseWriter, request *http.Request) {
		requestID := RequestIDFromContext(request.Context())
		if !deps.AllowDestructive {
			writeAPIError(writer, deps.Logger, apierr.New(
				apierr.CodeConflict, "节点未开启文件删除；可取消清理文件仅移除记录，或由管理员启用 CLOUDVIRT_ALLOW_DESTRUCTIVE", nil,
			), requestID)
			return
		}
		var payload inspectRequest
		if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
			writeAPIError(writer, deps.Logger, apierr.New(
				apierr.CodeInvalidArgument, "请求体解析失败", err,
			), requestID)
			return
		}
		root, err := imageRootForPool(request.Context(), deps, payload.StoragePool)
		if err != nil { writeAPIError(writer, deps.Logger, err, requestID); return }
		if err := storage.Remove(root, payload.RelativePath); err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		writeJSON(writer, http.StatusOK, map[string]string{
			"path": payload.RelativePath, "result": "deleted",
		})
	}
}
