#!/usr/bin/env bash
# Optional persistent server browser. Does not alter host networking or VM state.
set -Eeuo pipefail
umask 077
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
ORIGIN= CA= NODE="${CLOUDVIRT_WORKBENCH_NODE:-/opt/cloudvirt/runtime/node/bin/node}"
while (($#)); do
    case "$1" in
        --origin) ORIGIN=${2:?Missing origin}; shift 2;;
        --ca) CA=${2:?Missing CA certificate}; shift 2;;
        *) printf 'Unknown option: %s\n' "$1" >&2; exit 1;;
    esac
done
[[ $EUID == 0 && -x "$NODE" ]] || { printf 'Root and installed Node.js are required\n' >&2; exit 1; }
python3 - "$ORIGIN" <<'PY'
import sys
from urllib.parse import urlsplit
origin=urlsplit(sys.argv[1])
if origin.scheme!='https' or not origin.hostname or origin.username or origin.password or origin.path not in {'','/'} or origin.query or origin.fragment:
    raise SystemExit('Provide an HTTPS platform origin')
PY
if [[ -n "$CA" ]]; then openssl x509 -in "$CA" -noout >/dev/null; fi
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends xvfb x11vnc xauth libnss3-tools libgtk-3-0t64 libgbm1 libasound2t64 fonts-noto-cjk sudo apparmor-utils
RUNTIME=/usr/local/lib/cloudvirt-workbench
install -d -m 0755 "$RUNTIME" /opt/cloudvirt-workbench-browser /etc/cloudvirt
install -m 0755 "$NODE" "$RUNTIME/node"
install -m 0755 "$ROOT/services/workbench/control.py" "$ROOT/services/workbench/broker.py" "$RUNTIME/"
install -m 0644 "$ROOT/services/workbench/runner.mjs" "$ROOT/services/workbench/package.json" "$ROOT/services/workbench/package-lock.json" "$RUNTIME/"
task_node_dir=$(dirname -- "$NODE")
PATH="$task_node_dir:$PATH" npm --prefix "$RUNTIME" ci --ignore-scripts --omit=dev --no-audit --no-fund
PLAYWRIGHT_BROWSERS_PATH=/opt/cloudvirt-workbench-browser "$RUNTIME/node" "$RUNTIME/node_modules/playwright-core/cli.js" install chromium --no-shell
CHROME=$(cd "$RUNTIME" && PLAYWRIGHT_BROWSERS_PATH=/opt/cloudvirt-workbench-browser ./node --input-type=module -e 'import {chromium} from "playwright-core";console.log(chromium.executablePath())')
[[ -x "$CHROME" && "$CHROME" == /opt/cloudvirt-workbench-browser/* ]] || exit 1
chmod -R a+rX /opt/cloudvirt-workbench-browser "$RUNTIME/node_modules"
# Allow user namespaces only for this root-owned browser executable. Keep its sandbox enabled.
cat > /etc/apparmor.d/cloudvirt-workbench-browser <<PROFILE
abi <abi/4.0>,
include <tunables/global>
profile cloudvirt-workbench-browser $CHROME flags=(unconfined) {
    userns,
}
PROFILE
apparmor_parser -r /etc/apparmor.d/cloudvirt-workbench-browser
if [[ -n "$CA" ]]; then install -m 0600 "$CA" /etc/cloudvirt/workbench-ca.crt; CA=/etc/cloudvirt/workbench-ca.crt; fi
python3 - "$ORIGIN" "$CHROME" "$CA" <<'PY'
import json,os,sys,tempfile
config={'origin':sys.argv[1].rstrip('/'),'chrome':sys.argv[2],'ca':sys.argv[3], 'node':'/usr/local/lib/cloudvirt-workbench/node','runner':'/usr/local/lib/cloudvirt-workbench/runner.mjs','limit':2}
with tempfile.NamedTemporaryFile('w',dir='/etc/cloudvirt',delete=False) as output:
    json.dump(config,output)
os.chmod(output.name,0o600)
os.replace(output.name,'/etc/cloudvirt/workbench.json')
PY
install -d -m 0700 /var/lib/cloudvirt-workbench-registry
cat > /etc/systemd/system/cloudvirt-workbench-broker.service <<'UNIT'
[Unit]
Description=CloudVirt bounded local workbench launcher
After=network.target
[Service]
Type=simple
User=root
Group=cloudvirt-agent
RuntimeDirectory=cloudvirt-workbench
RuntimeDirectoryMode=0750
ExecStart=/usr/bin/python3 /usr/local/lib/cloudvirt-workbench/broker.py
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
# The helper reserves a loopback VNC port before asking systemd to start a unit.
# The broker itself continues to listen exclusively on its authenticated Unix socket.
RestrictAddressFamilies=AF_UNIX AF_INET
TasksMax=32
MemoryMax=128M
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now cloudvirt-workbench-broker.service
systemctl restart cloudvirt-workbench-broker.service
printf '%s\n' 'Workbench runtime installed. Enable WORKBENCH_ENABLED=true and the reconcile_workspaces timer after applying migrations.'
