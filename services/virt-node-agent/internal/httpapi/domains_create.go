package httpapi

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/domainxml"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/storage"
)

// DomainOperator 是域操作依赖，便于测试替换真实 libvirt。
type DomainOperator interface {
	DomainExists(ctx context.Context, name string) (bool, error)
	DefineDomain(ctx context.Context, content string) error
	StartDomain(ctx context.Context, name string) error
	DumpXML(ctx context.Context, name string) (string, error)
	DomainState(ctx context.Context, name string) (string, error)
}

// createDomainRequest 是创建域请求体。
type createDomainRequest struct {
	Name             string `json:"name"`
	UUID             string `json:"uuid"`
	VCPU             int    `json:"vcpu"`
	MemoryMiB        int    `json:"memory_mib"`
	DiskRelativePath string `json:"disk_relative_path"`
	DiskGiB          int    `json:"disk_gib"`
	Network          string `json:"network"`
}

// createDomainResponse 是创建域结果。
type createDomainResponse struct {
	UUID                 string `json:"uuid"`
	Name                 string `json:"name"`
	State                string `json:"state"`
	VCPU                 int    `json:"vcpu"`
	MemoryMiB            int    `json:"memory_mib"`
	DiskPath             string `json:"disk_path"`
	DiskVirtualSizeBytes int64  `json:"disk_virtual_size_bytes"`
	Created              bool   `json:"created"`
}

// createDomainHandler 创建并启动域；同名域已存在时按幂等返回现状。
func createDomainHandler(deps Dependencies) http.HandlerFunc {
	return func(writer http.ResponseWriter, request *http.Request) {
		requestID := RequestIDFromContext(request.Context())
		ctx := request.Context()

		var payload createDomainRequest
		if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
			writeAPIError(writer, deps.Logger, apierr.New(
				apierr.CodeInvalidArgument, "请求体解析失败", err,
			), requestID)
			return
		}

		// 磁盘可能尚不存在，使用允许缺失的路径校验
		diskPath, err := storage.SafePathAllowMissing(deps.DiskDir, payload.DiskRelativePath)
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		spec := domainxml.Spec{
			Name:      payload.Name,
			UUID:      payload.UUID,
			VCPU:      payload.VCPU,
			MemoryMiB: payload.MemoryMiB,
			DiskPath:  diskPath,
			Network:   payload.Network,
		}
		if err := domainxml.ValidateSpec(spec); err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}

		if deps.Virtualizer == nil {
			writeAPIError(writer, deps.Logger, errNoVirtualizer, requestID)
			return
		}

		// 幂等：已存在同名域时直接返回现状，避免重复创建
		exists, err := deps.Virtualizer.DomainExists(ctx, payload.Name)
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		if exists {
			writeExistingDomain(writer, deps, ctx, payload, requestID)
			return
		}

		if err := storage.CreateDisk(ctx, diskPath, payload.DiskGiB); err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		format, virtualSize, err := storage.DiskInfo(ctx, diskPath)
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		if strings.ToUpper(format) != strings.ToUpper(domainxml.DiskFormat) {
			writeAPIError(writer, deps.Logger, apierr.New(
				apierr.CodeOperationFailed, "磁盘格式与预期不符", nil,
			), requestID)
			return
		}

		content, err := domainxml.Build(spec)
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		if err := deps.Virtualizer.DefineDomain(ctx, content); err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		if err := deps.Virtualizer.StartDomain(ctx, payload.Name); err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}

		dump, err := deps.Virtualizer.DumpXML(ctx, payload.Name)
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		actual, err := domainxml.Parse(dump)
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		if actual.UUID != payload.UUID || actual.MemoryMiB != payload.MemoryMiB || actual.VCPU != payload.VCPU {
			writeAPIError(writer, deps.Logger, apierr.New(
				apierr.CodeConflict, "创建结果与请求规格不一致", nil,
			), requestID)
			return
		}

		state, err := deps.Virtualizer.DomainState(ctx, payload.Name)
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		writeJSON(writer, http.StatusCreated, createDomainResponse{
			UUID:                 actual.UUID,
			Name:                 actual.Name,
			State:                state,
			VCPU:                 actual.VCPU,
			MemoryMiB:            actual.MemoryMiB,
			DiskPath:             diskPath,
			DiskVirtualSizeBytes: virtualSize,
			Created:              true,
		})
	}
}

// writeExistingDomain 返回已存在域的现状（幂等路径）。
func writeExistingDomain(writer http.ResponseWriter, deps Dependencies, ctx context.Context, payload createDomainRequest, requestID string) {
	dump, err := deps.Virtualizer.DumpXML(ctx, payload.Name)
	if err != nil {
		writeAPIError(writer, deps.Logger, err, requestID)
		return
	}
	actual, err := domainxml.Parse(dump)
	if err != nil {
		writeAPIError(writer, deps.Logger, err, requestID)
		return
	}
	if actual.UUID != payload.UUID {
		writeAPIError(writer, deps.Logger, apierr.New(
			apierr.CodeConflict, "同名域存在但 UUID 不一致", nil,
		), requestID)
		return
	}
	state, err := deps.Virtualizer.DomainState(ctx, payload.Name)
	if err != nil {
		writeAPIError(writer, deps.Logger, err, requestID)
		return
	}
	var virtualSize int64
	if _, size, infoErr := storage.DiskInfo(ctx, actual.DiskPath); infoErr == nil {
		virtualSize = size
	}
	writeJSON(writer, http.StatusOK, createDomainResponse{
		UUID:                 actual.UUID,
		Name:                 actual.Name,
		State:                state,
		VCPU:                 actual.VCPU,
		MemoryMiB:            actual.MemoryMiB,
		DiskPath:             actual.DiskPath,
		DiskVirtualSizeBytes: virtualSize,
		Created:              false,
	})
}
