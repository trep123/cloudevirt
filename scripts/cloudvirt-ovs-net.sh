#!/usr/bin/env bash
# Dedicated OVS network; never attach or reconfigure the management interface.
set -Eeuo pipefail
OVS_BRIDGE="${OVS_BRIDGE:-ovsbr0}"
OVS_INTERNAL="${OVS_INTERNAL:-ovsbr0-int}"
OVS_SUBNET="${OVS_SUBNET:-192.168.150.0/24}"
OVS_GATEWAY="${OVS_GATEWAY:-192.168.150.1}"
OVS_UPLINK="${OVS_UPLINK:-$(ip -4 route show default | awk 'NR==1{print $5}')}"
for name in "$OVS_BRIDGE" "$OVS_INTERNAL" "$OVS_UPLINK"; do
    [[ "$name" =~ ^[a-zA-Z0-9_.:-]{1,15}$ ]] || { echo "Invalid interface name" >&2; exit 1; }
done
[[ "$OVS_UPLINK" != "$OVS_BRIDGE" && "$OVS_UPLINK" != "$OVS_INTERNAL" ]] || exit 1
export OVS_SUBNET OVS_GATEWAY
OVS_PREFIX=$(python3 - <<'PY'
import ipaddress, os
network = ipaddress.ip_network(os.environ['OVS_SUBNET'], strict=True)
gateway = ipaddress.ip_address(os.environ['OVS_GATEWAY'])
assert network.version == 4 and gateway in network
assert gateway not in (network.network_address, network.broadcast_address)
print(network.prefixlen)
PY
)
ip link show dev "$OVS_UPLINK" >/dev/null
ovs-vsctl --may-exist add-br "$OVS_BRIDGE"
ovs-vsctl --may-exist add-port "$OVS_BRIDGE" "$OVS_INTERNAL" -- set Interface "$OVS_INTERNAL" type=internal
ip link set "$OVS_BRIDGE" up
ip link set "$OVS_INTERNAL" up
ip addr replace "$OVS_GATEWAY/$OVS_PREFIX" dev "$OVS_INTERNAL"
sysctl -w net.ipv4.ip_forward=1 >/dev/null

# Delete and replace our own table in one nftables transaction.
# Other bridges/forwarding rules are left to their existing firewall chains.
DELETE_TABLE=""
if nft list table inet cloudvirt_ovs >/dev/null 2>&1; then
    DELETE_TABLE="delete table inet cloudvirt_ovs"
fi
nft -f - <<RULES
$DELETE_TABLE
table inet cloudvirt_ovs {
    chain input {
        type filter hook input priority -5; policy accept;
        iifname "$OVS_INTERNAL" udp sport 68 udp dport 67 accept
        iifname "$OVS_INTERNAL" ip protocol icmp accept
        iifname "$OVS_INTERNAL" drop
    }
    chain forward {
        type filter hook forward priority -5; policy accept;
        iifname "$OVS_INTERNAL" ip daddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, 127.0.0.0/8 } drop
        iifname "$OVS_INTERNAL" oifname "$OVS_UPLINK" ip saddr $OVS_SUBNET ct state { new, established, related } accept
        iifname "$OVS_UPLINK" oifname "$OVS_INTERNAL" ip daddr $OVS_SUBNET ct state { established, related } accept
        iifname "$OVS_INTERNAL" drop
        oifname "$OVS_INTERNAL" drop
    }
    chain postrouting {
        type nat hook postrouting priority 100; policy accept;
        ip saddr $OVS_SUBNET oifname "$OVS_UPLINK" masquerade
    }
}
RULES
