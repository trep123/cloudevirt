#!/usr/bin/env bash
# CloudVirt single-host installer for Ubuntu 26.x / amd64.
# Run from the complete source tree: sudo bash install.sh
set -Eeuo pipefail
umask 077

APP_DIR=/opt/cloudvirt
CONFIG_DIR=/etc/cloudvirt
DATA_DIR=/var/lib/libvirt/images/cloudvirt
WEB_ROOT=/var/www/cloudvirt
REPO_URL="${CLOUDVIRT_REPO_URL:-https://github.com/trep123/cloudevirt.git}"
REPO_REF="${CLOUDVIRT_REPO_REF:-master}"
SOURCE_DIR=""
OFFLINE_DIR="${CLOUDVIRT_OFFLINE_DIR:-}"
DOMAIN="${CLOUDVIRT_DOMAIN:-}"
PORT="${CLOUDVIRT_PORT:-443}"
HTTPS=true
ENABLE_OVS=false
STORAGE_ROOTS=()
BRIDGE_ALLOWED=()
ALLOW_DESTRUCTIVE=false
TMP_DIR=""
INSTALL_STATE=""
INSTALL_TRACKING=false
STEP=preflight

usage() {
    cat <<'HELP'
CloudVirt / Ubuntu 26.x amd64
  sudo bash install.sh [options]

  --source DIR          Install this complete local source tree (preferred).
  --offline-dir DIR     Use verified local Node/Python/npm/Go packages.
  --domain HOST         Hostname or IPv4 address; defaults to primary host IP.
  --port PORT           HTTPS listen port; default 443.
  --http                Use HTTP instead of self-signed HTTPS (default port 80).
  --enable-ovs          Configure a dedicated OVS bridge, DHCP and NAT.
  --storage-root DIR    Approve an additional VM storage directory (repeatable).
  --bridge-allow-interface NAME  Exempt a NIC from management detection (repeatable).
  --allow-destructive   Allow Agent force-stop and deletion operations.
  --help                Show this help without changing the system.

If no local source is found, clone CLOUDVIRT_REPO_URL at CLOUDVIRT_REPO_REF.
Unpublished local changes are included only when installing the complete source package.
With --source, bundled offline/linux-amd64 packages are selected automatically.
An explicitly selected --offline-dir must be complete and match the source locks.
OVS variables: CLOUDVIRT_OVS_SUBNET, CLOUDVIRT_OVS_GATEWAY,
CLOUDVIRT_OVS_DHCP_START, CLOUDVIRT_OVS_DHCP_END, CLOUDVIRT_UPLINK.
Initial credentials: /etc/cloudvirt/initial-admin.txt (root only).
HELP
}

log() { printf '\n[CloudVirt] %s\n' "$*"; }
die() {
    printf '\n[CloudVirt] ERROR: %s\n' "$*" >&2
    [[ ${INSTALL_TRACKING:-false} != true ]] || touch "$INSTALL_STATE/provenance-incomplete"
    exit 1
}
on_error() {
    local rc=$?
    [[ ${INSTALL_TRACKING:-false} != true ]] || touch "$INSTALL_STATE/provenance-incomplete"
    printf '\n[CloudVirt] Failed at step %s (line %s, exit %s).\n' "$STEP" "$1" "$rc" >&2
    printf 'Existing database and disk images were not deleted. Review: journalctl -u cloudvirt-management -u cloudvirt-agent -u cloudvirt-worker -n 80\n' >&2
    exit "$rc"
}
cleanup() {
    if [[ -n "$TMP_DIR" && "$TMP_DIR" == /var/tmp/cloudvirt-install.* && -d "$TMP_DIR" ]]; then
        rm -rf -- "$TMP_DIR"
    fi
}
trap 'on_error "$LINENO"' ERR
trap cleanup EXIT

while (($#)); do
    case "$1" in
        --source|--offline-dir|--domain|--port)
            (($# >= 2)) || die "Missing value for $1"
            case "$1" in --source) SOURCE_DIR=$2;; --offline-dir) OFFLINE_DIR=$2;; --domain) DOMAIN=$2;; --port) PORT=$2;; esac
            shift 2;;
        --http) HTTPS=false; [[ "$PORT" != 443 ]] || PORT=80; shift;;
        --enable-ovs) ENABLE_OVS=true; shift;;
        --storage-root)
            (($# >= 2)) || die "Missing value for $1"
            STORAGE_ROOTS+=("$2")
            shift 2;;
        --allow-destructive) ALLOW_DESTRUCTIVE=true; shift;;
        --bridge-allow-interface)
            (($# >= 2)) || die "Missing value for $1"
            [[ "$2" =~ ^[A-Za-z][A-Za-z0-9_-]{0,14}$ && "$2" != lo && -e "/sys/class/net/$2" ]] || die "Invalid bridge interface: $2"
            BRIDGE_ALLOWED+=("$2")
            shift 2;;
        --help|-h) usage; exit 0;;
        *) die "Unknown option: $1";;
    esac
done

[[ $EUID == 0 ]] || die "Run with sudo bash install.sh"
[[ -r /etc/os-release ]] || die "Cannot identify OS"
# shellcheck source=/dev/null
. /etc/os-release
[[ "${ID:-}" == ubuntu && "${VERSION_ID:-}" == 26.* ]] || die "Ubuntu 26.x is required; found ${PRETTY_NAME:-unknown}"
[[ $(uname -m) == x86_64 ]] || die "Current Agent domain XML requires an amd64/x86_64 host"
[[ -d /run/systemd/system ]] || die "A booted Ubuntu host with systemd is required (not a container/chroot)"
for install_root in "$APP_DIR" "$CONFIG_DIR" "$WEB_ROOT"; do
    [[ ! -L "$install_root" && $(realpath -m -- "$install_root") == "$install_root" ]] || die "Deployment roots and ancestors must not be symlinks: $install_root"
done
[[ "$PORT" =~ ^[0-9]{1,5}$ ]] && ((10#$PORT >= 1 && 10#$PORT <= 65535)) || die "Invalid web port"
for root in "${STORAGE_ROOTS[@]}"; do
    [[ "$root" =~ ^/[A-Za-z0-9_./-]+$ && "$root" != / && $(realpath -m -- "$root") == "$root" ]] || die "Invalid storage root: $root"
    case "$root" in
        /etc|/etc/*|/usr|/usr/*|/root|/root/*|/home|/home/*|/proc|/proc/*|/sys|/sys/*|/dev|/dev/*|/run|/run/*|/tmp|/tmp/*|/var/log|/var/log/*|/var/tmp|/var/tmp/*|/var/www|/var/www/*|/opt/cloudvirt|/opt/cloudvirt/*)
            die "System directory cannot be a storage root: $root";;
    esac
done
PORT=$((10#$PORT))
case "$PORT" in 5432|8000|9100) die "Web port conflicts with an internal service";; esac
command -v flock >/dev/null || die "flock is required (Ubuntu util-linux)"
exec 9>/run/lock/cloudvirt-install.lock
flock -n 9 || die "Another installer is running"
[[ $(df -Pk /opt | awk 'NR==2 {print $4}') -ge 8388608 ]] || die "At least 8 GiB free disk space is required"
[[ $(awk '/^MemTotal:/ {print $2}' /proc/meminfo) -ge 1572864 ]] || die "At least 1.5 GiB RAM is required (4 GiB recommended)"
grep -Eq '(vmx|svm)' /proc/cpuinfo || die "Hardware virtualization is unavailable; enable VT-x/AMD-V or nested virtualization first"
if [[ ! -c /dev/kvm ]]; then
    modprobe kvm
    if grep -q vmx /proc/cpuinfo; then modprobe kvm_intel; else modprobe kvm_amd; fi
fi
[[ -c /dev/kvm ]] || die "/dev/kvm is unavailable"

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
if [[ -z "$SOURCE_DIR" && -f "$SCRIPT_DIR/frontend/package-lock.json" && -f "$SCRIPT_DIR/apps/management/manage.py" ]]; then
    SOURCE_DIR=$SCRIPT_DIR
fi
if [[ -n "$SOURCE_DIR" ]]; then
    SOURCE_DIR=$(realpath -e -- "$SOURCE_DIR")
    [[ -f "$SOURCE_DIR/apps/management/manage.py" && -f "$SOURCE_DIR/services/virt-node-agent/go.mod" && -f "$SOURCE_DIR/frontend/package-lock.json" ]] || die "Incomplete source tree"
fi
if [[ -z "$DOMAIN" ]]; then
    DOMAIN=$(ip -4 route get 1.1.1.1 | awk '{for(i=1;i<=NF;i++)if($i=="src"){print $(i+1);exit}}')
fi
[[ "$DOMAIN" =~ ^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$ ]] || die "Specify --domain with a hostname or IPv4 address"

STEP=packages
INSTALL_STATE=/var/lib/cloudvirt-installer
[[ ! -L "$INSTALL_STATE" && $(realpath -m -- "$INSTALL_STATE") == "$INSTALL_STATE" ]] || die "Invalid installer state directory"
install -d -o root -g root -m 0700 "$INSTALL_STATE"
INSTALL_TRACKING=true
if [[ ! -e "$INSTALL_STATE/baseline-packages.txt" ]]; then
    [[ ! -e "$CONFIG_DIR/install-secrets.env" ]] || touch "$INSTALL_STATE/provenance-incomplete"
    dpkg-query -W -f='${binary:Package}\t${Status}\n' | awk -F '\t' '$2 == "install ok installed" {print $1}' | sort -u > "$INSTALL_STATE/baseline-packages.txt"
fi
dpkg-query -W -f='${binary:Package}\t${Status}\n' | awk -F '\t' '$2 == "install ok installed" {print $1}' | sort -u > "$INSTALL_STATE/before-packages.txt"
log "Installing Ubuntu packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y software-properties-common ca-certificates curl git rsync xz-utils openssl
add-apt-repository -y universe
apt-get update
apt-get install -y python3 python3-venv python3-dev build-essential libpq-dev \
    postgresql postgresql-client nginx golang-go qemu-system-x86 qemu-utils \
    libvirt-daemon-system libvirt-clients libvirt-daemon-config-network acl genisoimage ovmf swtpm iproute2
[[ -x /usr/bin/qemu-system-x86_64 ]] || die "qemu-system-x86 did not provide /usr/bin/qemu-system-x86_64"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,14) else 1)' || die "Python >=3.14 is required by the pinned Django requirements"
TMP_DIR=$(mktemp -d /var/tmp/cloudvirt-install.XXXXXX)

STEP=source
if [[ -z "$SOURCE_DIR" ]]; then
    log "Cloning $REPO_URL / $REPO_REF"
    git clone --depth 1 --single-branch --branch "$REPO_REF" -- "$REPO_URL" "$TMP_DIR/source"
    SOURCE_DIR=$TMP_DIR/source
fi
if [[ "$ENABLE_OVS" == true && ! -f "$SOURCE_DIR/scripts/install_ovs.sh" ]]; then
    die "OVS helper is not present in the selected source; use the complete deployment package"
fi
if [[ -z "$OFFLINE_DIR" && -f "$SOURCE_DIR/offline/linux-amd64/manifest.sha256" ]]; then
    OFFLINE_DIR="$SOURCE_DIR/offline/linux-amd64"
fi
if [[ -n "$OFFLINE_DIR" ]]; then
    STEP=offline-packages
    OFFLINE_DIR=$(realpath -e -- "$OFFLINE_DIR")
    [[ -d "$OFFLINE_DIR/wheels" && -f "$OFFLINE_DIR/manifest.sha256" &&
       -f "$OFFLINE_DIR/source.sha256" && -f "$OFFLINE_DIR/npm-cache.tar.gz" &&
       -f "$OFFLINE_DIR/go-vendor.tar.gz" ]] || die "Incomplete offline package directory: $OFFLINE_DIR"
    log "Verifying local package checksums and source dependency locks"
    (cd "$OFFLINE_DIR"; sha256sum --status -c manifest.sha256) || die "Offline package checksum mismatch"
    python3 - "$SOURCE_DIR" "$OFFLINE_DIR/source.sha256" <<'PY' || die "Offline packages do not match source dependency locks"
import hashlib
import pathlib
import sys

source = pathlib.Path(sys.argv[1])
for entry in pathlib.Path(sys.argv[2]).read_text().splitlines():
    expected, name = entry.split(maxsplit=1)
    path = source / name.strip().lstrip('*')
    # Source archives prepared on Windows may use CRLF for text lock files.
    actual = hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
    if actual != expected:
        raise SystemExit(f'Lock file mismatch: {name}')
PY
fi
if [[ -e "$APP_DIR/apps/management/manage.py" && "$SOURCE_DIR" != "$APP_DIR" ]]; then
    install -d -m 0700 /var/backups/cloudvirt
    log "Backing up existing application files"
    tar --exclude=.venv --exclude=node_modules --exclude=.git --exclude=frontend/dist \
        -czf "/var/backups/cloudvirt/source-$(date -u +%Y%m%dT%H%M%SZ).tar.gz" -C "$APP_DIR" .
fi
if [[ -f "$CONFIG_DIR/install-secrets.env" ]]; then
    # Retire optional services from older releases before updating the schema.
    systemctl disable --now cloudvirt-media.service cloudvirt-workbench-broker.service \
        cloudvirt-reconcile_broadcasts.timer cloudvirt-reconcile_workspaces.timer 2>/dev/null || true
    while read -r legacy_unit _; do
        [[ "$legacy_unit" =~ ^cloudvirt-workbench-[0-9a-f-]{36}\.service$ ]] || continue
        systemctl stop "$legacy_unit"
    done < <(systemctl list-units --all --plain --no-legend 'cloudvirt-workbench-*.service')
    log "Stopping application jobs while deploying (running guests are not stopped)"
    systemctl stop cloudvirt-collect_node_status.timer cloudvirt-reconcile.timer cloudvirt-cleanup_console_sessions.timer cloudvirt-cleanup_account_batches.timer 2>/dev/null || true
    systemctl stop cloudvirt-collect_node_status.service cloudvirt-reconcile.service cloudvirt-cleanup_console_sessions.service cloudvirt-cleanup_account_batches.service 2>/dev/null || true
    systemctl stop cloudvirt-worker cloudvirt-management cloudvirt-agent 2>/dev/null || true
fi
install -d -m 0755 "$APP_DIR" "$WEB_ROOT"
if [[ "$SOURCE_DIR" != "$APP_DIR" ]]; then
    rsync -a --exclude=.git --exclude=.venv --exclude=node_modules --exclude=dist \
        --exclude=outputs --exclude=work --include=.env.example --exclude='.env*' \
        "$SOURCE_DIR/" "$APP_DIR/"
fi
# ZIP files extracted from Windows may contain CRLF in shell scripts.
find "$APP_DIR/scripts" -maxdepth 1 -type f -name '*.sh' -exec sed -i 's/\r$//' {} +
chmod 0755 "$APP_DIR" "$APP_DIR/scripts"

STEP=accounts
if ! getent passwd cloudvirt >/dev/null; then
    useradd --system --home-dir /var/lib/cloudvirt --create-home --shell /usr/sbin/nologin cloudvirt
    printf 'cloudvirt\n' >> "$INSTALL_STATE/created-users.txt"
fi
if ! getent passwd cloudvirt-agent >/dev/null; then
    useradd --system --home-dir /var/lib/cloudvirt-agent --create-home --shell /usr/sbin/nologin cloudvirt-agent
    printf 'cloudvirt-agent\n' >> "$INSTALL_STATE/created-users.txt"
fi
usermod -a -G libvirt,kvm cloudvirt-agent
getent passwd libvirt-qemu >/dev/null && usermod -a -G kvm libvirt-qemu
install -d -o cloudvirt -g cloudvirt -m 0750 /var/log/cloudvirt
for root in "$DATA_DIR" "$DATA_DIR/images" "$DATA_DIR/disks" "${STORAGE_ROOTS[@]}"; do
    [[ -e "$root" ]] || printf '%s\n' "$root" >> "$INSTALL_STATE/created-storage-directories.txt"
done
install -d -m 0755 /var/lib/libvirt/images "$DATA_DIR"
install -d -o cloudvirt-agent -g kvm -m 2770 "$DATA_DIR/images" "$DATA_DIR/disks"
for root in "${STORAGE_ROOTS[@]}"; do
    install -d -o cloudvirt-agent -g kvm -m 2770 "$root"
done
# The management account can read application code, but cannot modify it.
chown -R root:root "$APP_DIR"
find "$APP_DIR" -type d -exec chmod a+rx {} +
find "$APP_DIR" -type f ! -name '.env' ! -name '.env.*' ! -name '*.pem' ! -name '*.key' -exec chmod a+r {} +
find "$APP_DIR" -type f \( -name '.env' -o -name '.env.*' \) ! -name '.env.example' -exec chmod 0600 {} +
install -d -o root -g cloudvirt -m 0750 "$CONFIG_DIR"

STEP=secrets
if [[ -e "$CONFIG_DIR/install-secrets.env" ]]; then
    [[ -f "$CONFIG_DIR/install-secrets.env" && ! -L "$CONFIG_DIR/install-secrets.env" ]] || die "Invalid secrets file"
    [[ $(stat -c %u "$CONFIG_DIR/install-secrets.env") == 0 ]] || die "Secrets file must be root-owned"
    [[ $(stat -c %a "$CONFIG_DIR/install-secrets.env") == 600 ]] || die "Secrets file must have mode 600"
    # shellcheck source=/dev/null
    . "$CONFIG_DIR/install-secrets.env"
else
    [[ ! -e "$CONFIG_DIR/management.env" ]] || die "Existing deployment has no installer secrets; refusing to replace its credentials"
    systemctl enable --now postgresql
    if [[ $(runuser -u postgres -- psql -X -h /var/run/postgresql -U postgres -p 5432 -At -d postgres -c "SELECT EXISTS(SELECT FROM pg_roles WHERE rolname='cloudvirt') OR EXISTS(SELECT FROM pg_database WHERE datname='cloudvirt')") == t ]]; then
        die "An unmanaged cloudvirt database/role already exists; refusing to replace its credentials"
    fi
    DB_PASSWORD=$(openssl rand -hex 32)
    DJANGO_KEY=$(openssl rand -hex 48)
    AGENT_TOKEN=$(openssl rand -hex 48)
    printf 'DB_PASSWORD=%s\nDJANGO_KEY=%s\nAGENT_TOKEN=%s\n' \
        "$DB_PASSWORD" "$DJANGO_KEY" "$AGENT_TOKEN" > "$CONFIG_DIR/install-secrets.env"
    chmod 0600 "$CONFIG_DIR/install-secrets.env"
fi
[[ "$DB_PASSWORD" =~ ^[a-f0-9]{64}$ && "$DJANGO_KEY" =~ ^[a-f0-9]{96}$ && "$AGENT_TOKEN" =~ ^[a-f0-9]{96}$ ]] || die "Unexpected installer secret format"

STEP=database
systemctl enable --now postgresql
if [[ $(runuser -u postgres -- psql -X -h /var/run/postgresql -U postgres -p 5432 -At -d postgres -c "SELECT EXISTS(SELECT FROM pg_database WHERE datname='cloudvirt')") == t ]]; then
    install -d -m 0700 /var/backups/cloudvirt
    runuser -u postgres -- pg_dump -h /var/run/postgresql -U postgres -p 5432 -Fc cloudvirt > "/var/backups/cloudvirt/database-$(date -u +%Y%m%dT%H%M%SZ).dump"
fi
export CLOUDVIRT_DB_PASSWORD="$DB_PASSWORD"
runuser -u postgres --preserve-environment -- psql -X -h /var/run/postgresql -U postgres -p 5432 -v ON_ERROR_STOP=1 -d postgres <<'SQL'
\getenv dbpass CLOUDVIRT_DB_PASSWORD
SELECT format('CREATE ROLE cloudvirt LOGIN PASSWORD %L', :'dbpass')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='cloudvirt') \gexec
SELECT format('ALTER ROLE cloudvirt PASSWORD %L', :'dbpass') \gexec
SELECT 'CREATE DATABASE cloudvirt OWNER cloudvirt'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='cloudvirt') \gexec
SQL
unset CLOUDVIRT_DB_PASSWORD

STEP=runtime
log "Installing private Node.js 24 runtime with official SHA-256 verification"
NODE_HOME="$APP_DIR/runtime/node"
if [[ ! -x "$NODE_HOME/bin/node" ]] || [[ $("$NODE_HOME/bin/node" -p 'process.versions.node.split(".")[0]') != 24 ]]; then
    if [[ -n "$OFFLINE_DIR" ]]; then
        node_archives=("$OFFLINE_DIR"/node-v24.*-linux-x64.tar.xz)
        [[ ${#node_archives[@]} == 1 && -f "${node_archives[0]}" ]] || die "Offline bundle must contain one Node.js 24 linux-x64 archive"
        NODE_ARCHIVE=${node_archives[0]}
        (cd "$OFFLINE_DIR"; sha256sum --status -c node-official.sha256) || die "Node.js archive differs from its official SHA-256"
    else
        curl --proto '=https' --tlsv1.2 -fSL --retry 3 --connect-timeout 20 \
            https://nodejs.org/dist/latest-v24.x/SHASUMS256.txt -o "$TMP_DIR/SHASUMS256.txt"
        NODE_FILE=$(awk '$2 ~ /^node-v24\.[0-9]+\.[0-9]+-linux-x64.tar.xz$/ {print $2; exit}' "$TMP_DIR/SHASUMS256.txt")
        [[ "$NODE_FILE" =~ ^node-v24\.[0-9]+\.[0-9]+-linux-x64.tar.xz$ ]] || die "Cannot resolve official Node.js 24 download"
        curl --proto '=https' --tlsv1.2 -fSL --retry 3 --connect-timeout 20 \
            "https://nodejs.org/dist/latest-v24.x/$NODE_FILE" -o "$TMP_DIR/$NODE_FILE"
        (cd "$TMP_DIR"; awk -v file="$NODE_FILE" '$2 == file' SHASUMS256.txt | sha256sum -c -)
        NODE_ARCHIVE="$TMP_DIR/$NODE_FILE"
    fi
    install -d -m 0755 "$NODE_HOME"
    tar -xJf "$NODE_ARCHIVE" --strip-components=1 -C "$NODE_HOME"
fi
export PATH="$NODE_HOME/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export CLOUDVIRT_NPM_REGISTRY="${CLOUDVIRT_NPM_REGISTRY:-https://registry.npmjs.org}"
# Preserve lockfile integrity hashes while avoiding a hard dependency on the original mirror.
python3 - "$APP_DIR/frontend/package-lock.json" <<'PY'
import json, os, pathlib
path = pathlib.Path(__import__('sys').argv[1])
registry = os.environ['CLOUDVIRT_NPM_REGISTRY'].rstrip('/')
if not registry.startswith('https://'):
    raise SystemExit('CLOUDVIRT_NPM_REGISTRY must use HTTPS')
lock = json.loads(path.read_text())
for package in lock.get('packages', {}).values():
    url = package.get('resolved', '')
    for original in ('https://registry.npmmirror.com', 'https://registry.npmjs.org'):
        if url.startswith(original + '/'):
            package['resolved'] = registry + url[len(original):]
            break
path.write_text(json.dumps(lock, indent=2) + '\n')
PY
log "Building Python backend, React frontend and Go Agent"
python3 -m venv "$APP_DIR/.venv"
if [[ -n "$OFFLINE_DIR" ]]; then
    "$APP_DIR/.venv/bin/python" -m pip install --no-index --find-links "$OFFLINE_DIR/wheels" --upgrade pip
    "$APP_DIR/.venv/bin/python" -m pip install --no-index --find-links "$OFFLINE_DIR/wheels" -r "$APP_DIR/apps/management/requirements/prod.txt"
    install -d -m 0700 "$TMP_DIR/npm-cache"
    tar -xzf "$OFFLINE_DIR/npm-cache.tar.gz" -C "$TMP_DIR/npm-cache"
    (cd "$APP_DIR/frontend"; npm ci --offline --cache "$TMP_DIR/npm-cache" --registry="$CLOUDVIRT_NPM_REGISTRY" --no-audit --no-fund; npm run build)
else
    "$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
    "$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/apps/management/requirements/prod.txt"
    (cd "$APP_DIR/frontend"; npm ci --registry="$CLOUDVIRT_NPM_REGISTRY"; npm run build)
fi
install -d -m 0755 "$APP_DIR/services/virt-node-agent/bin"
if [[ -n "$OFFLINE_DIR" ]]; then
    tar -xzf "$OFFLINE_DIR/go-vendor.tar.gz" -C "$APP_DIR/services/virt-node-agent"
    (cd "$APP_DIR/services/virt-node-agent"; CGO_ENABLED=0 GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off GOFLAGS=-mod=vendor go build -trimpath -o bin/virt-node-agent ./cmd/virt-node-agent)
else
    (cd "$APP_DIR/services/virt-node-agent"; CGO_ENABLED=0 GOTOOLCHAIN=auto GOFLAGS=-mod=mod go build -trimpath -o bin/virt-node-agent ./cmd/virt-node-agent)
fi
rsync -a --chmod=D755,F644 "$APP_DIR/frontend/dist/" "$WEB_ROOT/"
chmod -R a+rX "$APP_DIR/.venv"
chmod 0755 "$APP_DIR/services/virt-node-agent/bin/virt-node-agent"

STEP=config
SCHEME=https
[[ "$HTTPS" == true ]] || SCHEME=http
ORIGIN="$SCHEME://$DOMAIN"
if [[ "$HTTPS:$PORT" != true:443 && "$HTTPS:$PORT" != false:80 ]]; then ORIGIN="$ORIGIN:$PORT"; fi
if [[ ! -e "$CONFIG_DIR/management.env" ]]; then
    cat > "$CONFIG_DIR/management.env" <<ENV
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=$DJANGO_KEY
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,$DOMAIN
DJANGO_CSRF_TRUSTED_ORIGINS=$ORIGIN
DJANGO_TRUST_PROXY=true
DJANGO_SESSION_COOKIE_SECURE=$HTTPS
DJANGO_CSRF_COOKIE_SECURE=$HTTPS
DATABASE_URL=postgresql://cloudvirt:$DB_PASSWORD@127.0.0.1:5432/cloudvirt
AGENT_SHARED_TOKEN=$AGENT_TOKEN
AGENT_REQUEST_TIMEOUT_SECONDS=30
USER_QUOTA_INSTANCES=10
USER_QUOTA_VCPU=32
USER_QUOTA_MEMORY_MIB=65536
USER_QUOTA_DISK_GIB=1024
ENV
else
    log "Keeping existing database and application secrets"
fi
python3 - "$CONFIG_DIR/management.env" "$DOMAIN" "$ORIGIN" "$HTTPS" <<'PY'
import os, pathlib, sys, tempfile
path = pathlib.Path(sys.argv[1])
domain, origin, secure = sys.argv[2:]
lines = path.read_text().splitlines()
current = dict(line.split('=', 1) for line in lines if '=' in line and not line.lstrip().startswith('#'))
updates = {'DJANGO_TRUST_PROXY': 'true', 'DJANGO_DEBUG': 'false',
           'DJANGO_SESSION_COOKIE_SECURE': secure, 'DJANGO_CSRF_COOKIE_SECURE': secure}
for key, value in [('DJANGO_ALLOWED_HOSTS', domain), ('DJANGO_CSRF_TRUSTED_ORIGINS', origin)]:
    values = [part for part in current.get(key, '').split(',') if part]
    if value not in values:
        values.append(value)
    updates[key] = ','.join(values)
output = []
for line in lines:
    key = line.partition('=')[0]
    if key in updates:
        output.append(f'{key}={updates.pop(key)}')
    else:
        output.append(line)
output.extend(f'{key}={value}' for key, value in updates.items())
metadata = path.stat()
with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False) as temporary:
    temporary.write('\n'.join(output) + '\n')
os.chmod(temporary.name, metadata.st_mode & 0o777)
os.chown(temporary.name, metadata.st_uid, metadata.st_gid)
os.replace(temporary.name, path)
PY
if [[ ! -e "$CONFIG_DIR/agent.env" ]]; then
    cat > "$CONFIG_DIR/agent.env" <<ENV
CLOUDVIRT_AGENT_LISTEN=127.0.0.1:9100
CLOUDVIRT_AGENT_TOKEN=$AGENT_TOKEN
CLOUDVIRT_IMAGE_DIR=$DATA_DIR/images
CLOUDVIRT_DISK_DIR=$DATA_DIR/disks
CLOUDVIRT_MAX_REQUEST_SECONDS=600
CLOUDVIRT_ALLOW_DESTRUCTIVE=$ALLOW_DESTRUCTIVE
CLOUDVIRT_DHCP_LEASE_FILE=/var/lib/misc/dnsmasq.ovs.leases
ENV
elif [[ "$ALLOW_DESTRUCTIVE" == true ]]; then
    sed -i 's/^CLOUDVIRT_ALLOW_DESTRUCTIVE=.*/CLOUDVIRT_ALLOW_DESTRUCTIVE=true/' "$CONFIG_DIR/agent.env"
fi
ROOTS_CSV=$(sed -n 's/^CLOUDVIRT_STORAGE_ROOTS=//p' "$CONFIG_DIR/agent.env" | tail -1)
IFS=, read -r -a EXISTING_ROOTS <<< "$ROOTS_CSV"
for root in "${EXISTING_ROOTS[@]}"; do
    [[ "$root" =~ ^/[A-Za-z0-9_./-]+$ && $(realpath -m -- "$root") == "$root" ]] || die "Invalid existing storage root: $root"
    case "$root" in
        /etc|/etc/*|/usr|/usr/*|/root|/root/*|/home|/home/*|/proc|/proc/*|/sys|/sys/*|/dev|/dev/*|/run|/run/*|/tmp|/tmp/*|/var/log|/var/log/*|/var/tmp|/var/tmp/*|/var/www|/var/www/*|/opt/cloudvirt|/opt/cloudvirt/*)
            die "System directory cannot be a storage root: $root";;
    esac
done
for root in "${STORAGE_ROOTS[@]}"; do
    [[ ",$ROOTS_CSV," == *",$root,"* ]] || ROOTS_CSV="${ROOTS_CSV:+$ROOTS_CSV,}$root"
done
if grep -q '^CLOUDVIRT_STORAGE_ROOTS=' "$CONFIG_DIR/agent.env"; then
    sed -i "s|^CLOUDVIRT_STORAGE_ROOTS=.*|CLOUDVIRT_STORAGE_ROOTS=$ROOTS_CSV|" "$CONFIG_DIR/agent.env"
else
    printf 'CLOUDVIRT_STORAGE_ROOTS=%s\n' "$ROOTS_CSV" >> "$CONFIG_DIR/agent.env"
fi
chown root:cloudvirt "$CONFIG_DIR/management.env"
chmod 0640 "$CONFIG_DIR/management.env"
chown root:cloudvirt-agent "$CONFIG_DIR/agent.env"
chmod 0640 "$CONFIG_DIR/agent.env"
# The Agent needs directory traversal only; management credentials remain unreadable to it.
setfacl -m u:cloudvirt-agent:--x "$CONFIG_DIR"

manage() (
    set -a
    # shellcheck source=/dev/null
    . "$CONFIG_DIR/management.env"
    set +a
    cd "$APP_DIR/apps/management"
    runuser -u cloudvirt -- "$APP_DIR/.venv/bin/python" manage.py "$@"
)
STEP=migrations
manage check
manage migrate --noinput
manage sync_roles
if manage shell --verbosity 0 -c 'import sys; from django.contrib.auth import get_user_model; sys.exit(0 if get_user_model().objects.filter(is_superuser=True).exists() else 3)'; then
    log "Existing administrator preserved"
else
    result=$?
    [[ "$result" == 3 ]] || die "Could not inspect administrator state"
    export CLOUDVIRT_BOOTSTRAP_ADMIN=true CLOUDVIRT_BOOTSTRAP_PASSWORD
    CLOUDVIRT_BOOTSTRAP_PASSWORD=$(openssl rand -hex 16)
    manage bootstrap_admin --username admin > "$CONFIG_DIR/initial-admin.txt"
    chmod 0600 "$CONFIG_DIR/initial-admin.txt"
    unset CLOUDVIRT_BOOTSTRAP_PASSWORD CLOUDVIRT_BOOTSTRAP_ADMIN
fi

STEP=libvirt
if systemctl list-unit-files libvirtd.service --no-legend | grep -q '^libvirtd.service'; then
    systemctl enable --now libvirtd.service
else
    systemctl enable --now virtqemud.socket virtnetworkd.socket virtstoraged.socket
fi
virsh -c qemu:///system list --all >/dev/null
if ! virsh -c qemu:///system net-info default >/dev/null 2>&1; then
    [[ -r /usr/share/libvirt/networks/default.xml ]] || die "libvirt default network XML is unavailable"
    virsh -c qemu:///system net-define /usr/share/libvirt/networks/default.xml
    touch "$INSTALL_STATE/created-default-network"
fi
if ! virsh -c qemu:///system net-list --name | grep -qx default; then
    virsh -c qemu:///system net-start default
fi
virsh -c qemu:///system net-autostart default
runuser -u cloudvirt-agent -- virsh -c qemu:///system list --all >/dev/null

STEP=services
install -o root -g root -m 0755 "$APP_DIR/scripts/cloudvirtctl.py" /usr/local/sbin/cloudvirtctl
if ((${#BRIDGE_ALLOWED[@]})); then
    install -d -m 0750 "$CONFIG_DIR"
    touch "$CONFIG_DIR/network.env"
    for nic in "${BRIDGE_ALLOWED[@]}"; do
        printf 'Bridge management-filter exemption: %s (existing addresses/routes are not migrated)\n' "$nic"
    done
    allowed_csv=$(IFS=,; printf '%s' "${BRIDGE_ALLOWED[*]}")
    existing_allowed=$(sed -n 's/^CLOUDVIRT_BRIDGE_ALLOWED_INTERFACES=//p' "$CONFIG_DIR/network.env" | tail -1)
    sed -i '/^CLOUDVIRT_BRIDGE_ALLOWED_INTERFACES=/d' "$CONFIG_DIR/network.env"
    printf 'CLOUDVIRT_BRIDGE_ALLOWED_INTERFACES=%s\n' "${existing_allowed:+$existing_allowed,}$allowed_csv" >> "$CONFIG_DIR/network.env"
    chown root:cloudvirt-agent "$CONFIG_DIR/network.env"
    chmod 0640 "$CONFIG_DIR/network.env"
fi
if ! grep -q '^CLOUDVIRT_PROTECTED_INTERFACES=' "$CONFIG_DIR/network.env" 2>/dev/null; then
    python3 - "$CONFIG_DIR/network.env" <<'PY'
import ipaddress
import json
import pathlib
import subprocess
import sys

links = json.loads(subprocess.check_output(['ip', '-j', 'address', 'show']))
protected = sorted({link['ifname'] for link in links if link['ifname'] != 'lo'
                    and any(not ipaddress.ip_address(address['local']).is_link_local
                            for address in link.get('addr_info', []))})
with pathlib.Path(sys.argv[1]).open('a', encoding='utf-8') as output:
    output.write('CLOUDVIRT_PROTECTED_INTERFACES=' + ','.join(protected) + '\n')
PY
    chown root:cloudvirt-agent "$CONFIG_DIR/network.env"
    chmod 0640 "$CONFIG_DIR/network.env"
fi
for service in management worker agent network; do
    install -m 0644 "$APP_DIR/deploy/systemd/cloudvirt-$service.service" "/etc/systemd/system/cloudvirt-$service.service"
done
systemctl daemon-reload
if grep -qx 'CLOUDVIRT_NETWORK_BRIDGE_ENABLED=false' "$CONFIG_DIR/network.env"; then
    systemctl disable --now cloudvirt-network.service
else
    systemctl enable cloudvirt-network.service
    systemctl restart cloudvirt-network.service
fi
install -d -m 0755 /etc/systemd/system/cloudvirt-agent.service.d
cat > /etc/systemd/system/cloudvirt-agent.service.d/install.conf <<ENV
[Service]
User=cloudvirt-agent
Group=cloudvirt-agent
SupplementaryGroups=libvirt kvm
UMask=0007
ReadWritePaths=
ReadWritePaths=$DATA_DIR ${ROOTS_CSV//,/ } /var/log/cloudvirt
ENV
for job in collect_node_status reconcile cleanup_console_sessions cleanup_account_batches; do
    interval=30
    [[ "$job" != reconcile ]] || interval=60
    cat > "/etc/systemd/system/cloudvirt-$job.service" <<ENV
[Unit]
Description=CloudVirt $job
After=cloudvirt-management.service cloudvirt-agent.service
[Service]
Type=oneshot
User=cloudvirt
Group=cloudvirt
WorkingDirectory=$APP_DIR/apps/management
EnvironmentFile=$CONFIG_DIR/management.env
ExecStart=$APP_DIR/.venv/bin/python manage.py $job
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ENV
    cat > "/etc/systemd/system/cloudvirt-$job.timer" <<ENV
[Unit]
Description=CloudVirt $job schedule
[Timer]
OnBootSec=45s
OnUnitInactiveSec=${interval}s
Unit=cloudvirt-$job.service
[Install]
WantedBy=timers.target
ENV
done
systemctl daemon-reload
systemctl enable cloudvirt-management cloudvirt-agent cloudvirt-worker
systemctl restart cloudvirt-agent cloudvirt-management cloudvirt-worker

STEP=nginx
install -d -m 0755 /etc/nginx/snippets
install -m 0644 "$APP_DIR/deploy/nginx/security-headers.conf" /etc/nginx/snippets/cloudvirt-security-headers.conf
install -m 0644 "$APP_DIR/deploy/nginx/hsts.conf" /etc/nginx/snippets/cloudvirt-hsts.conf
CLOUDVIRT_CONSOLE_GATEWAY_KEY=$(manage console_gateway_key)
export CLOUDVIRT_CONSOLE_GATEWAY_KEY
"$APP_DIR/.venv/bin/python" - "$APP_DIR/deploy/nginx/console-gateway.conf" <<'PY'
import os
import sys
from pathlib import Path
target = Path('/etc/nginx/snippets/cloudvirt-console.conf')
target.write_text(Path(sys.argv[1]).read_text().replace('__CONSOLE_GATEWAY_KEY__', os.environ['CLOUDVIRT_CONSOLE_GATEWAY_KEY']))
target.chmod(0o640)
PY
unset CLOUDVIRT_CONSOLE_GATEWAY_KEY
TLS_LINES=""
if [[ "$HTTPS" == true ]]; then
    install -d -m 0700 "$CONFIG_DIR/tls"
    if [[ ! -f "$CONFIG_DIR/tls/server.key" || ! -f "$CONFIG_DIR/tls/server.crt" ]]; then
        SAN="DNS:localhost,IP:127.0.0.1"
        if [[ "$DOMAIN" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then SAN="$SAN,IP:$DOMAIN"; else SAN="$SAN,DNS:$DOMAIN"; fi
        openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 365 \
            -subj "/CN=$DOMAIN" -addext "subjectAltName=$SAN" \
            -keyout "$CONFIG_DIR/tls/server.key" -out "$CONFIG_DIR/tls/server.crt" 2>/dev/null
        chmod 0600 "$CONFIG_DIR/tls/server.key"
    fi
    TLS_LINES="ssl_certificate $CONFIG_DIR/tls/server.crt;
    ssl_certificate_key $CONFIG_DIR/tls/server.key;
    ssl_protocols TLSv1.2 TLSv1.3;"
fi
LISTEN="$PORT"
[[ "$HTTPS" != true ]] || LISTEN="$PORT ssl"
cat > /etc/nginx/sites-available/cloudvirt <<NGINX
server {
    listen $LISTEN;
    server_name $DOMAIN localhost 127.0.0.1;
    $TLS_LINES
    root $WEB_ROOT;
    index index.html;
    include /etc/nginx/snippets/cloudvirt-security-headers.conf;
    $(if [[ "$HTTPS" == true ]]; then printf '%s' 'include /etc/nginx/snippets/cloudvirt-hsts.conf;'; fi)
    client_max_body_size 64m;
    location /assets/ { expires 30d; try_files \$uri =404; }
    location = /index.html { expires epoch; }
    location / { try_files \$uri \$uri/ /index.html; }
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$remote_addr;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 5s;
        proxy_send_timeout 180s;
        proxy_read_timeout 180s;
    }
    include /etc/nginx/snippets/cloudvirt-console.conf;
}
NGINX
if [[ "$HTTPS" == true && "$PORT" != 80 ]]; then
    REDIRECT_PORT=""
    [[ "$PORT" == 443 ]] || REDIRECT_PORT=":$PORT"
    cat >> /etc/nginx/sites-available/cloudvirt <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;
    return 301 https://$DOMAIN$REDIRECT_PORT\$request_uri;
}
NGINX
fi
ln -sfn /etc/nginx/sites-available/cloudvirt /etc/nginx/sites-enabled/cloudvirt
# Leave the distribution's default site and any other administrator sites intact.
# CloudVirt's explicit server_name routes its own host without taking over port 80.
nginx -t
systemctl enable --now nginx
systemctl reload nginx
if command -v ufw >/dev/null && ufw status | grep -q '^Status: active'; then
    ufw allow "$PORT/tcp" comment 'CloudVirt console'
fi

STEP=health
wait_url() {
    local url=$1 attempts=0
    shift
    until curl -fsS --connect-timeout 3 --max-time 5 "$@" "$url" >/dev/null; do
        attempts=$((attempts+1))
        ((attempts < 30)) || die "Health check timed out: $url"
        sleep 2
    done
}
wait_url http://127.0.0.1:9100/health
wait_url http://127.0.0.1:8000/api/v1/health
[[ -s "$WEB_ROOT/index.html" ]] || die "Frontend index.html was not deployed"
if [[ "$HTTPS" == true ]]; then
    wait_url "$ORIGIN/api/v1/health" --noproxy '*' --resolve "$DOMAIN:$PORT:127.0.0.1" --cacert "$CONFIG_DIR/tls/server.crt"
    wait_url "$ORIGIN/index.html" --noproxy '*' --resolve "$DOMAIN:$PORT:127.0.0.1" --cacert "$CONFIG_DIR/tls/server.crt"
    if [[ "$PORT" != 80 ]]; then
        redirect_status=$(curl -sS -o /dev/null -w '%{http_code}' --noproxy '*' \
            --resolve "$DOMAIN:80:127.0.0.1" "http://$DOMAIN/")
        [[ "$redirect_status" == 301 ]] || die "HTTP-to-HTTPS redirect is unavailable for $DOMAIN (status $redirect_status)"
    fi
else
    wait_url "$ORIGIN/api/v1/health" --noproxy '*' --resolve "$DOMAIN:$PORT:127.0.0.1"
    wait_url "$ORIGIN/index.html" --noproxy '*' --resolve "$DOMAIN:$PORT:127.0.0.1"
fi
export CLOUDVIRT_DEFAULT_NETWORK_XML
CLOUDVIRT_DEFAULT_NETWORK_XML=$(virsh -c qemu:///system net-dumpxml default)
manage shell --verbosity 0 <<'PY'
import ipaddress
import os
import xml.etree.ElementTree as ET
from apps.nodes.models import Node
from apps.networks.models import Network
from apps.nodes.services import refresh_node
node, _ = Node.objects.get_or_create(name='local', defaults={'endpoint': 'http://127.0.0.1:9100'})
if node.endpoint != 'http://127.0.0.1:9100' or node.is_deleted:
    raise RuntimeError('Existing local node record conflicts with this installer')
refresh_node(node)
if node.status not in {'ONLINE', 'DEGRADED'}:
    raise RuntimeError('Local Agent resource collection failed')
root = ET.fromstring(os.environ['CLOUDVIRT_DEFAULT_NETWORK_XML'])
ip = root.find('ip')
defaults = {'type': 'LIBVIRT_NETWORK', 'is_default': True}
if ip is not None and ip.get('address'):
    defaults['gateway'] = ip.get('address')
    defaults['subnet'] = str(ipaddress.ip_network(
        f"{ip.get('address')}/{ip.get('netmask') or ip.get('prefix') or '24'}", strict=False))
    pool = ip.find('dhcp/range')
    if pool is not None:
        defaults.update(dhcp_enabled=True, dhcp_start=pool.get('start'), dhcp_end=pool.get('end'))
Network.objects.get_or_create(name='default', defaults=defaults)
PY
unset CLOUDVIRT_DEFAULT_NETWORK_XML

if [[ "$ENABLE_OVS" == true ]]; then
    STEP=ovs
    # Optional network provisioning is isolated in an audited helper.
    bash "$APP_DIR/scripts/install_ovs.sh" "$APP_DIR"
fi
systemctl enable --now cloudvirt-collect_node_status.timer cloudvirt-reconcile.timer cloudvirt-cleanup_console_sessions.timer
systemctl enable --now cloudvirt-cleanup_account_batches.timer
for service in cloudvirt-agent cloudvirt-management cloudvirt-worker cloudvirt-network nginx postgresql; do
    if [[ "$service" == cloudvirt-network ]] && grep -qx 'CLOUDVIRT_NETWORK_BRIDGE_ENABLED=false' "$CONFIG_DIR/network.env"; then
        continue
    fi
    systemctl is-active --quiet "$service" || die "Service is not active: $service"
done
log "Deployment completed"
dpkg-query -W -f='${binary:Package}\t${Status}\n' | awk -F '\t' '$2 == "install ok installed" {print $1}' | sort -u > "$INSTALL_STATE/current-packages.txt"
comm -13 "$INSTALL_STATE/before-packages.txt" "$INSTALL_STATE/current-packages.txt" > "$INSTALL_STATE/new-packages.txt"
if [[ -f "$INSTALL_STATE/added-packages.txt" ]]; then
    cat "$INSTALL_STATE/new-packages.txt" "$INSTALL_STATE/added-packages.txt" | sort -u > "$INSTALL_STATE/added-packages.next"
else
    cp "$INSTALL_STATE/new-packages.txt" "$INSTALL_STATE/added-packages.next"
fi
mv "$INSTALL_STATE/added-packages.next" "$INSTALL_STATE/added-packages.txt"
printf 'Console: %s\n' "$ORIGIN"
if [[ -f "$CONFIG_DIR/initial-admin.txt" ]]; then
    printf 'Initial administrator credentials: sudo cat %s/initial-admin.txt\n' "$CONFIG_DIR"
else
    printf 'Existing administrator account retained; no new password was generated.\n'
fi
printf 'Images: %s/images\nDisks: %s/disks\n' "$DATA_DIR" "$DATA_DIR"
printf 'Self-signed HTTPS: %s (replace the certificate for public deployment).\n' "$HTTPS"
printf 'Agent destructive operations: check %s/agent.env\n' "$CONFIG_DIR"
printf 'No guest OS image is fabricated or downloaded; import an actual image before creating a VM.\n'
