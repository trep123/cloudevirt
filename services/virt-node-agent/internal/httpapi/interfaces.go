package httpapi

import (
	"net/http"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/domainxml"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/libvirt"
)

// domainInterfacesResponse 是域网卡列表响应。
type domainInterfacesResponse struct {
	Interfaces []libvirt.DomainInterface `json:"interfaces"`
}

// domainInterfacesHandler 返回域网卡信息。
func domainInterfacesHandler(deps Dependencies) http.HandlerFunc {
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
		interfaces, err := deps.Virtualizer.DomainInterfaces(request.Context(), name)
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		writeJSON(writer, http.StatusOK, domainInterfacesResponse{Interfaces: interfaces})
	}
}
