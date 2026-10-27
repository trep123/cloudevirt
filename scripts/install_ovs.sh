#!/usr/bin/env bash
# Invoked by install.sh --enable-ovs, or explicitly as root.
set -Eeuo pipefail
umask 077
[[ $EUID == 0 ]] || { echo "Run as root" >&2; exit 1; }
APP_DIR="${1:-/opt/cloudvirt}"
[[ "$APP_DIR" == /opt/cloudvirt ]] || { echo "Unsupported application directory" >&2; exit 1; }
CONFIG_DIR=/etc/cloudvirt
OVS_SUBNET="${CLOUDVIRT_OVS_SUBNET:-192.168.150.0/24}"
OVS_GATEWAY="${CLOUDVIRT_OVS_GATEWAY:-192.168.150.1}"
OVS_DHCP_START="${CLOUDVIRT_OVS_DHCP_START:-192.168.150.100}"
OVS_DHCP_END="${CLOUDVIRT_OVS_DHCP_END:-192.168.150.200}"
OVS_UPLINK="${CLOUDVIRT_UPLINK:-$(ip -4 route show default | awk 'NR==1{print $5}')}"
[[ "$OVS_UPLINK" =~ ^[a-zA-Z0-9_.:-]{1,15}$ ]] || { echo "Invalid uplink" >&2; exit 1; }
ip link show dev "$OVS_UPLINK" >/dev/null
export OVS_SUBNET OVS_GATEWAY OVS_DHCP_START OVS_DHCP_END
OVS_NETMASK=$(python3 - <<'PY'
import ipaddress, json, os, subprocess
network = ipaddress.ip_network(os.environ['OVS_SUBNET'], strict=True)
assert network.version == 4 and 16 <= network.prefixlen <= 28, 'Use an IPv4 /16 to /28 subnet'
gateway, start, end = [ipaddress.ip_address(os.environ[key]) for key in
                       ('OVS_GATEWAY', 'OVS_DHCP_START', 'OVS_DHCP_END')]
assert all(ip in network and ip not in (network.network_address, network.broadcast_address)
           for ip in (gateway, start, end)), 'Addresses must be usable hosts in subnet'
assert start <= end and not start <= gateway <= end, 'Invalid DHCP pool'
routes = json.loads(subprocess.check_output(['ip', '-j', '-4', 'route', 'show']))
for route in routes:
    dst = route.get('dst', '')
    if not dst or dst == 'default' or route.get('dev') in {'ovsbr0', 'ovsbr0-int'}:
        continue
    other = ipaddress.ip_network(dst, strict=False)
    assert not network.overlaps(other), f'OVS subnet overlaps existing route: {dst}'
print(network.netmask)
PY
)
if [[ -e "$CONFIG_DIR/ovs.env" ]]; then
    # Existing networks require explicit migration; never silently renumber them.
    for entry in "OVS_SUBNET=$OVS_SUBNET" "OVS_GATEWAY=$OVS_GATEWAY" "OVS_UPLINK=$OVS_UPLINK"; do
        grep -Fxq "$entry" "$CONFIG_DIR/ovs.env" || { echo "Existing OVS configuration differs; migrate it explicitly" >&2; exit 1; }
    done
fi
export DEBIAN_FRONTEND=noninteractive
apt-get install -y openvswitch-switch dnsmasq-base nftables
systemctl enable --now openvswitch-switch
if ip link show dev ovsbr0 >/dev/null 2>&1 && ! ovs-vsctl br-exists ovsbr0; then
    echo "ovsbr0 already exists and is not an OVS bridge" >&2
    exit 1
fi
getent passwd cloudvirt-dhcp >/dev/null || useradd --system --home-dir /var/lib/cloudvirt-dhcp --shell /usr/sbin/nologin cloudvirt-dhcp
install -d -o cloudvirt-dhcp -g cloudvirt-dhcp -m 0755 /var/lib/cloudvirt-dhcp
cat > "$CONFIG_DIR/ovs.env" <<ENV
OVS_BRIDGE=ovsbr0
OVS_INTERNAL=ovsbr0-int
OVS_SUBNET=$OVS_SUBNET
OVS_GATEWAY=$OVS_GATEWAY
OVS_UPLINK=$OVS_UPLINK
ENV
chmod 0600 "$CONFIG_DIR/ovs.env"
cat > "$CONFIG_DIR/ovs-dhcp.conf" <<ENV
interface=ovsbr0-int
bind-interfaces
port=0
user=cloudvirt-dhcp
group=cloudvirt-dhcp
dhcp-authoritative
dhcp-range=$OVS_DHCP_START,$OVS_DHCP_END,$OVS_NETMASK,12h
dhcp-option=3,$OVS_GATEWAY
dhcp-option=6,1.1.1.1,8.8.8.8
dhcp-leasefile=/var/lib/cloudvirt-dhcp/leases
log-dhcp
ENV
chmod 0644 "$CONFIG_DIR/ovs-dhcp.conf"
dnsmasq --test --conf-file="$CONFIG_DIR/ovs-dhcp.conf"
printf 'net.ipv4.ip_forward=1\n' > /etc/sysctl.d/99-cloudvirt-ovs.conf
sysctl -w net.ipv4.ip_forward=1 >/dev/null
install -m 0750 "$APP_DIR/scripts/cloudvirt-ovs-net.sh" /usr/local/sbin/cloudvirt-ovs-net.sh
cat > /etc/systemd/system/cloudvirt-ovs-net.service <<'UNIT'
[Unit]
Description=CloudVirt dedicated OVS bridge and NAT
After=network-online.target openvswitch-switch.service
Wants=network-online.target
Requires=openvswitch-switch.service
[Service]
Type=oneshot
EnvironmentFile=/etc/cloudvirt/ovs.env
ExecStart=/usr/local/sbin/cloudvirt-ovs-net.sh
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/systemd/system/cloudvirt-ovs-dhcp.service <<'UNIT'
[Unit]
Description=CloudVirt dedicated DHCP
After=cloudvirt-ovs-net.service
Requires=cloudvirt-ovs-net.service
[Service]
Type=simple
ExecStart=/usr/sbin/dnsmasq --keep-in-foreground --conf-file=/etc/cloudvirt/ovs-dhcp.conf
Restart=on-failure
RestartSec=3
UMask=0022
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/cloudvirt-dhcp
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable cloudvirt-ovs-net cloudvirt-ovs-dhcp
systemctl restart cloudvirt-ovs-net cloudvirt-ovs-dhcp
systemctl is-active --quiet cloudvirt-ovs-dhcp
nft list table inet cloudvirt_ovs >/dev/null
if command -v ufw >/dev/null && ufw status | grep -q '^Status: active'; then
    ufw route allow in on ovsbr0-int out on "$OVS_UPLINK" from "$OVS_SUBNET" comment 'CloudVirt OVS egress'
    ufw allow in on ovsbr0-int proto udp from any port 68 to any port 67 comment 'CloudVirt DHCP'
fi
sed -i 's|^CLOUDVIRT_DHCP_LEASE_FILE=.*|CLOUDVIRT_DHCP_LEASE_FILE=/var/lib/cloudvirt-dhcp/leases|' "$CONFIG_DIR/agent.env"
systemctl restart cloudvirt-agent
(
    set -a
    # shellcheck source=/dev/null
    . "$CONFIG_DIR/management.env"
    set +a
    cd "$APP_DIR/apps/management"
    runuser -u cloudvirt -- "$APP_DIR/.venv/bin/python" manage.py shell --verbosity 0 <<'PY'
import os
from apps.networks.models import Network
existing = Network.objects.filter(name='ovs-nat').first()
if existing and (existing.type != 'OVS' or existing.bridge != 'ovsbr0' or existing.vlan_id):
    raise RuntimeError('Existing ovs-nat record does not match the installer-managed untagged bridge')
Network.objects.update_or_create(name='ovs-nat', defaults={
    'type': 'OVS', 'bridge': 'ovsbr0', 'subnet': os.environ['OVS_SUBNET'],
    'gateway': os.environ['OVS_GATEWAY'], 'dhcp_enabled': True,
    'dhcp_start': os.environ['OVS_DHCP_START'], 'dhcp_end': os.environ['OVS_DHCP_END'],
    'dns_servers': '1.1.1.1,8.8.8.8',
})
PY
)
echo "OVS configured: ovsbr0 / $OVS_SUBNET; physical management interface was not bridged."
