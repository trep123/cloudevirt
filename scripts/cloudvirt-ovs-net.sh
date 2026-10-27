#!/bin/bash
# OVS 独立网络：ovsbr0 + ovsbr0-int 网关 + nft NAT
set -u

if ! ovs-vsctl br-exists ovsbr0 2>/dev/null; then
    ovs-vsctl add-br ovsbr0
fi
ip link set ovsbr0 up

# 清理旧的 veth 复用链路
ovs-vsctl --if-exists del-port ovsbr0 ovs-virbr
ip link del ovs-virbr 2>/dev/null || true

ovs-vsctl --may-exist add-port ovsbr0 ovsbr0-int -- set Interface ovsbr0-int type=internal
ip link set ovsbr0-int up
ip addr replace 192.168.150.1/24 dev ovsbr0-int

sysctl -w net.ipv4.ip_forward=1 >/dev/null

nft delete table inet cloudvirt_ovs 2>/dev/null || true
nft add table inet cloudvirt_ovs
nft 'add chain inet cloudvirt_ovs forward { type filter hook forward priority 0; policy accept; }'
nft add rule inet cloudvirt_ovs forward iifname "ovsbr0-int" accept
nft add rule inet cloudvirt_ovs forward oifname "ovsbr0-int" accept
nft 'add chain inet cloudvirt_ovs postrouting { type nat hook postrouting priority 100; policy accept; }'
nft add rule inet cloudvirt_ovs postrouting ip saddr 192.168.150.0/24 oifname "ens18" masquerade
