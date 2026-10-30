// Package host 采集宿主机资源（CPU、内存、存储），供管理后端心跳与调度使用。
//
// 采集值必须来自操作系统真实数据，禁止写死样例值；无法采集的字段返回错误，
// 由调用方决定降级策略（保留上次值并标记过期）。
package host

import (
	"bufio"
	"fmt"
	"os"
	"runtime"
	"strconv"
	"strings"
	"syscall"
	"time"
)

// procMemInfo 是内存信息文件路径，便于测试替换。
const procMemInfo = "/proc/meminfo"

// KiBPerMiB 是 KiB 到 MiB 的换算基数。
const KiBPerMiB = 1024

// Memory 是内存采集结果（单位 MiB）。
type Memory struct {
	TotalMiB     int64
	AvailableMiB int64
}

// Storage 是单个路径的存储采集结果。
type Storage struct {
	FilesystemID string
	Path         string
	TotalBytes   uint64
	FreeBytes    uint64
}

// Resources 是一次完整采集的结果。
type Resources struct {
	CPUUsagePercent    *float64
	CPUSampledAt       *time.Time
	CPULogical         int
	MemoryTotalMiB     int64
	MemoryAvailableMiB int64
	Storage            []Storage
	SampledAt          time.Time
}

// Collect 采集 CPU、内存与指定路径的存储使用情况。
//
// Args:
//
//	storagePaths: 需要统计容量的目录，通常为镜像目录与磁盘目录。
//
// Returns:
//
//	采集结果；任一必要字段采集失败时返回错误。
func Collect(storagePaths []string) (Resources, error) {
	cpuPercent, cpuSampledAt := CPUUsage()
	memory, err := ReadMemory()
	if err != nil {
		return Resources{}, err
	}

	storage := make([]Storage, 0, len(storagePaths))
	for _, path := range storagePaths {
		usage, err := ReadStorage(path)
		if err != nil {
			return Resources{}, err
		}
		storage = append(storage, usage)
	}

	return Resources{
		CPUUsagePercent:    cpuPercent,
		CPUSampledAt:       cpuSampledAt,
		CPULogical:         runtime.NumCPU(),
		MemoryTotalMiB:     memory.TotalMiB,
		MemoryAvailableMiB: memory.AvailableMiB,
		Storage:            storage,
		SampledAt:          time.Now().UTC(),
	}, nil
}

// ReadMemory 读取系统内存总量与可用量。
func ReadMemory() (Memory, error) {
	content, err := os.ReadFile(procMemInfo)
	if err != nil {
		return Memory{}, fmt.Errorf("读取内存信息失败: %w", err)
	}
	return ParseMemInfo(string(content))
}

// ParseMemInfo 解析 /proc/meminfo 内容。
//
// Args:
//
//	content: /proc/meminfo 的文本内容。
//
// Returns:
//
//	内存总量与可用量（MiB）；缺少必要字段时返回错误。
func ParseMemInfo(content string) (Memory, error) {
	values := map[string]int64{}
	scanner := bufio.NewScanner(strings.NewReader(content))
	for scanner.Scan() {
		line := scanner.Text()
		name, raw, found := strings.Cut(line, ":")
		if !found {
			continue
		}
		fields := strings.Fields(raw)
		if len(fields) == 0 {
			continue
		}
		value, err := strconv.ParseInt(fields[0], 10, 64)
		if err != nil {
			continue
		}
		values[strings.TrimSpace(name)] = value
	}
	if err := scanner.Err(); err != nil {
		return Memory{}, fmt.Errorf("解析内存信息失败: %w", err)
	}

	total, ok := values["MemTotal"]
	if !ok {
		return Memory{}, fmt.Errorf("内存信息缺少 MemTotal")
	}
	available, ok := values["MemAvailable"]
	if !ok {
		// 部分内核缺少 MemAvailable，退化为 MemFree + Buffers + Cached
		available = values["MemFree"] + values["Buffers"] + values["Cached"]
	}
	return Memory{TotalMiB: total / KiBPerMiB, AvailableMiB: available / KiBPerMiB}, nil
}

// ReadStorage 统计指定路径所在文件系统的容量。
//
// Args:
//
//	path: 需要统计的目录。
//
// Returns:
//
//	总容量与剩余容量（字节）；路径不存在或统计失败时返回错误。
func ReadStorage(path string) (Storage, error) {
	if strings.TrimSpace(path) == "" {
		return Storage{}, fmt.Errorf("存储路径不能为空")
	}
	var stat syscall.Statfs_t
	if err := syscall.Statfs(path, &stat); err != nil {
		return Storage{}, fmt.Errorf("统计存储容量失败: path=%s: %w", path, err)
	}
	var device syscall.Stat_t
	if err := syscall.Stat(path, &device); err != nil {
		return Storage{}, fmt.Errorf("读取文件系统标识失败: %w", err)
	}
	return Storage{
		FilesystemID: strconv.FormatUint(uint64(device.Dev), 10),
		Path:         path,
		TotalBytes:   stat.Blocks * uint64(stat.Bsize),
		FreeBytes:    stat.Bavail * uint64(stat.Bsize),
	}, nil
}
