package httpapi

import (
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
)

// errorResponse 是统一错误响应体，与管理后端结构保持一致。
type errorResponse struct {
	Code      string `json:"code"`
	Message   string `json:"message"`
	RequestID string `json:"request_id"`
}

// statusByCode 是错误码到 HTTP 状态码的集中映射。
var statusByCode = map[apierr.Code]int{
	apierr.CodeUnauthorized:         http.StatusUnauthorized,
	apierr.CodeInvalidArgument:      http.StatusBadRequest,
	apierr.CodeNotFound:             http.StatusNotFound,
	apierr.CodeConflict:             http.StatusConflict,
	apierr.CodeInsufficientResource: http.StatusConflict,
	apierr.CodeLibvirtUnavailable:   http.StatusServiceUnavailable,
	apierr.CodeCommandTimeout:       http.StatusGatewayTimeout,
	apierr.CodeOperationFailed:      http.StatusInternalServerError,
	apierr.CodeInternalError:        http.StatusInternalServerError,
}

// writeError 输出统一错误响应，并记录脱敏后的错误日志。
func writeError(writer http.ResponseWriter, logger *slog.Logger, status int, code apierr.Code, message, requestID string) {
	if logger != nil {
		logger.Warn("请求失败", "code", string(code), "status", status, "request_id", requestID)
	}
	payload := errorResponse{Code: string(code), Message: message, RequestID: requestID}
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(status)
	if err := json.NewEncoder(writer).Encode(payload); err != nil {
		slog.Error("错误响应序列化失败", "error", err)
	}
}

// writeAPIError 把 apierr.Error 映射为 HTTP 响应。
func writeAPIError(writer http.ResponseWriter, logger *slog.Logger, err error, requestID string) {
	var apiError *apierr.Error
	code := apierr.CodeInternalError
	message := "服务器内部错误"
	status := http.StatusInternalServerError
	if errors.As(err, &apiError) {
		code = apiError.Code
		message = apiError.Message
		if mapped, ok := statusByCode[code]; ok {
			status = mapped
		}
	} else if logger != nil {
		logger.Error("未分类错误", "error", err, "request_id", requestID)
	}
	writeError(writer, logger, status, code, message, requestID)
}
