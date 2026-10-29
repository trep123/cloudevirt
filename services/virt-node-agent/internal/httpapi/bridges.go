package httpapi

import (
	"context"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/hostbridge"
	"io"
	"net"
	"net/http"
	"time"
)

func bridgeProxyHandler(deps Dependencies) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		transport := &http.Transport{DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
			return (&net.Dialer{}).DialContext(ctx, "unix", hostbridge.Socket)
		}}
		defer transport.CloseIdleConnections()
		ctx, cancel := context.WithTimeout(r.Context(), 28*time.Second)
		defer cancel()
		upstream, err := http.NewRequestWithContext(ctx, r.Method, "http://network-helper"+r.URL.Path, http.MaxBytesReader(w, r.Body, 4096))
		if err == nil {
			upstream.Header.Set("Content-Type", "application/json")
			var response *http.Response
			response, err = (&http.Client{Transport: transport}).Do(upstream)
			if err == nil {
				defer response.Body.Close()
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(response.StatusCode)
				io.Copy(w, io.LimitReader(response.Body, 128*1024))
				return
			}
		}
		writeAPIError(w, deps.Logger, apierr.New(apierr.CodeConflict, "节点网络管理组件未启用或不可达，请启动 cloudvirt-network 服务", err), RequestIDFromContext(r.Context()))
	}
}
