#!/usr/bin/env bash
# Build the Ubuntu 26 amd64 non-apt dependency bundle on an online Ubuntu 26 host.
set -Eeuo pipefail
umask 022

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
OUTPUT=${1:-$ROOT/offline/linux-amd64}
[[ $(uname -m) == x86_64 ]] || { echo 'Ubuntu amd64 host required' >&2; exit 1; }
[[ ! -e "$OUTPUT" ]] || { echo "Output already exists: $OUTPUT" >&2; exit 1; }
for tool in curl sha256sum tar python3 go rsync; do
    command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 1; }
done
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,14) else 1)' || {
    echo 'Python 3.14 or newer required' >&2; exit 1;
}
WORK=$(mktemp -d /var/tmp/cloudvirt-offline.XXXXXX)
trap 'rm -rf -- "$WORK"' EXIT
mkdir -p "$WORK/bundle/wheels" "$WORK/npm-cache" "$WORK/frontend" "$WORK/go"

echo '[CloudVirt offline] Downloading and verifying official Node.js 24 archive'
curl --proto '=https' --tlsv1.2 -fSL --retry 3 --connect-timeout 20 \
    https://nodejs.org/dist/latest-v24.x/SHASUMS256.txt -o "$WORK/SHASUMS256.txt"
NODE_FILE=$(awk '$2 ~ /^node-v24\.[0-9]+\.[0-9]+-linux-x64.tar.xz$/ {print $2; exit}' "$WORK/SHASUMS256.txt")
[[ "$NODE_FILE" =~ ^node-v24\.[0-9]+\.[0-9]+-linux-x64.tar.xz$ ]] || exit 1
awk -v file="$NODE_FILE" '$2 == file' "$WORK/SHASUMS256.txt" > "$WORK/bundle/node-official.sha256"
curl --proto '=https' --tlsv1.2 -fSL --retry 3 --connect-timeout 20 \
    "https://nodejs.org/dist/latest-v24.x/$NODE_FILE" -o "$WORK/bundle/$NODE_FILE"
(cd "$WORK/bundle"; sha256sum -c node-official.sha256)
mkdir -p "$WORK/node"
tar -xJf "$WORK/bundle/$NODE_FILE" --strip-components=1 -C "$WORK/node"
export PATH="$WORK/node/bin:$PATH"

echo '[CloudVirt offline] Downloading pinned Python binary wheels'
python3 -m venv "$WORK/venv"
"$WORK/venv/bin/python" -m pip download --only-binary=:all: \
    --dest "$WORK/bundle/wheels" \
    -r "$ROOT/apps/management/requirements/prod.txt" 'pip==26.2.2'
"$WORK/venv/bin/python" -m pip install --no-index --find-links "$WORK/bundle/wheels" \
    -r "$ROOT/apps/management/requirements/prod.txt"

echo '[CloudVirt offline] Caching the complete frontend lockfile, including optional linux-x64 packages'
cp "$ROOT/frontend/package.json" "$ROOT/frontend/package-lock.json" "$WORK/frontend/"
python3 - "$WORK/frontend/package-lock.json" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
lock = json.loads(path.read_text())
for package in lock.get('packages', {}).values():
    resolved = package.get('resolved', '')
    for original in ('https://registry.npmmirror.com', 'https://registry.npmjs.org'):
        if resolved.startswith(original + '/'):
            package['resolved'] = 'https://registry.npmjs.org' + resolved[len(original):]
            break
path.write_text(json.dumps(lock, indent=2) + '\n')
PY
(cd "$WORK/frontend"; npm ci --cache "$WORK/npm-cache" \
    --registry=https://registry.npmjs.org --no-audit --no-fund)
rm -rf -- "$WORK/frontend/node_modules"
(cd "$WORK/frontend"; npm ci --offline --cache "$WORK/npm-cache" \
    --registry=https://registry.npmjs.org --no-audit --no-fund)
tar -czf "$WORK/bundle/npm-cache.tar.gz" -C "$WORK/npm-cache" .

echo '[CloudVirt offline] Vendoring and building locked Go modules'
rsync -a --exclude=bin --exclude=vendor "$ROOT/services/virt-node-agent/" "$WORK/go/"
(cd "$WORK/go"; GOTOOLCHAIN=local go mod vendor)
(cd "$WORK/go"; CGO_ENABLED=0 GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off \
    GOFLAGS=-mod=vendor go build -o "$WORK/virt-node-agent" ./cmd/virt-node-agent)
tar -czf "$WORK/bundle/go-vendor.tar.gz" -C "$WORK/go" vendor

echo '[CloudVirt offline] Recording source locks and package SHA-256 checksums'
(cd "$ROOT"; sha256sum frontend/package.json frontend/package-lock.json \
    apps/management/requirements/base.txt apps/management/requirements/prod.txt \
    services/virt-node-agent/go.mod services/virt-node-agent/go.sum) > "$WORK/bundle/source.sha256"
(cd "$WORK/bundle"; find . -type f ! -name manifest.sha256 -print0 | sort -z | xargs -0 sha256sum) \
    > "$WORK/bundle/manifest.sha256"
mkdir -p "$(dirname -- "$OUTPUT")"
mv "$WORK/bundle" "$OUTPUT"
echo "[CloudVirt offline] Bundle ready: $OUTPUT"
