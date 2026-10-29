package storage

import (
	"context"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

type CloudInit struct {
	Networks      []GuestNetwork `json:"networks"`
	Hostname      string         `json:"hostname"`
	Username      string         `json:"username"`
	SSHPublicKeys []string       `json:"ssh_public_keys"`
}

var hostPattern = regexp.MustCompile(`^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$`)
var userPattern = regexp.MustCompile(`^[a-z_][a-z0-9_-]{0,30}$`)

func ValidateCloudInit(config CloudInit) error {
	if _, err := GuestNetworkConfig(config.Networks); err != nil {
		return err
	}
	if (config.Hostname != "" && !hostPattern.MatchString(config.Hostname)) || !userPattern.MatchString(config.Username) || config.Username == "root" || len(config.SSHPublicKeys) == 0 || len(config.SSHPublicKeys) > 16 {
		return apierr.New(apierr.CodeInvalidArgument, "初始化主机名、用户或公钥数量无效", nil)
	}
	for _, key := range config.SSHPublicKeys {
		parts := strings.Fields(key)
		if len(parts) < 2 || len(key) > 8192 || strings.ContainsAny(key, "\r\n") {
			return apierr.New(apierr.CodeInvalidArgument, "SSH 公钥格式无效", nil)
		}
		switch parts[0] {
		case "ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521":
		default:
			return apierr.New(apierr.CodeInvalidArgument, "SSH 公钥算法不支持", nil)
		}
		blob, err := base64.StdEncoding.DecodeString(parts[1])
		if err != nil || len(blob) < 8 || int(binary.BigEndian.Uint32(blob[:4])) != len(parts[0]) || len(blob) < 4+len(parts[0]) || string(blob[4:4+len(parts[0])]) != parts[0] {
			return apierr.New(apierr.CodeInvalidArgument, "SSH 公钥内容无效", err)
		}
	}
	return nil
}

// CloudInitISO contains structured guest configuration only, never host commands or passwords.
func CloudInitISO(ctx context.Context, root, uuid, name string, config CloudInit) (string, error) {
	if err := ValidateCloudInit(config); err != nil {
		return "", err
	}
	target, err := SafePathAllowMissing(root, ".init-"+uuid+".iso")
	if err != nil {
		return "", err
	}
	if _, err := os.Lstat(target); err == nil {
		return target, nil
	} else if !os.IsNotExist(err) {
		return "", err
	}
	temporary, err := os.MkdirTemp(root, ".seed-build-")
	if err != nil {
		return "", err
	}
	defer os.RemoveAll(temporary)
	hostname := config.Hostname
	if hostname == "" {
		hostname = name
	}
	userdata := map[string]any{"hostname": hostname, "manage_etc_hosts": true, "ssh_pwauth": false, "users": []any{"default", map[string]any{"name": config.Username, "lock_passwd": true, "sudo": []string{"ALL=(ALL) NOPASSWD:ALL"}, "shell": "/bin/bash", "ssh_authorized_keys": config.SSHPublicKeys}}, "resize_rootfs": true, "growpart": map[string]any{"mode": "auto", "devices": []string{"/"}, "ignore_growroot_disabled": false}}
	userData, err := json.Marshal(userdata)
	if err != nil {
		return "", err
	}
	metaData, _ := json.Marshal(map[string]string{"instance-id": uuid, "local-hostname": hostname})
	if err := os.WriteFile(filepath.Join(temporary, "user-data"), append([]byte("#cloud-config\n"), userData...), 0600); err != nil {
		return "", err
	}
	if err := os.WriteFile(filepath.Join(temporary, "meta-data"), metaData, 0600); err != nil {
		return "", err
	}
	commandCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	iso := filepath.Join(temporary, "seed.iso")
	command := exec.CommandContext(commandCtx, "genisoimage", "-quiet", "-output", iso, "-volid", "cidata", "-joliet", "-rock", "user-data", "meta-data")
	command.Dir = temporary
	if len(config.Networks) > 0 {
		networkConfig, err := GuestNetworkConfig(config.Networks)
		if err != nil {
			return "", err
		}
		data, err := json.Marshal(networkConfig)
		if err != nil {
			return "", err
		}
		if err := os.WriteFile(filepath.Join(temporary, "network-config"), data, 0600); err != nil {
			return "", err
		}
		command.Args = append(command.Args, "network-config")
	}
	if err := command.Run(); err != nil {
		return "", apierr.New(apierr.CodeOperationFailed, "初始化介质生成失败，请检查 genisoimage", err)
	}
	if err := os.Chmod(iso, 0644); err != nil {
		return "", err
	}
	if err := os.Link(iso, target); err != nil {
		return "", err
	}
	return target, nil
}
