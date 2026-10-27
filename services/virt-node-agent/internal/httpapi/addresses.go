package httpapi

import (
	"net/http"
	"time"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/domainxml"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/libvirt"
)

// domainAddressResponse 是域网卡地址响应。
type domainAddressResponse struct {
	Addresses []libvirt.DomainAddress `json:"addresses"`
	FetchedAt time.Time               `json:"fetched_at"`
}

// domainAddressesHandler 返回域内网卡的 IPv4/IPv6 地址。
func domainAddressesHandler(deps Dependencies) http.HandlerFunc {
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
		addresses, err := deps.Virtualizer.DomainAddresses(request.Context(), name)
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		writeJSON(writer, http.StatusOK, domainAddressResponse{
			Addresses: addresses,
			FetchedAt: time.Now().UTC(),
		})
	}
}
