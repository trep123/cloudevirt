#!/bin/bash
# 将 CloudVirt OVS 网桥 ovsbr0 通过 veth 接入 libvirt 默认 NAT 网络，
# 复用 default 网络的 DHCP 与 NAT，避免改动管理网卡 ens18。
set -u

if ! ovs-vsctl br-exists ovsbr0 2>/dev/null; then
    ovs-vsctl add-br ovsbr0
fi
ip link set ovsbr0 up

if ! ip link show ovs-virbr >/dev/null 2>&1; then
    ip link add ovs-virbr type veth peer name virbr-ovs
fi
ovs-vsctl --may-exist add-port ovsbr0 ovs-virbr
ip link set ovs-virbr up
ip link set virbr-ovs up

# libvirt default 网络可能稍后才创建 virbr0，最多等待 30 秒
for _ in $(seq 1 30); do
    if ip link show virbr0 >/dev/null 2>&1; then
        ip link set virbr-ovs master virbr0 2>/dev/null || true
        exit 0
    fi
    sleep 1
done
exit 0
