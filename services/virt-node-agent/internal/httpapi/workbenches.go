package httpapi

import (
	"context"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"time"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
)

type workspaceStatus struct {
	State      string `json:"state"`
	Generation string `json:"generation,omitempty"`
	Port       int    `json:"port,omitempty"`
	Error      string `json:"error,omitempty"`
}

func workspaceOperation(ctx context.Context, operation, id string, body []byte) (workspaceStatus, error) {
	var result workspaceStatus
	if !consoleID.MatchString(id) {
		return result, apierr.New(apierr.CodeInvalidArgument, "工作台 ID 无效", nil)
	}
	ctx, cancel := context.WithTimeout(ctx, 24*time.Second)
	defer cancel()
	connection, err := (&net.Dialer{}).DialContext(ctx, "unix", "/run/cloudvirt-workbench/control.sock")
	if err != nil {
		return result, apierr.New(apierr.CodeOperationFailed, "工作台组件尚未配置或未启动", nil)
	}
	defer connection.Close()
	_ = connection.SetDeadline(time.Now().Add(24 * time.Second))
	var spec any
	if len(body) > 0 && json.Unmarshal(body, &spec) != nil {
		return result, apierr.New(apierr.CodeInvalidArgument, "工作台参数无效", nil)
	}
	if json.NewEncoder(connection).Encode(map[string]any{"operation": operation, "identity": id, "spec": spec}) != nil {
		return result, apierr.New(apierr.CodeOperationFailed, "工作台组件连接中断", nil)
	}
	output, err := io.ReadAll(io.LimitReader(connection, 16385))
	if err != nil || len(output) > 16384 || json.Unmarshal(output, &result) != nil {
		return result, apierr.New(apierr.CodeOperationFailed, "工作台组件执行失败，请检查安装和服务日志", nil)
	}
	return result, nil
}

func workspacePort(ctx context.Context, id, generation string) (int, error) {
	result, err := workspaceOperation(ctx, "status", id, nil)
	if err != nil {
		return 0, err
	}
	if result.State != "READY" || result.Generation != generation || result.Port < 1024 || result.Port > 65535 {
		return 0, apierr.New(apierr.CodeOperationFailed, "工作台未就绪或已重建", nil)
	}
	return result.Port, nil
}

func workspaceHandler(deps Dependencies) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		operation := "status"
		var body []byte
		switch r.Method {
		case http.MethodPost:
			operation = "start"
			var err error
			body, err = io.ReadAll(http.MaxBytesReader(w, r.Body, 16384))
			if err != nil || !json.Valid(body) {
				writeAPIError(w, deps.Logger, apierr.New(apierr.CodeInvalidArgument, "工作台参数无效", nil), RequestIDFromContext(r.Context()))
				return
			}
		case http.MethodDelete:
			operation = "stop"
		}
		result, err := workspaceOperation(r.Context(), operation, r.PathValue("id"), body)
		if err != nil {
			writeAPIError(w, deps.Logger, err, RequestIDFromContext(r.Context()))
			return
		}
		writeJSON(w, http.StatusOK, result)
	}
}
