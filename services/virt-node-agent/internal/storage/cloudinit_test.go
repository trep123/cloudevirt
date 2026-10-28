package storage

import (
	"context"
	"encoding/base64"
	"os"
	"os/exec"
	"strings"
	"testing"
)

func TestCloudInitStructuredSeed(t *testing.T) {
	if _, err := exec.LookPath("genisoimage"); err != nil {
		t.Skip("requires genisoimage")
	}
	blob := append([]byte{0, 0, 0, 11}, []byte("ssh-ed25519")...)
	blob = append(blob, []byte{0, 0, 0, 32}...)
	blob = append(blob, make([]byte, 32)...)
	key := "ssh-ed25519 " + base64.StdEncoding.EncodeToString(blob)
	config := CloudInit{Hostname: "guest-one", Username: "cloudvirt", SSHPublicKeys: []string{key}}
	path, err := CloudInitISO(context.Background(), t.TempDir(), "0f6f2b1e-3333-4a44-9f55-000000000003", "guest-one", config)
	if err != nil {
		t.Fatal(err)
	}
	file, err := os.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	magic := make([]byte, 5)
	file.ReadAt(magic, 16*2048+1)
	if string(magic) != "CD001" {
		t.Fatal("invalid seed ISO")
	}
	for _, bad := range []CloudInit{{Username: "root", SSHPublicKeys: []string{key}}, {Username: "cloudvirt", SSHPublicKeys: []string{key + "\ncommand=bad"}}, {Username: "cloudvirt", SSHPublicKeys: []string{strings.Repeat("x", 9000)}}} {
		if ValidateCloudInit(bad) == nil {
			t.Fatal("accepted invalid configuration")
		}
	}
}
