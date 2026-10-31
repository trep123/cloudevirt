package httpapi

import (
	"encoding/json"
	"io"
	"net/http"
	"strconv"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/storage"
)

func imageUploadHandler(deps Dependencies) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		fail := func(err error) { writeAPIError(w, deps.Logger, err, RequestIDFromContext(r.Context())) }
		id, extension := r.PathValue("id"), r.URL.Query().Get("extension")
		root, rootErr := imageRootForPool(r.Context(), deps, r.URL.Query().Get("storage_pool"))
		if rootErr != nil { fail(rootErr); return }
		if directory := r.URL.Query().Get("directory"); directory != "" {
			root, rootErr = storage.EnsureManagedDirectory(root, directory)
			if rootErr != nil { fail(apierr.New(apierr.CodeInvalidArgument, "无法创建镜像用户目录", rootErr)); return }
		}
		var progress storage.UploadProgress
		var err error
		switch r.Method {
		case http.MethodGet:
			progress, err = storage.ImageUploadProgress(root, id, extension)
		case http.MethodPut:
			offset, e1 := strconv.ParseInt(r.URL.Query().Get("offset"), 10, 64)
			total, e2 := strconv.ParseInt(r.URL.Query().Get("size"), 10, 64)
			if e1 != nil || e2 != nil {
				fail(apierr.New(apierr.CodeInvalidArgument, "分片偏移或大小无效", nil))
				return
			}
			data, e := io.ReadAll(http.MaxBytesReader(w, r.Body, storage.UploadChunkBytes))
			if e != nil {
				fail(apierr.New(apierr.CodeInvalidArgument, "分片超过 8 MiB 或连接已中断", e))
				return
			}
			progress, err = storage.WriteImageChunk(root, id, extension, offset, total, data)
		case http.MethodPost:
			var body struct {
				Size      int64  `json:"size_bytes"`
				Extension string `json:"extension"`
			}
			decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096))
			decoder.DisallowUnknownFields()
			if e := decoder.Decode(&body); e != nil {
				fail(apierr.New(apierr.CodeInvalidArgument, "发布请求无效", e))
				return
			}
			progress, err = storage.PublishImageUpload(root, id, body.Extension, body.Size)
		case http.MethodDelete:
			err = storage.CancelImageUpload(root, id, extension)
		}
		if err != nil {
			fail(err)
			return
		}
		writeJSON(w, 200, progress)
	}
}
