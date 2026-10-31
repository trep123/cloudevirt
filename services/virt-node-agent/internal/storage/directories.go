package storage

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
)

var managedDirectory = regexp.MustCompile(`^(images|vms)/user-[0-9]+/[a-f0-9-]{32,36}$`)

// EnsureManagedDirectory creates only server-generated user namespaces beneath a root.
func EnsureManagedDirectory(root, relative string) (string, error) {
	if !managedDirectory.MatchString(relative) { return "", fmt.Errorf("受管用户目录无效") }
	base, err := filepath.EvalSymlinks(root)
	if err != nil { return "", err }
	opened, err := os.OpenRoot(base)
	if err != nil { return "", err }
	defer opened.Close()
	current := ""
	for _, part := range strings.Split(relative, "/") {
		current = filepath.Join(current, part)
		if err := opened.Mkdir(current, 0770); err != nil && !os.IsExist(err) { return "", err }
		info, err := os.Lstat(filepath.Join(base, current))
		if err != nil { return "", err }
		if !info.IsDir() || info.Mode()&os.ModeSymlink != 0 { return "", fmt.Errorf("受管目录不允许符号链接或普通文件") }
	}
	return filepath.Join(base, relative), nil
}

func EnsureDiskParent(root, relative string) error {
	parent := filepath.ToSlash(filepath.Dir(relative))
	if !strings.HasPrefix(parent, "vms/user-") { return nil }
	_, err := EnsureManagedDirectory(root, parent)
	if err != nil { return apierr.New(apierr.CodeOperationFailed, "无法创建用户磁盘目录，请检查 Agent 对存储池目录的写入权限", err) }
	return nil
}
