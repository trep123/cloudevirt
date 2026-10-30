#!/usr/bin/env bash
# CloudVirt control-plane uninstaller. Default: plan only, never remove guest data.
set -Eeuo pipefail
umask 077
APPLY=false
STEP=preflight
APP_DIR=/opt/cloudvirt
WEB_ROOT=/var/www/cloudvirt
BACKUP=""

usage() {
    cat <<'HELP'
CloudVirt control-plane uninstall (Ubuntu / systemd)
  sudo bash uninstall.sh              Show the plan only (default).
  sudo bash uninstall.sh --dry-run    Show the plan only.
  sudo bash uninstall.sh --apply      Execute the documented control-plane removal.
  bash uninstall.sh --help            Show this help.

Removes CloudVirt web/API/worker/Agent integration and scheduled jobs.
Preserves PostgreSQL database/role, config/secrets/TLS, VMs, disks, snapshots,
backups, OS packages, service accounts, libvirt and existing network services.
The dedicated bridge helper and its executable stay installed so retained
VM networking can survive a reboot. No bridges, NICs, NAT rules, DHCP, UFW
rules, system forwarding settings, or shared nginx sites are removed.
There is deliberately no --purge-data option.
HELP
}
log() { printf '[CloudVirt uninstall] %s\n' "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }
on_error() {
    local result=$?
    printf '[CloudVirt uninstall] Failed at %s, line %s (exit %s). Backup: %s\n' "$STEP" "$1" "$result" "${BACKUP:-not created}" >&2
    exit "$result"
}
trap 'on_error "$LINENO"' ERR
while (($#)); do
    case "$1" in
        --apply) APPLY=true;;
        --dry-run) APPLY=false;;
        --help|-h) usage; exit 0;;
        *) die "Unknown option: $1";;
    esac
    shift
done

# Fixed allowlist; validate canonical targets before every recursive removal.
assert_path() {
    local target=$1
    case "$target" in
        /opt/cloudvirt/apps|/opt/cloudvirt/frontend|/opt/cloudvirt/.venv|/opt/cloudvirt/runtime|/opt/cloudvirt/offline|/var/www/cloudvirt) ;;
        *) die "Path is not an approved application directory: $target";;
    esac
    [[ ! -L "$target" && $(realpath -m -- "$target") == "$target" ]] || die "Refusing symlinked application path: $target"
}
remove_app_tree() {
    local target=$1
    assert_path "$target"
    [[ ! -e "$target" ]] || rm -rf --one-file-system -- "$target"
}

# Only literal installer-owned units; no broad cloudvirt* stop/delete glob.
JOBS=(collect_node_status reconcile cleanup_console_sessions cleanup_account_batches)
SERVICES=(cloudvirt-management.service cloudvirt-worker.service cloudvirt-agent.service
          cloudvirt-media.service cloudvirt-workbench-broker.service)
TIMERS=()
for job in "${JOBS[@]}"; do
    TIMERS+=("cloudvirt-$job.timer")
    SERVICES+=("cloudvirt-$job.service")
done
# Retired periodic jobs may remain on installations upgraded from older versions.
for job in reconcile_broadcasts reconcile_workspaces; do
    TIMERS+=("cloudvirt-$job.timer")
    SERVICES+=("cloudvirt-$job.service")
done
TARGETS=("$APP_DIR/apps" "$APP_DIR/frontend" "$APP_DIR/.venv" "$APP_DIR/runtime" "$APP_DIR/offline" "$WEB_ROOT")
log "Mode: $([[ "$APPLY" == true ]] && printf APPLY || printf PLAN-ONLY)"
log "Stop/disable/remove units: ${TIMERS[*]} ${SERVICES[*]}"
log "Remove CloudVirt nginx site, console/security/HSTS snippets and application directories: ${TARGETS[*]}"
log "Keep /etc/cloudvirt, all databases, /var/lib/cloudvirt, /var/lib/libvirt, backups and service accounts."
log "Keep cloudvirt-network, cloudvirt-ovs-* and $APP_DIR/services for existing VM networking."
log "Keep source checkouts, OS packages, firewall rules and shared web server configuration."
if [[ "$APPLY" != true ]]; then
    log "Nothing changed. Execution requires an explicit --apply."
    exit 0
fi

[[ $EUID == 0 ]] || die "Run with sudo bash uninstall.sh --apply"
[[ -d /run/systemd/system ]] || die "A booted systemd host is required"
[[ -f /etc/cloudvirt/install-secrets.env && ! -L /etc/cloudvirt/install-secrets.env ]] || die "Installer-owned deployment marker not found; refusing to remove an unmanaged deployment"
[[ $(stat -c %u /etc/cloudvirt/install-secrets.env) == 0 && $(stat -c %a /etc/cloudvirt/install-secrets.env) == 600 ]] || die "Invalid installer deployment marker ownership/mode"
for tool in realpath systemctl flock tar nginx findmnt; do
    command -v "$tool" >/dev/null || die "Missing required tool: $tool"
done
exec 9>/run/lock/cloudvirt-install.lock
flock -n 9 || die "Another installer/uninstaller is running"
for target in "${TARGETS[@]}"; do
    assert_path "$target"
    # Do not silently traverse a dedicated application filesystem or nested mounts.
    while IFS= read -r mounted; do
        [[ "$mounted" != "$target" && "$mounted" != "$target/"* ]] || die "Unmount application filesystem before removal: $mounted"
    done < <(findmnt -rn -o TARGET)
done
for root in /etc/nginx/sites-available /etc/nginx/sites-enabled /etc/nginx/snippets /etc/systemd/system; do
    [[ ! -L "$root" && $(realpath -m -- "$root") == "$root" ]] || die "Refusing redirected system configuration root: $root"
done
for file in /etc/nginx/sites-available/cloudvirt /etc/nginx/snippets/cloudvirt-console.conf \
            /etc/nginx/snippets/cloudvirt-security-headers.conf /etc/nginx/snippets/cloudvirt-hsts.conf; do
    [[ ! -L "$file" ]] || die "Unexpected symlink in CloudVirt nginx file: $file"
done
if [[ -L /etc/nginx/sites-enabled/cloudvirt ]]; then
    [[ $(realpath -m /etc/nginx/sites-enabled/cloudvirt) == /etc/nginx/sites-available/cloudvirt ]] || die "CloudVirt site points outside installer-owned configuration"
fi
[[ ! -e /etc/nginx/sites-enabled/cloudvirt || -L /etc/nginx/sites-enabled/cloudvirt ]] || die "Enabled CloudVirt site is not the installer symlink"

STEP=backup
[[ ! -L /var/backups/cloudvirt && $(realpath -m /var/backups/cloudvirt) == /var/backups/cloudvirt ]] || die "Invalid backup directory"
install -d -m 0700 /var/backups/cloudvirt
BACKUP=$(mktemp -d /var/backups/cloudvirt/uninstall-XXXXXXXX)
# Configuration backup is retained even if a later stage fails; no database is changed.
if [[ -d /etc/cloudvirt ]]; then tar -czf "$BACKUP/config.tar.gz" -C /etc cloudvirt; fi
install -d -m 0700 "$BACKUP/nginx" "$BACKUP/units"
for file in /etc/nginx/sites-available/cloudvirt /etc/nginx/sites-enabled/cloudvirt \
            /etc/nginx/snippets/cloudvirt-console.conf \
            /etc/nginx/snippets/cloudvirt-security-headers.conf \
            /etc/nginx/snippets/cloudvirt-hsts.conf; do
    if [[ -e "$file" || -L "$file" ]]; then cp -a --parents -- "$file" "$BACKUP/nginx/"; fi
done
for unit in "${TIMERS[@]}" "${SERVICES[@]}"; do
    [[ ! -e /etc/systemd/system/$unit ]] || cp -a -- "/etc/systemd/system/$unit" "$BACKUP/units/"
done
if [[ -d /etc/systemd/system/cloudvirt-agent.service.d ]]; then
    cp -a -- /etc/systemd/system/cloudvirt-agent.service.d "$BACKUP/units/"
fi

STEP=nginx
nginx -t
rm -f -- /etc/nginx/sites-enabled/cloudvirt /etc/nginx/sites-available/cloudvirt \
    /etc/nginx/snippets/cloudvirt-console.conf \
    /etc/nginx/snippets/cloudvirt-security-headers.conf \
    /etc/nginx/snippets/cloudvirt-hsts.conf
if ! nginx -t; then
    log "Remaining nginx configuration is invalid; restoring CloudVirt nginx files."
    if [[ -d "$BACKUP/nginx/etc/nginx" ]]; then cp -a "$BACKUP/nginx/etc/nginx/." /etc/nginx/; fi
    die "nginx validation failed; no application services were stopped"
fi
if systemctl is-active --quiet nginx; then systemctl reload nginx; fi

STEP=services
for unit in "${TIMERS[@]}" "${SERVICES[@]}"; do
    if [[ $(systemctl show "$unit" -p LoadState --value) != not-found ]]; then
        systemctl stop "$unit"
        systemctl disable "$unit"
    fi
    rm -f -- "/etc/systemd/system/$unit"
done
# Exact installer drop-in only; custom overrides are preserved for administrator review.
rm -f -- /etc/systemd/system/cloudvirt-agent.service.d/install.conf
systemctl daemon-reload

STEP=application-files
for target in "${TARGETS[@]}"; do remove_app_tree "$target"; done
STEP=complete
log "Control-plane uninstall completed. Backup: $BACKUP"
log "VMs/disks/database/secrets and networking were preserved. Shared packages were not removed."
log "Remaining $APP_DIR/services and network units are intentional; source/deployment backups remain."
log "Reinstall using the complete source tree and existing /etc/cloudvirt installer secrets."
