package httpapi

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/storage"
	"os"
	"sync"
)

var creationLocks sync.Map

func lockCreation(uuid string) func() {
	value, _ := creationLocks.LoadOrStore(uuid, &sync.Mutex{})
	mutex := value.(*sync.Mutex)
	mutex.Lock()
	return mutex.Unlock
}
func creationFingerprint(payload createDomainRequest) string {
	data, _ := json.Marshal(payload)
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}
func journalMatches(root string, payload createDomainRequest) (bool, error) {
	path, err := storage.SafePathAllowMissing(root, ".create-"+payload.UUID+".json")
	if err != nil {
		return false, err
	}
	data, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	var record map[string]string
	if json.Unmarshal(data, &record) != nil || record["fingerprint"] != creationFingerprint(payload) {
		return false, apierr.New(apierr.CodeConflict, "创建配置与原任务不一致，禁止重放", nil)
	}
	return true, nil
}
func claimCreation(root string, payload createDomainRequest, paths []string) (bool, error) {
	exists, err := journalMatches(root, payload)
	if err != nil || exists {
		return exists, err
	}
	for _, path := range paths {
		if _, err := os.Lstat(path); !os.IsNotExist(err) {
			return false, apierr.New(apierr.CodeConflict, "目标磁盘已存在且不属于本任务", err)
		}
	}
	path, err := storage.SafePathAllowMissing(root, ".create-"+payload.UUID+".json")
	if err != nil {
		return false, err
	}
	file, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return false, err
	}
	defer file.Close()
	if err := json.NewEncoder(file).Encode(map[string]string{"fingerprint": creationFingerprint(payload)}); err != nil {
		return false, err
	}
	return false, file.Sync()
}
