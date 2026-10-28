#!/usr/bin/python3
"""Privileged, UUID-scoped systemd launcher. Never accepts commands or paths from an HTTP body."""

import argparse
import fcntl
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def private_json(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(fd)
        if metadata.st_uid != 0 or metadata.st_mode & 0o022:
            raise ValueError("unsafe configuration")
        with os.fdopen(fd, "r", closefd=False) as stream:
            return json.load(stream)
    finally:
        os.close(fd)


def execute(args, timeout=15):
    return subprocess.run(
        args,
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=timeout,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/etc/cloudvirt/workbench.json")
    parser.add_argument("operation", choices=["start", "stop", "status"])
    parser.add_argument("identity")
    args = parser.parse_args()
    if os.geteuid() != 0 or not UUID.fullmatch(args.identity):
        raise ValueError("invalid workspace")
    if (
        args.config != "/etc/cloudvirt/workbench.json"
        and os.environ.get("SUDO_UID", "0") != "0"
    ):
        raise ValueError("configuration override forbidden")
    cfg = private_json(args.config)
    identity = args.identity
    prefix = cfg.get("prefix", "cloudvirt-workbench-")
    if not re.fullmatch(r"cloudvirt-workbench[-a-z]*-", prefix):
        raise ValueError("invalid service prefix")
    unit = prefix + identity + ".service"
    registry = Path(cfg.get("registry", "/var/lib/cloudvirt-workbench-registry"))
    registry.mkdir(mode=0o700, parents=True, exist_ok=True)
    entry = registry / (identity + ".json")
    state_name = prefix + identity
    state = Path("/var/lib") / state_name

    def current():
        if not entry.exists():
            return {"state": "MISSING"}
        data = private_json(entry)
        result = {
            "state": "STARTING",
            "generation": data["generation"],
            "port": data["port"],
        }
        active = execute(
            ["systemctl", "show", unit, "--property=ActiveState", "--value"]
        ).stdout.strip()
        if active not in {"active", "activating"}:
            result["state"] = "STOPPED" if active == "inactive" else "ERROR"
            return result
        try:
            with (state / "status.json").open() as status_file:
                status_data = json.loads(status_file.read(16385))
            if status_data.get("generation") == data["generation"]:
                result["state"] = (
                    status_data.get("state", "ERROR")
                    if status_data.get("state")
                    in {"STARTING", "READY", "ERROR", "STOPPED"}
                    else "ERROR"
                )
                result["error"] = str(status_data.get("error", ""))[:256]
        except (OSError, ValueError):
            pass
        return result

    if args.operation == "status":
        print(json.dumps(current()))
        return
    lock = registry / "control.lock"
    with lock.open("a") as control:
        fcntl.flock(control, fcntl.LOCK_EX)
        if args.operation == "stop":
            if not entry.exists():
                print(json.dumps({"state": "STOPPED"}))
                return
            execute(["systemctl", "stop", unit], timeout=20)
            remaining = execute(
                ["systemctl", "show", unit, "--property=ActiveState", "--value"]
            ).stdout.strip()
            if remaining in {"active", "activating", "deactivating"}:
                raise ValueError("workspace still running")
            # Only a registry-owned, exact UUID state directory may be cleaned.
            execute(["systemctl", "clean", "--what=state", unit])
            for candidate in [Path("/var/lib/private") / state_name, state]:
                if candidate.is_symlink():
                    candidate.unlink()
                elif candidate.is_dir():
                    if candidate.name != state_name:
                        raise ValueError("unsafe state path")
                    shutil.rmtree(candidate)
            entry.unlink(missing_ok=True)
            (registry / (identity + ".credential")).unlink(missing_ok=True)
            print(json.dumps({"state": "STOPPED"}))
            return
        data = json.loads(sys.stdin.buffer.read(16385))
        if not UUID.fullmatch(data.get("generation", "")) or not re.fullmatch(
            r"[A-Za-z0-9_-]{43}", data.get("bootstrap_token", "")
        ):
            raise ValueError("invalid capability")
        if (
            not isinstance(data.get("owner"), int)
            or data["owner"] < 1
            or not re.fullmatch(r"[A-Za-z0-9]{8}", data.get("vnc_password", ""))
        ):
            raise ValueError("invalid owner")
        remaining = data.get("expires_at", 0) - int(time.time())
        if not 1 <= remaining <= 86400:
            raise ValueError("invalid lifetime")
        old = current()
        if old.get("state") in {"STARTING", "READY"}:
            if old.get("generation") != data["generation"]:
                raise ValueError("workspace generation differs")
            print(json.dumps(old))
            return
        count = 0
        for record in registry.glob("*.json"):
            other = record.stem
            if UUID.fullmatch(other):
                answer = execute(
                    ["systemctl", "is-active", prefix + other + ".service"]
                )
                if answer.returncode == 0:
                    count += 1
        if count >= int(cfg.get("limit", 2)):
            raise ValueError("workspace capacity reached")
        if entry.exists() or state.exists() or state.is_symlink():
            raise ValueError("old workspace must be stopped first")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        display = secrets.randbelow(20000) + 10000
        spec = {
            **data,
            "workspace": identity,
            "port": port,
            "display": display,
            "origin": cfg["origin"],
            "chrome": cfg["chrome"],
        }
        # Credentials are loaded into a private per-unit mount; never passed as argv/environment.
        credential = registry / (identity + ".credential")
        descriptor = os.open(credential, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as output:
            json.dump(spec, output)
        descriptor = os.open(entry, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as output:
            json.dump({"generation": data["generation"], "port": port}, output)
        properties = [
            "DynamicUser=yes",
            "NoNewPrivileges=yes",
            "PrivateTmp=yes",
            "PrivateDevices=yes",
            "ProtectSystem=strict",
            "ProtectHome=yes",
            "ProtectProc=invisible",
            "RestrictSUIDSGID=yes",
            "LockPersonality=yes",
            "MemoryMax=1536M",
            "CPUQuota=150%",
            "TasksMax=256",
            "TimeoutStopSec=8s",
            "KillMode=control-group",
            "RuntimeMaxSec=" + str(remaining),
            "StateDirectory=" + state_name,
            "StateDirectoryMode=0700",
            "WorkingDirectory=" + str(state),
            "Environment=HOME=" + str(state),
            "LoadCredential=spec:" + str(credential),
            "InaccessiblePaths=-/etc/cloudvirt -/opt/cloudvirt -/opt/cloudevirt -/var/lib/libvirt -/var/lib/postgresql -/run/libvirt",
            "SocketBindDeny=any",
            "SocketBindAllow=ipv4:tcp:" + str(port),
        ]
        if cfg.get("ca"):
            properties.append("LoadCredential=ca:" + cfg["ca"])
        command = ["systemd-run", "--quiet", "--unit=" + unit]
        command.extend("--property=" + item for item in properties)
        command.extend([cfg["node"], cfg["runner"]])
        if execute(command).returncode != 0:
            entry.unlink(missing_ok=True)
            credential.unlink(missing_ok=True)
            raise ValueError("renderer launch failed")
        print(
            json.dumps(
                {"state": "STARTING", "generation": data["generation"], "port": port}
            )
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - privileged boundary must not print credentials or raw subprocess errors.
        print(json.dumps({"state": "ERROR", "error": "WORKBENCH_OPERATION_FAILED"}))
        raise SystemExit(1)
