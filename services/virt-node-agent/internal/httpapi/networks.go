package httpapi

import (
	"context"
	"net/http"
	"time"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/libvirt"
)

// NetworkLister 是网络查询依赖，便于测试替换。
type NetworkLister interface {
	ListNetworks(ctx context.Context) ([]libvirt.Network, error)
	NetworkExists(ctx context.Context, name string) (bool, error)
}

// networkPayload 是单个网络信息。
type networkPayload struct {
	Name   string `json:"name"`
	Active bool   `json:"active"`
}

// networkListResponse 是网络列表响应。
type networkListResponse struct {
	Networks  []networkPayload `json:"networks"`
	SampledAt time.Time        `json:"sampled_at"`
}

// networkListHandler 返回本机 libvirt 网络列表。
func networkListHandler(deps Dependencies) http.HandlerFunc {
	return func(writer http.ResponseWriter, request *http.Request) {
		requestID := RequestIDFromContext(request.Context())
		if deps.Networks == nil {
			writeAPIError(writer, deps.Logger, apierr.New(
				apierr.CodeInternalError, "网络查询依赖未初始化", nil,
			), requestID)
			return
		}
		networks, err := deps.Networks.ListNetworks(request.Context())
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		payload := networkListResponse{SampledAt: time.Now().UTC()}
		for _, item := range networks {
			payload.Networks = append(payload.Networks, networkPayload{
				Name: item.Name, Active: item.Active,
			})
		}
		writeJSON(writer, http.StatusOK, payload)
	}
}
