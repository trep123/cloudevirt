// Package storage 负责镜像与磁盘文件的路径安全与信息检查。
//
// 所有路径必须是相对路径，解析后必须位于配置的根目录内；
// 符号链接、目录穿越与绝对路径一律拒绝。
package storage

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
)

// ErrPathEscape 表示路径解析后越出根目录。
var ErrPathEscape = errors.New("路径越出允许的根目录")

// SafePath 把相对路径解析为根目录内的绝对路径。
//
// Args:
//
//	root: 允许的根目录（镜像目录或磁盘目录）。
//	relative: 调用方传入的相对路径。
//
// Returns:
//
//	安全的绝对路径；越界、绝对路径或符号链接越界时返回错误。
func SafePath(root, relative string) (string, error) {
	if strings.TrimSpace(root) == "" {
		return "", apierr.New(apierr.CodeInternalError, "存储根目录未配置", nil)
	}
	if strings.TrimSpace(relative) == "" {
		return "", apierr.New(apierr.CodeInvalidArgument, "文件路径不能为空", nil)
	}
	if filepath.IsAbs(relative) {
		return "", apierr.New(apierr.CodeInvalidArgument, "文件路径必须是相对路径", nil)
	}
	cleaned := filepath.Clean(filepath.Join(root, relative))
	rootCleaned := filepath.Clean(root)
	if cleaned != rootCleaned && !strings.HasPrefix(cleaned, rootCleaned+string(os.PathSeparator)) {
		return "", apierr.New(apierr.CodeInvalidArgument, "路径越出允许的根目录", ErrPathEscape)
	}
	// 解析符号链接后再次校验，避免通过链接逃出根目录
	resolved, err := filepath.EvalSymlinks(cleaned)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return "", apierr.New(apierr.CodeNotFound, "节点镜像目录中找不到文件；请核对所选节点和相对路径，或使用浏览器上传", err)
		}
		if errors.Is(err, os.ErrPermission) {
			return "", apierr.New(apierr.CodeOperationFailed, "Agent 无权访问目录；请检查目录遍历权限及 cloudvirt-agent 用户权限", err)
		}
		return "", apierr.New(apierr.CodeOperationFailed, "路径解析失败", err)
	}
	if resolved != rootCleaned && !strings.HasPrefix(resolved, rootCleaned+string(os.PathSeparator)) {
		return "", apierr.New(apierr.CodeInvalidArgument, "符号链接越出允许的根目录", ErrPathEscape)
	}
	return resolved, nil
}

// FileInfo 是镜像/磁盘文件的检查结果。
type FileInfo struct {
	Path             string `json:"path"`
	Format           string `json:"format"`
	SizeBytes        int64  `json:"size_bytes"`
	VirtualSizeBytes int64  `json:"virtual_size_bytes"`
	ChecksumSHA256   string `json:"checksum_sha256"`
}

// qemuImgOutput 只解析需要的字段，避免依赖完整结构。
type qemuImgOutput struct {
	Format           string `json:"format"`
	ActualSizeBytes  int64  `json:"actual-size"`
	VirtualSizeBytes int64  `json:"virtual-size"`
	BackingFilename  string `json:"backing-filename"`
	FormatSpecific   struct {
		Data struct {
			DataFile string `json:"data-file"`
		} `json:"data"`
	} `json:"format-specific"`
}

// Inspect 检查文件：校验路径、读取 qemu-img 信息并流式计算 SHA-256。
//
// Args:
//
//	root: 允许的根目录。
//	relative: 相对路径。
//
// Returns:
//
//	文件信息；任何一步失败都返回带错误码的错误。
func Inspect(root, relative string) (FileInfo, error) {
	return InspectContext(context.Background(), root, relative)
}

func InspectContext(ctx context.Context, root, relative string) (FileInfo, error) {
	if strings.HasPrefix(filepath.Base(relative), ".upload-") {
		return FileInfo{}, apierr.New(apierr.CodeInvalidArgument, "上传临时分片不能作为可用镜像，请先完成发布", nil)
	}
	path, err := SafePath(root, relative)
	if err != nil {
		return FileInfo{}, err
	}

	statBeforeOpen, err := os.Stat(path)
	if err != nil || !statBeforeOpen.Mode().IsRegular() || statBeforeOpen.Size() == 0 {
		return FileInfo{}, apierr.New(apierr.CodeInvalidArgument, "镜像必须为非空普通文件", err)
	}
	file, err := os.Open(path)
	if err != nil {
		return FileInfo{}, apierr.New(apierr.CodeOperationFailed, "Agent 无法读取镜像文件；请检查文件及上级目录权限", err)
	}
	stat, err := file.Stat()
	if err != nil || !stat.Mode().IsRegular() || stat.Size() == 0 {
		file.Close()
		return FileInfo{}, apierr.New(apierr.CodeInvalidArgument, "镜像必须为非空普通文件", err)
	}
	// ISO9660 volume descriptors identify installation media; qemu-img calls these RAW.
	var magic [5]byte
	_, _ = file.ReadAt(magic[:], 16*2048+1)
	file.Close()
	commandCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	output, err := exec.CommandContext(commandCtx, "qemu-img", "info", "--output=json", "--", path).Output()
	if err != nil {
		if errors.Is(err, exec.ErrNotFound) {
			return FileInfo{}, apierr.New(apierr.CodeOperationFailed, "节点未安装 qemu-img，请安装 qemu-utils", err)
		}
		if commandCtx.Err() != nil {
			return FileInfo{}, apierr.New(apierr.CodeCommandTimeout, "解析镜像超时", err)
		}
		return FileInfo{}, apierr.New(apierr.CodeInvalidArgument, "无法解析镜像格式", err)
	}
	var parsed qemuImgOutput
	if err := json.Unmarshal(output, &parsed); err != nil {
		return FileInfo{}, apierr.New(apierr.CodeOperationFailed, "qemu-img 输出解析失败", err)
	}

	if parsed.BackingFilename != "" || parsed.FormatSpecific.Data.DataFile != "" {
		return FileInfo{}, apierr.New(apierr.CodeInvalidArgument, "不接受依赖外部 backing/data 文件的镜像，请先转换为独立镜像", nil)
	}
	if string(magic[:]) == "CD001" {
		parsed.Format = "iso"
	}
	checksum, size, err := checksumAndSizeContext(ctx, path)
	if err != nil {
		return FileInfo{}, err
	}
	virtualSize := parsed.VirtualSizeBytes
	if virtualSize == 0 {
		virtualSize = size
	}

	return FileInfo{
		Path:             relative,
		Format:           strings.ToUpper(parsed.Format),
		SizeBytes:        size,
		VirtualSizeBytes: virtualSize,
		ChecksumSHA256:   checksum,
	}, nil
}

// checksumAndSize 流式计算 SHA-256 并统计文件大小，避免一次性读入内存。
func checksumAndSize(path string) (string, int64, error) {
	return checksumAndSizeContext(context.Background(), path)
}

type contextReader struct {
	ctx    context.Context
	reader io.Reader
}

func (r contextReader) Read(buffer []byte) (int, error) {
	if err := r.ctx.Err(); err != nil {
		return 0, err
	}
	return r.reader.Read(buffer)
}

func checksumAndSizeContext(ctx context.Context, path string) (string, int64, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", 0, apierr.New(apierr.CodeOperationFailed, "文件无法打开", err)
	}
	defer file.Close()

	hasher := sha256.New()
	written, err := io.Copy(hasher, contextReader{ctx: ctx, reader: file})
	if err != nil {
		if ctx.Err() != nil {
			return "", 0, apierr.New(apierr.CodeCommandTimeout, "镜像校验超时，可在任务中心查看或重新校验", err)
		}
		return "", 0, apierr.New(apierr.CodeOperationFailed, "文件读取失败", err)
	}
	return hex.EncodeToString(hasher.Sum(nil)), written, nil
}

// Remove 删除根目录下的文件（受宿主机破坏性开关保护）。
func Remove(root, relative string) error {
	path, err := SafePath(root, relative)
	if err != nil {
		var apiError *apierr.Error
		if errors.As(err, &apiError) && apiError.Code == apierr.CodeNotFound {
			return nil
		}
		return err
	}
	if err := os.Remove(path); err != nil {
		return apierr.New(apierr.CodeOperationFailed, fmt.Sprintf("删除文件失败: %v", err), err)
	}
	return nil
}

// CreateDisk 创建稀疏 QCOW2 磁盘；文件已存在时视为成功（幂等）。
//
// Args:
//
//	path: 已通过 SafePath 校验的绝对路径。
//	sizeGiB: 虚拟容量（GiB），必须为正数。
//
// Returns:
//
//	创建或已存在时返回 nil。
func CreateDisk(ctx context.Context, path string, sizeGiB int) error {
	if sizeGiB <= 0 {
		return apierr.New(apierr.CodeInvalidArgument, "磁盘容量必须为正数", nil)
	}
	if _, err := os.Stat(path); err == nil {
		return nil
	} else if !errors.Is(err, os.ErrNotExist) {
		return apierr.New(apierr.CodeOperationFailed, "磁盘状态检查失败", err)
	}

	commandCtx, cancel := context.WithTimeout(ctx, 60*time.Second)
	defer cancel()
	argument := fmt.Sprintf("%dG", sizeGiB)
	output, err := exec.CommandContext(
		commandCtx, "qemu-img", "create", "-f", "qcow2", "--", path, argument,
	).CombinedOutput()
	if err != nil {
		return apierr.New(
			apierr.CodeOperationFailed,
			fmt.Sprintf("创建磁盘失败: %s", strings.TrimSpace(string(output))),
			err,
		)
	}
	return nil
}

// DiskInfo 返回实际格式与虚拟容量，用于创建后的复核。
func DiskInfo(ctx context.Context, path string) (string, int64, error) {
	commandCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	// --force-share 允许读取正在被 QEMU 打开的镜像
	output, err := exec.CommandContext(
		commandCtx, "qemu-img", "info", "--force-share", "--output=json", "--", path,
	).Output()
	if err != nil {
		return "", 0, apierr.New(apierr.CodeOperationFailed, "读取磁盘信息失败", err)
	}
	var parsed qemuImgOutput
	if err := json.Unmarshal(output, &parsed); err != nil {
		return "", 0, apierr.New(apierr.CodeOperationFailed, "磁盘信息解析失败", err)
	}
	return strings.ToUpper(parsed.Format), parsed.VirtualSizeBytes, nil
}

// SafePathAllowMissing 与 SafePath 类似，但允许目标文件尚不存在（用于创建磁盘）。
//
// 父目录必须存在且解析后仍位于根目录内，避免通过目录符号链接逃逸。
func SafePathAllowMissing(root, relative string) (string, error) {
	if strings.TrimSpace(root) == "" {
		return "", apierr.New(apierr.CodeInternalError, "存储根目录未配置", nil)
	}
	if strings.TrimSpace(relative) == "" {
		return "", apierr.New(apierr.CodeInvalidArgument, "文件路径不能为空", nil)
	}
	if filepath.IsAbs(relative) {
		return "", apierr.New(apierr.CodeInvalidArgument, "文件路径必须是相对路径", nil)
	}
	rootCleaned := filepath.Clean(root)
	cleaned := filepath.Clean(filepath.Join(rootCleaned, relative))
	if cleaned != rootCleaned && !strings.HasPrefix(cleaned, rootCleaned+string(os.PathSeparator)) {
		return "", apierr.New(apierr.CodeInvalidArgument, "路径越出允许的根目录", ErrPathEscape)
	}
	parent, err := filepath.EvalSymlinks(filepath.Dir(cleaned))
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return "", apierr.New(apierr.CodeNotFound, "目标目录不存在", err)
		}
		return "", apierr.New(apierr.CodeOperationFailed, "路径解析失败", err)
	}
	rootResolved, err := filepath.EvalSymlinks(rootCleaned)
	if err != nil {
		return "", apierr.New(apierr.CodeNotFound, "存储根目录不存在", err)
	}
	if parent != rootResolved && !strings.HasPrefix(parent, rootResolved+string(os.PathSeparator)) {
		return "", apierr.New(apierr.CodeInvalidArgument, "符号链接越出允许的根目录", ErrPathEscape)
	}
	return filepath.Join(parent, filepath.Base(cleaned)), nil
}

// DiskFile 是磁盘目录中单个文件的摘要。
type DiskFile struct {
	Name             string `json:"name"`
	Format           string `json:"format"`
	SizeBytes        int64  `json:"size_bytes"`
	VirtualSizeBytes int64  `json:"virtual_size_bytes"`
	ActualSizeBytes  int64  `json:"actual_size_bytes"`
}

// ListDiskFiles 列出磁盘目录下的常规文件及其容量信息。
//
// 只读取目录内的一层文件，跳过子目录与符号链接，避免意外遍历或越界。
func ListDiskFiles(ctx context.Context, root string) ([]DiskFile, error) {
	entries, err := os.ReadDir(root)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil, apierr.New(apierr.CodeNotFound, "磁盘目录不存在", err)
		}
		return nil, apierr.New(apierr.CodeOperationFailed, "读取磁盘目录失败", err)
	}

	files := make([]DiskFile, 0, len(entries))
	for _, entry := range entries {
		if strings.HasPrefix(entry.Name(), ".") {
			continue
		}
		if entry.IsDir() || entry.Type()&os.ModeSymlink != 0 {
			continue
		}
		path := filepath.Join(root, entry.Name())
		info, err := entry.Info()
		if err != nil {
			continue
		}
		format, virtualSize, err := DiskInfo(ctx, path)
		if err != nil {
			// 非镜像文件（如临时文件）不应导致整次扫描失败
			continue
		}
		files = append(files, DiskFile{
			Name:             entry.Name(),
			Format:           format,
			SizeBytes:        info.Size(),
			VirtualSizeBytes: virtualSize,
			ActualSizeBytes:  info.Size(),
		})
	}
	return files, nil
}
