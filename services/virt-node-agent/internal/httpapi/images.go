package httpapi

import (
	"encoding/json"
	"net/http"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/storage"
)

// inspectRequest 是镜像检查请求体。
type inspectRequest struct {
	RelativePath string `json:"relative_path"`
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
		info, err := storage.Inspect(deps.ImageDir, payload.RelativePath)
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
				apierr.CodeConflict, "宿主机未开启破坏性操作开关", nil,
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
		if err := storage.Remove(deps.ImageDir, payload.RelativePath); err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		writeJSON(writer, http.StatusOK, map[string]string{
			"path": payload.RelativePath, "result": "deleted",
		})
	}
}
