package storage

import (
	"bytes"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"sync"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/host"
)

const UploadChunkBytes = 8 * 1024 * 1024
const MaxImageBytes int64 = 64 * 1024 * 1024 * 1024

var uploadIDPattern = regexp.MustCompile(`^[0-9a-f]{32}$`)
var uploadLock sync.Mutex

type UploadProgress struct {
	Offset       int64  `json:"offset"`
	Published    bool   `json:"published"`
	RelativePath string `json:"relative_path"`
}

func uploadPaths(root, id, extension string) (string, string, string, error) {
	if !uploadIDPattern.MatchString(id) || (extension != ".qcow2" && extension != ".iso" && extension != ".raw" && extension != ".img") {
		return "", "", "", apierr.New(apierr.CodeInvalidArgument, "上传 ID 或扩展名无效", nil)
	}
	root, err := filepath.EvalSymlinks(root)
	if err != nil {
		return "", "", "", apierr.New(apierr.CodeOperationFailed, "镜像目录不存在或不可访问，请检查 Agent 镜像目录配置和权限", err)
	}
	finalName := "upload-" + id + extension
	for _, name := range []string{".upload-" + id + ".part", finalName} {
		stat, err := os.Lstat(filepath.Join(root, name))
		if err == nil && stat.Mode()&os.ModeSymlink != 0 {
			return "", "", "", apierr.New(apierr.CodeInvalidArgument, "上传目标禁止使用符号链接", nil)
		}
	}
	part, err := SafePathAllowMissing(root, ".upload-"+id+".part")
	if err != nil {
		return "", "", "", err
	}
	final, err := SafePathAllowMissing(root, finalName)
	if err != nil {
		return "", "", "", err
	}
	// Upload files may not be aliases of other files, even within the managed root.
	for _, path := range []string{part, final} {
		stat, err := os.Lstat(path)
		if err != nil && !os.IsNotExist(err) {
			return "", "", "", err
		}
		if err == nil && (!stat.Mode().IsRegular() || stat.Mode()&os.ModeSymlink != 0) {
			return "", "", "", apierr.New(apierr.CodeInvalidArgument, "上传目标不是普通文件", nil)
		}
	}
	return part, final, finalName, nil
}

func uploadProgress(part, final, relative string) (UploadProgress, error) {
	if stat, err := os.Stat(final); err == nil {
		return UploadProgress{stat.Size(), true, relative}, nil
	} else if !os.IsNotExist(err) {
		return UploadProgress{}, err
	}
	if stat, err := os.Stat(part); err == nil {
		return UploadProgress{stat.Size(), false, relative}, nil
	} else if !os.IsNotExist(err) {
		return UploadProgress{}, err
	}
	return UploadProgress{0, false, relative}, nil
}

func ImageUploadProgress(root, id, extension string) (UploadProgress, error) {
	uploadLock.Lock()
	defer uploadLock.Unlock()
	part, final, relative, err := uploadPaths(root, id, extension)
	if err != nil {
		return UploadProgress{}, err
	}
	return uploadProgress(part, final, relative)
}

// WriteImageChunk is offset-checked, bounded, durable and safe to replay after a lost response.
func WriteImageChunk(root, id, extension string, offset, total int64, data []byte) (UploadProgress, error) {
	if total <= 0 || total > MaxImageBytes || offset < 0 || len(data) == 0 || len(data) > UploadChunkBytes || offset > total-int64(len(data)) {
		return UploadProgress{}, apierr.New(apierr.CodeInvalidArgument, "分片范围或镜像大小无效", nil)
	}
	uploadLock.Lock()
	defer uploadLock.Unlock()
	part, final, relative, err := uploadPaths(root, id, extension)
	if err != nil {
		return UploadProgress{}, err
	}
	progress, err := uploadProgress(part, final, relative)
	if err != nil {
		return UploadProgress{}, err
	}
	if progress.Published {
		return UploadProgress{}, apierr.New(apierr.CodeConflict, "上传已完成发布，不可继续写入", nil)
	}
	if offset > progress.Offset {
		return UploadProgress{}, apierr.New(apierr.CodeConflict, "分片偏移不连续，请先查询节点进度", nil)
	}
	usage, err := host.ReadStorage(root)
	if err != nil {
		return UploadProgress{}, err
	}
	if offset == progress.Offset && usage.FreeBytes < uint64(total-progress.Offset)+64*1024*1024 {
		return UploadProgress{}, apierr.New(apierr.CodeInsufficientResource, "节点镜像目录可用空间不足，上传已暂停", nil)
	}
	file, err := os.OpenFile(part, os.O_CREATE|os.O_RDWR, 0o660)
	if err != nil {
		return UploadProgress{}, apierr.New(apierr.CodeOperationFailed, "Agent 无法写入镜像目录，请检查 cloudvirt-agent 用户目录权限", err)
	}
	defer file.Close()
	if offset < progress.Offset {
		if offset+int64(len(data)) > progress.Offset {
			return UploadProgress{}, apierr.New(apierr.CodeConflict, "分片与已上传数据部分重叠", nil)
		}
		previous := make([]byte, len(data))
		if _, err := file.ReadAt(previous, offset); err != nil || !bytes.Equal(previous, data) {
			return UploadProgress{}, apierr.New(apierr.CodeConflict, "重复分片与节点已有内容不一致", err)
		}
		return progress, nil
	}
	count, err := file.WriteAt(data, offset)
	if err == nil && count != len(data) {
		err = io.ErrShortWrite
	}
	if err == nil {
		err = file.Sync()
	}
	if err != nil {
		_ = file.Truncate(offset)
		return UploadProgress{}, apierr.New(apierr.CodeOperationFailed, "写入分片失败，请检查磁盘空间及权限", err)
	}
	progress.Offset += int64(count)
	return progress, nil
}

// PublishImageUpload atomically links a fully received file without replacing another file.
func PublishImageUpload(root, id, extension string, total int64) (UploadProgress, error) {
	if total <= 0 || total > MaxImageBytes {
		return UploadProgress{}, apierr.New(apierr.CodeInvalidArgument, "镜像大小无效", nil)
	}
	uploadLock.Lock()
	defer uploadLock.Unlock()
	part, final, relative, err := uploadPaths(root, id, extension)
	if err != nil {
		return UploadProgress{}, err
	}
	progress, err := uploadProgress(part, final, relative)
	if err != nil {
		return UploadProgress{}, err
	}
	if progress.Offset != total {
		return UploadProgress{}, apierr.New(apierr.CodeConflict, "镜像尚未完整接收，不能提交校验", nil)
	}
	if !progress.Published {
		if err := os.Chmod(part, 0o660); err != nil {
			return UploadProgress{}, err
		}
		if err := os.Link(part, final); err != nil {
			return UploadProgress{}, apierr.New(apierr.CodeOperationFailed, "无法发布镜像文件，未覆盖已有文件", err)
		}
		if err := os.Remove(part); err != nil {
			return UploadProgress{}, err
		}
		dir, err := os.Open(filepath.Dir(final))
		if err != nil {
			return UploadProgress{}, err
		}
		err = dir.Sync()
		dir.Close()
		if err != nil {
			return UploadProgress{}, err
		}
	} else if partialStat, partialErr := os.Stat(part); partialErr == nil {
		finalStat, finalErr := os.Stat(final)
		if finalErr != nil || !os.SameFile(partialStat, finalStat) {
			return UploadProgress{}, apierr.New(apierr.CodeConflict, "上传临时文件和已发布文件不一致", finalErr)
		}
		if err := os.Remove(part); err != nil {
			return UploadProgress{}, err
		}
	}
	progress.Published = true
	return progress, nil
}

// CancelImageUpload only removes a private unpublished partial file, never a published image.
func CancelImageUpload(root, id, extension string) error {
	uploadLock.Lock()
	defer uploadLock.Unlock()
	part, final, _, err := uploadPaths(root, id, extension)
	if err != nil {
		return err
	}
	if _, err := os.Stat(final); err == nil {
		return apierr.New(apierr.CodeConflict, "镜像已发布，请使用镜像删除流程", nil)
	} else if !os.IsNotExist(err) {
		return err
	}
	if err := os.Remove(part); err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("清理临时上传文件失败: %w", err)
	}
	return nil
}
