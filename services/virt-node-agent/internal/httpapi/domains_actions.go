package httpapi

import (
	"net/http"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/domainxml"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/storage"
)

// domainActionResponse 是域操作结果。
type domainActionResponse struct {
	Name   string `json:"name"`
	State  string `json:"state"`
	Action string `json:"action"`
}

// domainActionHandler 执行启动/关机/强停/重启，并返回操作后的状态。
func domainActionHandler(deps Dependencies, action string) http.HandlerFunc {
	return func(writer http.ResponseWriter, request *http.Request) {
		requestID := RequestIDFromContext(request.Context())
		name := request.PathValue("name")
		if !domainxml.ValidName(name) {
			writeAPIError(writer, deps.Logger, apierr.New(
				apierr.CodeInvalidArgument, "域名格式非法", nil,
			), requestID)
			return
		}
		if deps.Virtualizer == nil {
			writeAPIError(writer, deps.Logger, errNoVirtualizer, requestID)
			return
		}

		ctx := request.Context()
		var err error
		switch action {
		case "start":
			err = deps.Virtualizer.StartDomain(ctx, name)
		case "shutdown":
			err = deps.Virtualizer.ShutdownDomain(ctx, name)
		case "force-stop":
			err = deps.Virtualizer.DestroyDomain(ctx, name)
		case "reboot":
			err = deps.Virtualizer.RebootDomain(ctx, name)
		default:
			err = apierr.New(apierr.CodeInternalError, "未知操作", nil)
		}
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		state, err := deps.Virtualizer.DomainState(ctx, name)
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		writeJSON(writer, http.StatusOK, domainActionResponse{Name: name, State: state, Action: action})
	}
}

// deleteDomainHandler 删除域定义，并按参数决定是否删除磁盘文件。
func deleteDomainHandler(deps Dependencies) http.HandlerFunc {
	return func(writer http.ResponseWriter, request *http.Request) {
		requestID := RequestIDFromContext(request.Context())
		ctx := request.Context()
		name := request.PathValue("name")
		if !domainxml.ValidName(name) {
			writeAPIError(writer, deps.Logger, apierr.New(
				apierr.CodeInvalidArgument, "域名格式非法", nil,
			), requestID)
			return
		}
		if deps.Virtualizer == nil {
			writeAPIError(writer, deps.Logger, errNoVirtualizer, requestID)
			return
		}

		state, err := deps.Virtualizer.DomainState(ctx, name)
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		// 运行中的域先强制关闭，避免 undefine 失败留下不可控状态
		if state == "RUNNING" || state == "PAUSED" {
			if err := deps.Virtualizer.DestroyDomain(ctx, name); err != nil {
				writeAPIError(writer, deps.Logger, err, requestID)
				return
			}
		}
		if err := deps.Virtualizer.UndefineDomain(ctx, name); err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}

		diskRemoved := false
		if relative := request.URL.Query().Get("disk_relative_path"); relative != "" {
			if !deps.AllowDestructive {
				writeAPIError(writer, deps.Logger, apierr.New(
					apierr.CodeConflict, "宿主机未开启破坏性操作开关", nil,
				), requestID)
				return
			}
			if err := storage.Remove(deps.DiskDir, relative); err != nil {
				writeAPIError(writer, deps.Logger, err, requestID)
				return
			}
			diskRemoved = true
		}

		writeJSON(writer, http.StatusOK, map[string]any{
			"name": name, "result": "deleted", "disk_removed": diskRemoved,
		})
	}
}
