package httpapi

import (
	"context"
	"encoding/json"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"net/http"
	"sync"
)

// Deletion is exclusive with managed domain mutations; normal mutations remain parallel.
var diskReferenceMutation sync.RWMutex

func unusedDiskHandler(deps Dependencies) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		fail := func(e error) { writeAPIError(w, deps.Logger, e, RequestIDFromContext(r.Context())) }
		if !deps.AllowDestructive {
			fail(apierr.New(apierr.CodeConflict, "节点未开启磁盘删除操作", nil))
			return
		}
		var body struct {
			Relative string `json:"relative_path"`
		}
		d := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096))
		d.DisallowUnknownFields()
		if e := d.Decode(&body); e != nil || body.Relative == "" {
			fail(apierr.New(apierr.CodeInvalidArgument, "磁盘路径无效", e))
			return
		}
		provider, ok := deps.Virtualizer.(interface {
			RemoveUnusedDisk(context.Context, string, string) error
		})
		if !ok {
			fail(apierr.New(apierr.CodeConflict, "节点未实现保留磁盘清理，请先升级 Agent", nil))
			return
		}
		diskReferenceMutation.Lock()
		defer diskReferenceMutation.Unlock()
		if e := provider.RemoveUnusedDisk(r.Context(), deps.DiskDir, body.Relative); e != nil {
			fail(e)
			return
		}
		writeJSON(w, 200, map[string]any{"relative_path": body.Relative, "deleted": true})
	}
}
