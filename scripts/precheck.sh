#!/usr/bin/env bash
# 部署前环境检查：OS、CPU 虚拟化标志、/dev/kvm、libvirt、磁盘空间、端口占用。
# 用法: bash scripts/precheck.sh
# 退出码: 0=全部通过; 1=存在阻断项（如缺少 /dev/kvm）; 2=仅有告警项。

set -uo pipefail

readonly REQUIRED_FREE_KB=$((10 * 1024 * 1024))  # /var/lib/cloudvirt 至少 10 GiB 可用
readonly CHECK_PORTS=(8000 9100)

# 开发/测试环境可显式声明使用 QEMU TCG 软件模拟，此时缺少 /dev/kvm 降级为告警
ALLOW_TCG=${CLOUDVIRT_ALLOW_TCG:-false}

fail_count=0
warn_count=0

log_pass() { printf '[PASS] %s\n' "$1"; }
log_warn() { printf '[WARN] %s\n' "$1"; warn_count=$((warn_count + 1)); }
log_fail() { printf '[FAIL] %s\n' "$1"; fail_count=$((fail_count + 1)); }

echo "=== CloudVirt 部署前检查 ==="

# 1) 操作系统
if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    if [[ "${ID:-}" == "ubuntu" ]]; then
        log_pass "操作系统: ${PRETTY_NAME:-Ubuntu}"
    else
        log_warn "操作系统为 ${PRETTY_NAME:-未知}，官方基线为 Ubuntu Server LTS"
    fi
else
    log_warn "无法读取 /etc/os-release，跳过操作系统检查"
fi

# 2) CPU 虚拟化标志
if grep -qoE '(vmx|svm)' /proc/cpuinfo >/dev/null 2>&1; then
    log_pass "CPU 支持硬件虚拟化"
elif [ "${ALLOW_TCG}" = "true" ]; then
    log_warn "CPU 未报告硬件虚拟化标志（vmx/svm），按 CLOUDVIRT_ALLOW_TCG=true 降级为 TCG 模拟"
else
    log_fail "CPU 未报告硬件虚拟化标志（vmx/svm），请检查固件设置"
fi

# 3) /dev/kvm：默认缺失即为阻断项；开发测试环境显式声明后才降级为告警
if [ -e /dev/kvm ]; then
    log_pass "存在 /dev/kvm（硬件加速可用）"
elif [ "${ALLOW_TCG}" = "true" ]; then
    log_warn "缺少 /dev/kvm，按 CLOUDVIRT_ALLOW_TCG=true 降级：仅可用于开发/测试的 QEMU TCG 模拟，性能与行为不代表生产"
else
    log_fail "缺少 /dev/kvm，KVM 硬件加速不可用；开发测试环境可设置 CLOUDVIRT_ALLOW_TCG=true 明确降级"
fi

# 4) libvirt
if command -v virsh >/dev/null 2>&1; then
    if virsh -c qemu:///system list --all >/dev/null 2>&1; then
        log_pass "libvirt 可连接（qemu:///system）"
        if virsh -c qemu:///system capabilities 2>/dev/null | grep -q "domain type='kvm'"; then
            log_pass "libvirt 支持 KVM 加速域"
        else
            log_warn "libvirt 仅支持 TCG 模拟域（type=qemu），不具备硬件加速"
        fi
    else
        log_fail "virsh 无法连接 qemu:///system，请检查 libvirtd 服务与权限"
    fi
else
    log_warn "未安装 virsh（libvirt-clients），虚拟机管理能力不可用"
fi

# 5) 磁盘空间
if [ -d /var/lib/cloudvirt ]; then
    free_kb=$(df -Pk /var/lib/cloudvirt | awk 'NR==2 {print $4}')
else
    free_kb=$(df -Pk /var | awk 'NR==2 {print $4}')
fi
if [ "${free_kb:-0}" -ge "${REQUIRED_FREE_KB}" ]; then
    log_pass "可用磁盘空间: $((free_kb / 1024 / 1024)) GiB"
else
    log_warn "可用磁盘空间不足 10 GiB（当前 $((free_kb / 1024 / 1024)) GiB）"
fi

# 6) 端口占用
for port in "${CHECK_PORTS[@]}"; do
    if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | awk '{print $4}' | grep -q ":${port}$"; then
        log_warn "端口 ${port} 已被占用，请确认是否为本服务实例"
    else
        log_pass "端口 ${port} 可用"
    fi
done

echo "=== 检查结束: FAIL=${fail_count} WARN=${warn_count} ==="
if [ "${fail_count}" -gt 0 ]; then
    echo "存在阻断项，不得继续部署。"
    exit 1
fi
if [ "${warn_count}" -gt 0 ]; then
    echo "仅有告警项，可继续但需记录。"
    exit 2
fi
exit 0
