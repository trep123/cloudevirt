package httpapi

import (
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/config"
)

// TestHealthEndpoint 校验健康检查返回 200 与版本信息。
func TestHealthEndpoint(t *testing.T) {
	cfg := config.Config{Version: "0.1.0", Listen: "127.0.0.1:9100"}
	router := NewRouter(cfg, slog.Default())

	request := httptest.NewRequest(http.MethodGet, "/health", nil)
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("状态码错误: got=%d want=%d", recorder.Code, http.StatusOK)
	}

	var payload healthResponse
	if err := json.Unmarshal(recorder.Body.Bytes(), &payload); err != nil {
		t.Fatalf("响应不是合法 JSON: %v", err)
	}
	if payload.Status != "ok" || payload.Version != cfg.Version {
		t.Errorf("响应内容错误: %+v", payload)
	}
}

// TestHealthRejectsOtherMethods 校验未注册方法与路径不会被误处理。
func TestHealthRejectsOtherMethods(t *testing.T) {
	router := NewRouter(config.Config{Version: "0.1.0"}, slog.Default())

	request := httptest.NewRequest(http.MethodPost, "/health", nil)
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusMethodNotAllowed && recorder.Code != http.StatusNotFound {
		t.Fatalf("未注册方法应返回 405 或 404，实际为 %d", recorder.Code)
	}
}
