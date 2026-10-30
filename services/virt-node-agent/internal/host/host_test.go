package host

import (
	"strings"
	"testing"
)

// TestParseMemInfoUsesMemAvailable 校验正常字段解析。
func TestParseMemInfoUsesMemAvailable(t *testing.T) {
	content := strings.Join([]string{
		"MemTotal:       32768000 kB",
		"MemFree:         1024000 kB",
		"MemAvailable:   16384000 kB",
		"Buffers:          204800 kB",
		"Cached:          4096000 kB",
	}, "\n")

	memory, err := ParseMemInfo(content)
	if err != nil {
		t.Fatalf("解析不应失败: %v", err)
	}
	if memory.TotalMiB != 32000 {
		t.Errorf("总量错误: got=%d want=32000", memory.TotalMiB)
	}
	if memory.AvailableMiB != 16000 {
		t.Errorf("可用量错误: got=%d want=16000", memory.AvailableMiB)
	}
}

// TestParseMemInfoFallsBackWithoutMemAvailable 校验缺少 MemAvailable 时的退化计算。
func TestParseMemInfoFallsBackWithoutMemAvailable(t *testing.T) {
	content := "MemTotal: 1024000 kB\nMemFree: 512000 kB\nBuffers: 1024 kB\nCached: 2048 kB\n"

	memory, err := ParseMemInfo(content)
	if err != nil {
		t.Fatalf("解析不应失败: %v", err)
	}
	// (512000 + 1024 + 2048) KiB / 1024 = 503 MiB
	if memory.AvailableMiB != 503 {
		t.Errorf("退化可用量错误: got=%d want=503", memory.AvailableMiB)
	}
}

// TestParseMemInfoRejectsMissingTotal 校验缺少总量字段时返回错误。
func TestParseMemInfoRejectsMissingTotal(t *testing.T) {
	if _, err := ParseMemInfo("MemFree: 1024 kB\n"); err == nil {
		t.Fatal("缺少 MemTotal 时应返回错误")
	}
}

// TestReadStorageOnTempDir 校验临时目录容量可被统计。
func TestReadStorageOnTempDir(t *testing.T) {
	directory := t.TempDir()

	usage, err := ReadStorage(directory)
	if err != nil {
		t.Fatalf("统计不应失败: %v", err)
	}
	if usage.Path != directory {
		t.Errorf("路径错误: got=%q want=%q", usage.Path, directory)
	}
	if usage.TotalBytes == 0 || usage.FreeBytes == 0 {
		t.Errorf("容量不应为 0: total=%d free=%d", usage.TotalBytes, usage.FreeBytes)
	}
	if usage.FreeBytes > usage.TotalBytes {
		t.Errorf("剩余容量不应大于总容量: free=%d total=%d", usage.FreeBytes, usage.TotalBytes)
	}
}

// TestReadStorageRejectsEmptyAndMissingPath 校验非法路径被拒绝。
func TestReadStorageRejectsEmptyAndMissingPath(t *testing.T) {
	if _, err := ReadStorage("   "); err == nil {
		t.Fatal("空路径应返回错误")
	}
	if _, err := ReadStorage("/definitely/not/existing/path"); err == nil {
		t.Fatal("不存在的路径应返回错误")
	}
}

// TestCollectReturnsRealValues 校验完整采集返回真实值。
func TestCollectReturnsRealValues(t *testing.T) {
	directory := t.TempDir()

	resources, err := Collect([]string{directory})
	if err != nil {
		t.Fatalf("采集不应失败: %v", err)
	}
	if resources.CPULogical <= 0 {
		t.Errorf("CPU 核心数应大于 0: %d", resources.CPULogical)
	}
	if resources.MemoryTotalMiB <= 0 {
		t.Errorf("内存总量应大于 0: %d", resources.MemoryTotalMiB)
	}
	if len(resources.Storage) != 1 {
		t.Fatalf("存储条目数量错误: %d", len(resources.Storage))
	}
	if resources.SampledAt.IsZero() {
		t.Error("采样时间不能为空")
	}
}

func TestStorageFilesystemIdentity(t *testing.T) {
	root := t.TempDir()
	first, err := ReadStorage(root)
	if err != nil {
		t.Fatal(err)
	}
	second, err := ReadStorage(root + "/.")
	if err != nil {
		t.Fatal(err)
	}
	if first.FilesystemID == "" || first.FilesystemID != second.FilesystemID {
		t.Fatal("same filesystem must have stable nonempty identity")
	}
}
