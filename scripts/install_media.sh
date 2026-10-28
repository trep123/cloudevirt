#!/usr/bin/env bash
# Optional local-only media signaling, authenticated through CloudVirt.
set -Eeuo pipefail
umask 077
VERSION="${CLOUDVIRT_MEDIAMTX_VERSION:-v1.21.3}"
HOST="${CLOUDVIRT_MEDIA_HOST:-}"
if [[ "${1:-}" == --help ]]; then
    printf '%s\n' 'sudo bash scripts/install_media.sh --host LAN_IP'
    exit 0
fi
while (($#)); do
    case "$1" in --host) HOST=${2:?Missing host}; shift 2;; *) printf 'Unknown option: %s\n' "$1" >&2; exit 1;; esac
done
[[ $EUID == 0 && $(uname -m) == x86_64 ]] || { printf 'Ubuntu amd64 root required\n' >&2; exit 1; }
[[ "$VERSION" =~ ^v1[.][0-9]+[.][0-9]+$ ]] || exit 1
python3 - "$HOST" <<'PY'
import ipaddress,sys
address=ipaddress.ip_address(sys.argv[1])
if address.version != 4 or address.is_loopback or address.is_multicast or address.is_unspecified:
    raise SystemExit('Provide the reachable LAN IPv4 address with --host')
PY
task_media_cidr="${CLOUDVIRT_MEDIA_ALLOWED_CIDR:-$HOST/24}"
task_media_cidr=$(python3 - "$task_media_cidr" <<'PY'
import ipaddress,sys
print(ipaddress.ip_network(sys.argv[1],strict=False))
PY
)
task_media_tmp=$(mktemp -d /var/tmp/cloudvirt-media.XXXXXX)
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3-gi python3-gst-1.0 gir1.2-gstreamer-1.0 gstreamer1.0-tools \
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-rtsp
trap 'rm -rf -- "$task_media_tmp"' EXIT
asset="mediamtx_${VERSION}_linux_amd64.tar.gz"
base="https://github.com/bluenviron/mediamtx/releases/download/$VERSION"
curl --proto '=https' --tlsv1.2 -fSL --retry 3 "$base/checksums.sha256" -o "$task_media_tmp/checksums.sha256"
curl --proto '=https' --tlsv1.2 -fSL --retry 3 "$base/$asset" -o "$task_media_tmp/$asset"
expected=$(awk -v file="$asset" '$2==file || $2=="*"file {print $1}' "$task_media_tmp/checksums.sha256")
[[ "$expected" =~ ^[a-fA-F0-9]{64}$ ]] || { printf 'Release checksum missing\n' >&2; exit 1; }
[[ $(sha256sum "$task_media_tmp/$asset" | awk '{print $1}') == "$expected" ]] || { printf 'Checksum mismatch\n' >&2; exit 1; }
tar -xzf "$task_media_tmp/$asset" -C "$task_media_tmp" mediamtx
id cloudvirt-media >/dev/null 2>&1 || useradd --system --home-dir /var/lib/cloudvirt-media --shell /usr/sbin/nologin cloudvirt-media
install -d -m 0755 /opt/cloudvirt/runtime/mediamtx /etc/cloudvirt
install -d -o cloudvirt-media -g cloudvirt-media -m 0750 /var/lib/cloudvirt-media
install -m 0755 "$task_media_tmp/mediamtx" /opt/cloudvirt/runtime/mediamtx/mediamtx
if [[ ! -e /etc/cloudvirt/mediamtx.yml ]]; then
    cat > /etc/cloudvirt/mediamtx.yml <<YAML
logLevel: info
logDestinations: [stdout]
authMethod: internal
authInternalUsers:
  - user: any
    ips: ['127.0.0.1', '::1']
    permissions:
      - action: read
      - action: publish
      - action: api
api: true
apiAddress: 127.0.0.1:9997
rtsp: true
rtspAddress: 127.0.0.1:8554
rtspTransports: [tcp]
rtmp: false
hls: false
srt: false
moq: false
playback: false
metrics: false
pprof: false
webrtc: true
webrtcAddress: 127.0.0.1:8889
webrtcLocalUDPAddress: :8189
webrtcLocalTCPAddress: ''
webrtcIPsFromInterfaces: false
webrtcAdditionalHosts: ['$HOST']
webrtcICEServers2: []
paths:
  all_others:
YAML
    chown root:cloudvirt-media /etc/cloudvirt/mediamtx.yml
    chmod 0640 /etc/cloudvirt/mediamtx.yml
fi
cat > /etc/systemd/system/cloudvirt-media.service <<'UNIT'
[Unit]
Description=CloudVirt local media gateway
After=network.target
[Service]
User=cloudvirt-media
Group=cloudvirt-media
WorkingDirectory=/var/lib/cloudvirt-media
ExecStart=/opt/cloudvirt/runtime/mediamtx/mediamtx /etc/cloudvirt/mediamtx.yml
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/cloudvirt-media
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now cloudvirt-media
if command -v ufw >/dev/null && ufw status | grep -q '^Status: active'; then
    ufw allow from "$task_media_cidr" to any port 8189 proto udp comment 'CloudVirt authenticated WebRTC media'
fi
systemctl is-active --quiet cloudvirt-media
printf 'Media gateway ready. ICE host: %s; UDP: 8189; HTTP/RTSP/API: loopback only\n' "$HOST"
