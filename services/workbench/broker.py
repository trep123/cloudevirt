#!/usr/bin/python3
"""Local-only privileged operations, authenticated by Unix peer credentials."""

import json
import os
import pwd
import re
import socket
import socketserver
import struct
import subprocess
import threading

IDENTITY = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
CAPACITY = threading.BoundedSemaphore(8)


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        if not CAPACITY.acquire(blocking=False):
            return
        try:
            self.request.settimeout(3)
            _, uid, _ = struct.unpack(
                "3i", self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            )
            if uid not in {0, pwd.getpwnam("cloudvirt-agent").pw_uid}:
                return
            line = self.rfile.readline(20001)
            if len(line) > 20000 or not line.endswith(b"\n"):
                return
            command = json.loads(line)
            if not isinstance(command, dict):
                return
            operation, identity = command.get("operation"), command.get("identity", "")
            if operation not in {"start", "stop", "status"} or not IDENTITY.fullmatch(
                identity
            ):
                return
            result = subprocess.run(
                [
                    "/usr/bin/python3",
                    "/usr/local/lib/cloudvirt-workbench/control.py",
                    operation,
                    identity,
                ],
                check=False,
                input=json.dumps(command.get("spec", {})).encode(),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=27,
            )
            if len(result.stdout) > 16384:
                return
            self.wfile.write(result.stdout)
        except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
            self.wfile.write(
                b'{"state":"ERROR","error":"WORKBENCH_OPERATION_FAILED"}\n'
            )
        finally:
            CAPACITY.release()


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True


if __name__ == "__main__":
    address = "/run/cloudvirt-workbench/control.sock"
    if os.path.exists(address):
        os.unlink(address)
    with Server(address, Handler) as server:
        os.chmod(address, 0o660)
        server.serve_forever()
