// Package httpapi 提供节点 Agent 的 HTTP 路由、中间件与响应结构。
package httpapi

import (
	"encoding/json"
	"log/slog"
	"net/http"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/config"
)

// healthResponse 是健康检查响应体。
type healthResponse struct {
	Status  string `json:"status"`
	Version string `json:"version"`
}

// NewRouter 注册全部路由并返回处理器。
func NewRouter(cfg config.Config, logger *slog.Logger) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(writer http.ResponseWriter, request *http.Request) {
		writeJSON(writer, http.StatusOK, healthResponse{Status: "ok", Version: cfg.Version})
		logger.Info("健康检查", "remote_addr", request.RemoteAddr, "result", "ok")
	})
	return mux
}

// writeJSON 写入 JSON 响应，统一设置 Content-Type。
func writeJSON(writer http.ResponseWriter, status int, payload any) {
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(status)
	if err := json.NewEncoder(writer).Encode(payload); err != nil {
		slog.Error("响应序列化失败", "error", err)
	}
}
