package httpapi

import (
	"context"
	"encoding/json"
	"net/http"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/libvirt"
)

type infrastructureOperator interface {
	ListStoragePools(context.Context) ([]libvirt.StoragePool, error)
	CreateDirectoryPool(context.Context, string, string) error
	ListSnapshots(context.Context, string) ([]libvirt.Snapshot, error)
	SnapshotAction(context.Context, string, string, string, string) error
}

func storagePoolVolumesHandler(deps Dependencies) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		requestID := RequestIDFromContext(r.Context())
		name := r.PathValue("name")
		root, err := diskRootForPool(r.Context(), deps, name)
		if err != nil {
			writeAPIError(w, deps.Logger, err, requestID)
			return
		}
		lister, ok := deps.Virtualizer.(interface {
			ListStorageVolumes(context.Context, string) ([]libvirt.StorageVolume, bool, error)
		})
		if !ok {
			writeAPIError(w, deps.Logger, apierr.New(apierr.CodeConflict, "节点尚未提供存储卷浏览能力", nil), requestID)
			return
		}
		volumes, truncated, err := lister.ListStorageVolumes(r.Context(), root)
		if err != nil {
			writeAPIError(w, deps.Logger, err, requestID)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{
			"pool": name, "path": root, "results": volumes, "truncated": truncated, "sampled_at": time.Now().UTC(),
		})
	}
}

// Serialize infrastructure mutations within this Agent process.
var infrastructureMutation sync.Mutex

func infrastructureHandler(deps Dependencies, snapshots bool) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		diskReferenceMutation.RLock()
		defer diskReferenceMutation.RUnlock()
		requestID := RequestIDFromContext(r.Context())
		operator, ok := deps.Virtualizer.(infrastructureOperator)
		if !ok {
			writeAPIError(w, deps.Logger, errNoVirtualizer, requestID)
			return
		}
		fail := func(err error) { writeAPIError(w, deps.Logger, err, requestID) }
		diskRoot := deps.DiskDir
		if snapshots {
			unlock := lockCreation(r.PathValue("name"))
			defer unlock()
			var rootErr error
			diskRoot, rootErr = diskRootForPool(r.Context(), deps, r.URL.Query().Get("storage_pool"))
			if rootErr != nil {
				fail(rootErr)
				return
			}
		}
		if r.Method == http.MethodGet {
			if snapshots {
				result, err := operator.ListSnapshots(r.Context(), r.PathValue("name"))
				if err != nil {
					fail(err)
					return
				}
				writeJSON(w, 200, map[string]any{"results": result, "sampled_at": time.Now().UTC(), "write_mode": "offline-internal-qcow2", "allow_destructive": deps.AllowDestructive})
			} else {
				result, err := operator.ListStoragePools(r.Context())
				if err != nil {
					fail(err)
					return
				}
				roots := deps.StorageRoots
				if len(roots) == 0 {
					roots = []string{deps.DiskDir}
				}
				writeJSON(w, 200, map[string]any{"results": result, "sampled_at": time.Now().UTC(), "creatable_types": []string{"dir"}, "storage_roots": roots, "default_directory": deps.DiskDir})
			}
			return
		}
		var body struct {
			Name   string `json:"name"`
			Action string `json:"action"`
			Path   string `json:"path"`
		}
		decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096))
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&body); err != nil {
			fail(apierr.New(apierr.CodeInvalidArgument, "请求格式无效", nil))
			return
		}
		infrastructureMutation.Lock()
		defer infrastructureMutation.Unlock()
		if !snapshots {
			switch body.Action {
			case "delete":
				root, err := diskRootForPool(r.Context(), deps, body.Name)
				if err != nil || root != body.Path {
					fail(apierr.New(apierr.CodeConflict, "存储池目录已变化或不可用", err))
					return
				}
				remover, ok := deps.Virtualizer.(interface { DeleteDirectoryPool(context.Context, string, string) error })
				if !ok { fail(apierr.New(apierr.CodeConflict, "节点需升级", nil)); return }
				if err := remover.DeleteDirectoryPool(r.Context(), body.Name, root); err != nil { fail(err); return }
				writeJSON(w, 200, map[string]any{"deleted": true})
				return
			case "start", "stop", "refresh":
				if _, err := diskRootForPool(r.Context(), deps, body.Name); err != nil {
					fail(err)
					return
				}
				stateOperator, ok := deps.Virtualizer.(interface {
					StoragePoolAction(context.Context, string, string) error
				})
				if !ok {
					fail(apierr.New(apierr.CodeConflict, "节点尚未提供存储池状态控制能力", nil))
					return
				}
				if err := stateOperator.StoragePoolAction(r.Context(), body.Name, body.Action); err != nil {
					fail(err)
					return
				}
				writeJSON(w, 200, map[string]any{"name": body.Name, "action": body.Action, "acknowledged": true})
				return
			case "", "create":
			default:
				fail(apierr.New(apierr.CodeInvalidArgument, "不支持的存储池操作", nil))
				return
			}
		}
		var err error
		if snapshots {
			if body.Action != "create" && !deps.AllowDestructive {
				fail(apierr.New(apierr.CodeOperationFailed, "节点未开启破坏性操作，禁止恢复或删除快照", nil))
				return
			}
			err = operator.SnapshotAction(r.Context(), r.PathValue("name"), body.Name, body.Action, diskRoot)
		} else {
			if body.Path == "" {
				err = operator.CreateDirectoryPool(r.Context(), body.Name, deps.DiskDir)
			} else {
				roots := deps.StorageRoots
				if len(roots) == 0 {
					roots = []string{deps.DiskDir}
				}
				root := ""
				for _, candidate := range roots {
					candidate = filepath.Clean(candidate)
					if filepath.IsAbs(body.Path) && (body.Path == candidate || strings.HasPrefix(filepath.Clean(body.Path), candidate+string(filepath.Separator))) {
						root = candidate
						break
					}
				}
				creator, ok := deps.Virtualizer.(interface {
					CreateDirectoryPoolAt(context.Context, string, string, string) error
				})
				if !ok || root == "" {
					fail(apierr.New(apierr.CodeInvalidArgument, "目录必须位于节点允许的存储根目录内", nil))
					return
				}
				err = creator.CreateDirectoryPoolAt(r.Context(), body.Name, root, body.Path)
			}
		}
		if err != nil {
			fail(err)
			return
		}
		writeJSON(w, 200, map[string]any{"name": body.Name, "action": body.Action, "acknowledged": true})
	}
}
