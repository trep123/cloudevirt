package httpapi

import (
	"context"
	"encoding/json"
	"net/http"
	"path/filepath"
	"strings"

	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/apierr"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/domainxml"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/libvirt"
	"github.com/tl2004/cloude-virt/services/virt-node-agent/internal/storage"
)

// DomainOperator 是域操作依赖，便于测试替换真实 libvirt。
type DomainOperator interface {
	DomainExists(ctx context.Context, name string) (bool, error)
	DefineDomain(ctx context.Context, content string) error
	StartDomain(ctx context.Context, name string) error
	DumpXML(ctx context.Context, name string) (string, error)
	DomainState(ctx context.Context, name string) (string, error)
	DomainAddresses(ctx context.Context, name string) ([]libvirt.DomainAddress, error)
	DomainInterfaces(ctx context.Context, name string) ([]libvirt.DomainInterface, error)
	DomainVNCPort(ctx context.Context, name string) (int, error)
	ShutdownDomain(ctx context.Context, name string) error
	RebootDomain(ctx context.Context, name string) error
	DestroyDomain(ctx context.Context, name string) error
	UndefineDomain(ctx context.Context, name string) error
}

// createDomainRequest 是创建域请求体。
type createDomainRequest struct {
	StoragePool            string             `json:"storage_pool,omitempty"`
	ImageStoragePool       string             `json:"image_storage_pool,omitempty"`
	StoragePoolPath        string             `json:"storage_pool_path,omitempty"`
	CloneMode              string             `json:"clone_mode,omitempty"`
	UseExistingDisk        bool               `json:"use_existing_disk,omitempty"`
	SourceDiskRelativePath string             `json:"source_disk_relative_path,omitempty"`
	MAC                    string             `json:"mac"`
	Initialization         *storage.CloudInit `json:"initialization"`
	Hardware               domainxml.Hardware `json:"hardware"`
	DataDisks              []struct {
		RelativePath string `json:"relative_path"`
		SizeGiB      int    `json:"size_gib"`
	} `json:"data_disks"`
	AdditionalNetworks []domainxml.NetworkSpec `json:"additional_networks"`
	Name               string                  `json:"name"`
	UUID               string                  `json:"uuid"`
	VCPU               int                     `json:"vcpu"`
	MemoryMiB          int                     `json:"memory_mib"`
	DiskRelativePath   string                  `json:"disk_relative_path"`
	DiskGiB            int                     `json:"disk_gib"`
	Network            string                  `json:"network"`
	NetworkType        string                  `json:"network_type"`
	NetworkBridge      string                  `json:"network_bridge"`
	VLANID             int                     `json:"vlan_id"`
	VNCPassword        string                  `json:"vnc_password"`
	ImageRelativePath  string                  `json:"image_relative_path"`
	ImageFormat        string                  `json:"image_format"`
	ImageChecksum      string                  `json:"image_checksum"`
	StartAfterCreate   *bool                   `json:"start_after_create"`
	Autostart          *bool                   `json:"autostart"`
}

// createDomainResponse 是创建域结果。
type createDomainResponse struct {
	InitializationDelivered bool   `json:"initialization_delivered"`
	UUID                    string `json:"uuid"`
	Name                    string `json:"name"`
	State                   string `json:"state"`
	VCPU                    int    `json:"vcpu"`
	MemoryMiB               int    `json:"memory_mib"`
	DiskPath                string `json:"disk_path"`
	DiskVirtualSizeBytes    int64  `json:"disk_virtual_size_bytes"`
	Created                 bool   `json:"created"`
}

// createDomainHandler 创建并启动域；同名域已存在时按幂等返回现状。
func createDomainHandler(deps Dependencies) http.HandlerFunc {
	return func(writer http.ResponseWriter, request *http.Request) {
		requestID := RequestIDFromContext(request.Context())
		ctx := request.Context()

		var payload createDomainRequest
		decoder := json.NewDecoder(http.MaxBytesReader(writer, request.Body, 64*1024))
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&payload); err != nil {
			writeAPIError(writer, deps.Logger, apierr.New(
				apierr.CodeInvalidArgument, "请求体解析失败", err,
			), requestID)
			return
		}

		if payload.UseExistingDisk {
			diskReferenceMutation.Lock()
			defer diskReferenceMutation.Unlock()
		} else {
			diskReferenceMutation.RLock()
			defer diskReferenceMutation.RUnlock()
		}
		if payload.CloneMode != "" && payload.CloneMode != "full" && payload.CloneMode != "linked" {
			writeAPIError(writer, deps.Logger, apierr.New(apierr.CodeInvalidArgument, "克隆模式无效", nil), requestID)
			return
		}
		if payload.UseExistingDisk && payload.CloneMode != "" {
			writeAPIError(writer, deps.Logger, apierr.New(apierr.CodeInvalidArgument, "直接挂载不能指定克隆模式", nil), requestID)
			return
		}
		if payload.ImageFormat == "ISO" && payload.CloneMode == "linked" {
			writeAPIError(writer, deps.Logger, apierr.New(apierr.CodeInvalidArgument, "ISO 安装不支持链接克隆", nil), requestID)
			return
		}
		diskRoot, rootErr := diskRootForPool(ctx, deps, payload.StoragePool)
		if rootErr != nil {
			writeAPIError(writer, deps.Logger, rootErr, requestID)
			return
		}
		if payload.StoragePoolPath != "" && diskRoot != payload.StoragePoolPath {
			writeAPIError(writer, deps.Logger, apierr.New(apierr.CodeConflict, "存储池目录已变化", nil), requestID)
			return
		}
		// 磁盘可能尚不存在，使用允许缺失的路径校验
		if !payload.UseExistingDisk {
			if err := storage.EnsureDiskParent(diskRoot, payload.DiskRelativePath); err != nil { writeAPIError(writer, deps.Logger, apierr.New(apierr.CodeInvalidArgument, "无法创建虚拟机用户目录", err), requestID); return }
		}
		for _, disk := range payload.DataDisks { if err := storage.EnsureDiskParent(diskRoot, disk.RelativePath); err != nil { writeAPIError(writer, deps.Logger, apierr.New(apierr.CodeInvalidArgument, "无法创建数据盘用户目录", err), requestID); return } }
		diskPath, err := storage.SafePathAllowMissing(diskRoot, payload.DiskRelativePath)
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		spec := domainxml.Spec{
			MAC:                payload.MAC,
			Hardware:           payload.Hardware,
			AdditionalNetworks: payload.AdditionalNetworks,
			Name:               payload.Name,
			UUID:               payload.UUID,
			VCPU:               payload.VCPU,
			MemoryMiB:          payload.MemoryMiB,
			DiskPath:           diskPath,
			Network:            payload.Network,
			NetworkType:        payload.NetworkType,
			NetworkBridge:      payload.NetworkBridge,
			VLANID:             payload.VLANID,
			VNCPassword:        payload.VNCPassword,
		}
		if payload.Initialization != nil {
			if payload.ImageFormat == "ISO" {
				writeAPIError(writer, deps.Logger, apierr.New(apierr.CodeInvalidArgument, "ISO 安装不支持 cloud-init 注入", nil), requestID)
				return
			}
			if err := storage.ValidateCloudInit(*payload.Initialization); err != nil {
				writeAPIError(writer, deps.Logger, err, requestID)
				return
			}
		}
		if err := domainxml.ValidateSpec(spec); err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		if len(payload.DataDisks) > 8 || len(payload.AdditionalNetworks) > 7 {
			writeAPIError(writer, deps.Logger, apierr.New(apierr.CodeInvalidArgument, "设备数量超限", nil), requestID)
			return
		}
		seen := map[string]bool{diskPath: true}
		for _, dataDisk := range payload.DataDisks {
			path, pathErr := storage.SafePathAllowMissing(diskRoot, dataDisk.RelativePath)
			if pathErr != nil {
				writeAPIError(writer, deps.Logger, pathErr, requestID)
				return
			}
			if seen[path] || dataDisk.SizeGiB < 1 || dataDisk.SizeGiB > 2048 {
				writeAPIError(writer, deps.Logger, apierr.New(apierr.CodeInvalidArgument, "数据盘路径重复或容量无效", nil), requestID)
				return
			}
			seen[path] = true
			spec.AdditionalDiskPaths = append(spec.AdditionalDiskPaths, path)
		}
		for _, network := range payload.AdditionalNetworks {
			if network.NetworkType == "" || network.NetworkType == "LIBVIRT_NETWORK" {
				if deps.Networks == nil {
					writeAPIError(writer, deps.Logger, errNoDomainLister, requestID)
					return
				}
				exists, err := deps.Networks.NetworkExists(ctx, network.Network)
				if err != nil {
					writeAPIError(writer, deps.Logger, err, requestID)
					return
				}
				if !exists {
					writeAPIError(writer, deps.Logger, apierr.New(apierr.CodeInvalidArgument, "附加网络不存在", nil), requestID)
					return
				}
			}
		}

		if err := checkHardwareCapabilities(deps, ctx, payload); err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		if _, err := domainxml.Build(spec); err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		// libvirt 网络需要确认存在；网桥/OVS 由 libvirt 在定义或启动时校验
		if payload.Network != "" && (payload.NetworkType == "" || payload.NetworkType == "LIBVIRT_NETWORK") {
			if deps.Networks == nil {
				writeAPIError(writer, deps.Logger, apierr.New(
					apierr.CodeInternalError, "网络查询依赖未初始化", nil,
				), requestID)
				return
			}
			existsNetwork, netErr := deps.Networks.NetworkExists(ctx, payload.Network)
			if netErr != nil {
				writeAPIError(writer, deps.Logger, netErr, requestID)
				return
			}
			if !existsNetwork {
				writeAPIError(writer, deps.Logger, apierr.New(
					apierr.CodeInvalidArgument, "网络不存在", nil,
				), requestID)
				return
			}
		}

		if deps.Virtualizer == nil {
			writeAPIError(writer, deps.Logger, errNoVirtualizer, requestID)
			return
		}

		unlock := lockCreation(payload.Name)
		defer unlock()
		if _, err := journalMatches(diskRoot, payload); err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		// 幂等：已存在同名域时直接返回现状，避免重复创建
		exists, err := deps.Virtualizer.DomainExists(ctx, payload.Name)
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		if exists {
			writeExistingDomain(writer, deps, ctx, payload, requestID)
			return
		}

		claimPaths := append([]string{diskPath}, spec.AdditionalDiskPaths...)
		if payload.UseExistingDisk {
			claimPaths = append([]string{}, spec.AdditionalDiskPaths...)
		}
		if payload.Initialization != nil {
			seed, err := storage.SafePathAllowMissing(diskRoot, filepath.Join(filepath.Dir(payload.DiskRelativePath), ".init-"+payload.UUID+".iso"))
			if err != nil {
				writeAPIError(writer, deps.Logger, err, requestID)
				return
			}
			claimPaths = append(claimPaths, seed)
		}
		resume, claimErr := claimCreation(diskRoot, payload, claimPaths)
		if claimErr != nil {
			writeAPIError(writer, deps.Logger, claimErr, requestID)
			return
		}
		var diskErr error
		diskReady := false
		if resume {
			format, size, err := storage.DiskInfo(ctx, diskPath)
			diskReady = err == nil && format == "QCOW2" && size == int64(payload.DiskGiB)*1024*1024*1024
		}
		if payload.UseExistingDisk {
			if payload.ImageRelativePath != "" || payload.SourceDiskRelativePath != "" || payload.Initialization != nil {
				writeAPIError(writer, deps.Logger, apierr.New(apierr.CodeInvalidArgument, "直接使用系统盘不可同时指定镜像、克隆或初始化", nil), requestID)
				return
			}
			checker, ok := deps.Virtualizer.(interface {
				CheckUnusedDisk(context.Context, string, string) error
			})
			if !ok {
				writeAPIError(writer, deps.Logger, apierr.New(apierr.CodeConflict, "节点不支持磁盘引用检查", nil), requestID)
				return
			}
			if err := checker.CheckUnusedDisk(ctx, diskRoot, payload.DiskRelativePath); err != nil {
				writeAPIError(writer, deps.Logger, err, requestID)
				return
			}
			info, err := storage.InspectExistingDisk(ctx, diskRoot, payload.DiskRelativePath)
			if err != nil {
				writeAPIError(writer, deps.Logger, err, requestID)
				return
			}
			if int64(payload.DiskGiB) != (info.VirtualSizeBytes+1024*1024*1024-1)/(1024*1024*1024) {
				writeAPIError(writer, deps.Logger, apierr.New(apierr.CodeConflict, "系统盘容量已变化", nil), requestID)
				return
			}
		} else if payload.SourceDiskRelativePath != "" {
			if payload.ImageRelativePath != "" || payload.Initialization != nil || payload.SourceDiskRelativePath == payload.DiskRelativePath {
				writeAPIError(writer, deps.Logger, apierr.New(apierr.CodeInvalidArgument, "源磁盘参数冲突", nil), requestID)
				return
			}
			checker, ok := deps.Virtualizer.(interface {
				CheckUnusedDisk(context.Context, string, string) error
			})
			if !ok {
				writeAPIError(writer, deps.Logger, apierr.New(apierr.CodeConflict, "节点不支持源磁盘引用校验", nil), requestID)
				return
			}
			if err := checker.CheckUnusedDisk(ctx, diskRoot, payload.SourceDiskRelativePath); err != nil {
				writeAPIError(writer, deps.Logger, err, requestID)
				return
			}
			if !diskReady && payload.CloneMode == "linked" {
				diskErr = storage.CloneLinked(ctx, diskRoot, payload.SourceDiskRelativePath, "", "", diskPath, payload.DiskGiB)
			} else if !diskReady {
				diskErr = storage.CloneRetainedDisk(ctx, diskRoot, payload.SourceDiskRelativePath, diskPath, payload.DiskGiB)
			}
		} else if payload.ImageRelativePath != "" {
			imageRoot, rootErr := imageRootForPool(ctx, deps, payload.ImageStoragePool)
			if rootErr != nil { writeAPIError(writer, deps.Logger, rootErr, requestID); return }
			if payload.ImageFormat == "ISO" {
				info, inspectErr := storage.InspectContext(ctx, imageRoot, payload.ImageRelativePath)
				if inspectErr != nil {
					writeAPIError(writer, deps.Logger, inspectErr, requestID)
					return
				}
				if info.Format != "ISO" || len(payload.ImageChecksum) != 64 || !strings.EqualFold(info.ChecksumSHA256, payload.ImageChecksum) {
					writeAPIError(writer, deps.Logger, apierr.New(apierr.CodeConflict, "ISO 格式或摘要不匹配", nil), requestID)
					return
				}
				spec.ISOPath, diskErr = storage.SafePath(imageRoot, payload.ImageRelativePath)
				if diskErr == nil {
					diskErr = storage.CreateDisk(ctx, diskPath, payload.DiskGiB)
				}
			} else if !diskReady && payload.CloneMode == "linked" {
				diskErr = storage.CloneLinked(ctx, imageRoot, payload.ImageRelativePath, payload.ImageChecksum, payload.ImageFormat, diskPath, payload.DiskGiB)
			} else if !diskReady {
				diskErr = storage.CloneImage(ctx, imageRoot, payload.ImageRelativePath, payload.ImageChecksum, payload.ImageFormat, diskPath, payload.DiskGiB)
			}
		} else {
			diskErr = storage.CreateDisk(ctx, diskPath, payload.DiskGiB)
		}
		if err := diskErr; err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		for index, dataDisk := range payload.DataDisks {
			if err := storage.CreateDisk(ctx, spec.AdditionalDiskPaths[index], dataDisk.SizeGiB); err != nil {
				writeAPIError(writer, deps.Logger, err, requestID)
				return
			}
		}
		format, virtualSize, err := storage.DiskInfo(ctx, diskPath)
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		if strings.ToUpper(format) != strings.ToUpper(domainxml.DiskFormat) {
			writeAPIError(writer, deps.Logger, apierr.New(
				apierr.CodeOperationFailed, "磁盘格式与预期不符", nil,
			), requestID)
			return
		}

		if payload.Initialization != nil {
			seed, err := storage.CloudInitISO(ctx, filepath.Dir(diskPath), payload.UUID, payload.Name, *payload.Initialization)
			if err != nil {
				writeAPIError(writer, deps.Logger, err, requestID)
				return
			}
			spec.SeedPath = seed
		}
		content, err := domainxml.Build(spec)
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		if err := deps.Virtualizer.DefineDomain(ctx, content); err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		if payload.Autostart != nil {
			setter, ok := deps.Virtualizer.(interface {
				SetDomainAutostart(context.Context, string, bool) error
			})
			if !ok {
				writeAPIError(writer, deps.Logger, apierr.New(apierr.CodeOperationFailed, "此 Agent 不支持自启控制", nil), requestID)
				return
			}
			if err := setter.SetDomainAutostart(ctx, payload.Name, *payload.Autostart); err != nil {
				writeAPIError(writer, deps.Logger, err, requestID)
				return
			}
		}
		if payload.StartAfterCreate == nil || *payload.StartAfterCreate {
			if err := deps.Virtualizer.StartDomain(ctx, payload.Name); err != nil {
				writeAPIError(writer, deps.Logger, err, requestID)
				return
			}
		}

		dump, err := deps.Virtualizer.DumpXML(ctx, payload.Name)
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		actual, err := domainxml.Parse(dump)
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		if actual.UUID != payload.UUID || actual.MemoryMiB != payload.MemoryMiB || actual.VCPU != payload.VCPU {
			writeAPIError(writer, deps.Logger, apierr.New(
				apierr.CodeConflict, "创建结果与请求规格不一致", nil,
			), requestID)
			return
		}

		state, err := deps.Virtualizer.DomainState(ctx, payload.Name)
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		writeJSON(writer, http.StatusCreated, createDomainResponse{
			InitializationDelivered: payload.Initialization != nil,
			UUID:                    actual.UUID,
			Name:                    actual.Name,
			State:                   state,
			VCPU:                    actual.VCPU,
			MemoryMiB:               actual.MemoryMiB,
			DiskPath:                diskPath,
			DiskVirtualSizeBytes:    virtualSize,
			Created:                 true,
		})
	}
}

// writeExistingDomain 返回已存在域的现状（幂等路径）。
func writeExistingDomain(writer http.ResponseWriter, deps Dependencies, ctx context.Context, payload createDomainRequest, requestID string) {
	dump, err := deps.Virtualizer.DumpXML(ctx, payload.Name)
	if err != nil {
		writeAPIError(writer, deps.Logger, err, requestID)
		return
	}
	actual, err := domainxml.Parse(dump)
	if err != nil {
		writeAPIError(writer, deps.Logger, err, requestID)
		return
	}
	if actual.UUID != payload.UUID {
		writeAPIError(writer, deps.Logger, apierr.New(
			apierr.CodeConflict, "同名域存在但 UUID 不一致", nil,
		), requestID)
		return
	}
	state, err := deps.Virtualizer.DomainState(ctx, payload.Name)
	if err != nil {
		writeAPIError(writer, deps.Logger, err, requestID)
		return
	}
	if payload.Autostart != nil {
		setter, ok := deps.Virtualizer.(interface {
			SetDomainAutostart(context.Context, string, bool) error
		})
		if !ok {
			writeAPIError(writer, deps.Logger, apierr.New(apierr.CodeOperationFailed, "节点不支持自启控制", nil), requestID)
			return
		}
		if err := setter.SetDomainAutostart(ctx, payload.Name, *payload.Autostart); err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
	}
	if payload.StartAfterCreate != nil && *payload.StartAfterCreate && state == "SHUTOFF" {
		if err := deps.Virtualizer.StartDomain(ctx, payload.Name); err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
		state, err = deps.Virtualizer.DomainState(ctx, payload.Name)
		if err != nil {
			writeAPIError(writer, deps.Logger, err, requestID)
			return
		}
	}
	var virtualSize int64
	if _, size, infoErr := storage.DiskInfo(ctx, actual.DiskPath); infoErr == nil {
		virtualSize = size
	}
	writeJSON(writer, http.StatusOK, createDomainResponse{
		InitializationDelivered: payload.Initialization != nil,
		UUID:                    actual.UUID,
		Name:                    actual.Name,
		State:                   state,
		VCPU:                    actual.VCPU,
		MemoryMiB:               actual.MemoryMiB,
		DiskPath:                actual.DiskPath,
		DiskVirtualSizeBytes:    virtualSize,
		Created:                 false,
	})
}
