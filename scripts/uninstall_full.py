#!/usr/bin/env python3
"""Explicit CloudVirt full purge. Source checkout is always preserved."""

import argparse
import fcntl
import grp
import ipaddress
import json
import os
import pwd
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

APP = Path("/opt/cloudvirt")
CONFIG = Path("/etc/cloudvirt")
STATE = Path("/var/lib/cloudvirt-installer")
TREES = [
    APP,
    CONFIG,
    Path("/var/www/cloudvirt"),
    Path("/var/lib/cloudvirt"),
    Path("/var/lib/cloudvirt-agent"),
    Path("/var/lib/cloudvirt-dhcp"),
    Path("/var/log/cloudvirt"),
    Path("/var/backups/cloudvirt"),
]
UNITS = [
    f"cloudvirt-{name}.service"
    for name in (
        "management",
        "worker",
        "agent",
        "network",
        "ovs-net",
        "ovs-dhcp",
        "media",
        "workbench-broker",
    )
]
for job in (
    "collect_node_status",
    "reconcile",
    "cleanup_console_sessions",
    "cleanup_account_batches",
    "reconcile_broadcasts",
    "reconcile_workspaces",
):
    UNITS += [f"cloudvirt-{job}.timer", f"cloudvirt-{job}.service"]


def run(*args, capture=False):
    result = subprocess.run(args, check=True, text=True, capture_output=capture)
    return result.stdout.strip() if capture else ""


def trusted(path):
    if path.is_symlink() or path.resolve() != path.absolute():
        raise ValueError(f"Refusing symlinked path: {path}")
    if path.exists() and path.stat().st_uid != 0:
        raise ValueError(f"Expected root-owned configuration: {path}")
    if path.exists() and path.stat().st_mode & 0o022:
        raise ValueError(f"Configuration writable by non-root accounts: {path}")


def env_file(name):
    path = CONFIG / name
    trusted(path)
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if line and not line.startswith("#") and "=" in line
    )


def overlaps(one, two):
    return one == two or one in two.parents or two in one.parents


def check_tree(path, project, mounts):
    if overlaps(path, project):
        raise ValueError(
            f"Project directory overlaps purge target: {path}; move the source checkout first"
        )
    if path.is_symlink() or path.resolve() != path.absolute():
        raise ValueError(f"Refusing redirected purge target: {path}")
    if any(mount == path or path in mount.parents for mount in mounts):
        raise ValueError(f"Unmount filesystems under purge target first: {path}")
    if path.exists() and any(path.rglob(".git")):
        raise ValueError(
            f"Git checkout found inside purge target, preserving it: {path}"
        )


def remove_nginx():
    paths = [
        Path("/etc/nginx") / name
        for name in (
            "sites-enabled/cloudvirt",
            "sites-available/cloudvirt",
            "snippets/cloudvirt-console.conf",
            "snippets/cloudvirt-security-headers.conf",
            "snippets/cloudvirt-hsts.conf",
        )
    ]
    saved = {}
    for path in paths:
        if path.is_symlink():
            if path != paths[0] or path.resolve() != paths[1]:
                raise ValueError(f"Unexpected nginx symlink: {path}")
            saved[path] = ("link", os.readlink(path))
        elif path.exists():
            trusted(path)
            saved[path] = ("file", path.read_bytes())
    run("nginx", "-t")
    for path in paths:
        path.unlink(missing_ok=True)
    try:
        run("nginx", "-t")
    except subprocess.CalledProcessError:
        for path, (kind, content) in saved.items():
            if kind == "link":
                path.symlink_to(content)
            else:
                path.write_bytes(content)
        raise ValueError(
            "Other nginx sites depend on CloudVirt snippets; original files restored"
        ) from None
    active = (
        subprocess.run(
            ["systemctl", "is-active", "--quiet", "nginx"], check=False
        ).returncode
        == 0
    )
    if active:
        run("systemctl", "reload", "nginx")


INVENTORY = r"""
import json, os
from pathlib import PurePosixPath
from apps.instances.models import Instance, Disk
from apps.images.models import Image
from apps.infrastructure.models import ManagedStoragePool
files, preserved = set(), set()
for disk in Disk.objects.select_related('instance__storage_pool'):
    vm=disk.instance
    root=vm.storage_pool.path if vm.storage_pool_id else os.environ['CLOUDVIRT_DISK_DIR']
    path=str(PurePosixPath(root)/disk.relative_path)
    config=vm.creation_config or {}
    files.add(str(PurePosixPath(root)/('.create-'+str(vm.uuid)+'.json')))
    if disk.role=='SYSTEM' and config.get('existing_system_file') and config.get('clone_mode','direct')=='direct':
        preserved.add(path)
    else:
        files.add(path)
        if config.get('initialization'):
            files.add(str(PurePosixPath(path).parent/('.init-'+str(vm.uuid)+'.iso')))
        checksum=config.get('image',{}).get('checksum','')
        if config.get('clone_mode')=='linked' and len(checksum)==64 and all(c in '0123456789abcdef' for c in checksum):
            files.add(str(PurePosixPath(path).parent/'.bases'/(checksum+'.qcow2')))
for image in Image.objects.select_related('storage_pool'):
    root=image.storage_pool.path if image.storage_pool_id else os.environ['CLOUDVIRT_IMAGE_DIR']
    # Only browser uploads were created by the platform. Registered external originals stay intact.
    path=str(PurePosixPath(root)/image.relative_path)
    if hasattr(image,'upload'):
        files.add(path)
        files.add(str(PurePosixPath(path).parent/('.upload-'+image.upload.pk.hex+'.part')))
    else: preserved.add(path)
print(json.dumps({'domains':list(Instance.objects.values('libvirt_domain_name','uuid')),
 'pools':list(ManagedStoragePool.objects.values('name','path')),
 'files':sorted(files-preserved),'preserved_originals':sorted(preserved)},default=str))
"""


def inventory():
    command = [
        "bash",
        "-c",
        'set -a; . /etc/cloudvirt/management.env; . /etc/cloudvirt/agent.env; set +a; exec "$@"',
        "cloudvirt-inventory",
        str(APP / ".venv/bin/python"),
        "manage.py",
        "shell",
        "--verbosity",
        "0",
        "-c",
        INVENTORY,
    ]
    result = subprocess.run(
        command, cwd=APP / "apps/management", check=True, text=True, capture_output=True
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def main():
    parser = argparse.ArgumentParser(
        description="CloudVirt complete purge; source checkout preserved"
    )
    parser.add_argument("--project-dir", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm", choices=["DELETE-CLOUDVIRT"])
    parser.add_argument(
        "--packages",
        nargs="+",
        help="Explicit package list for old installs without provenance",
    )
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error(
            "Run with sudo, including preview (inventory needs protected configuration)"
        )
    project = args.project_dir.resolve(strict=True)
    source = Path(__file__).resolve().parent.parent
    for path in (CONFIG, STATE):
        trusted(path)
    marker = CONFIG / "install-secrets.env"
    trusted(marker)
    if not marker.is_file() or marker.stat().st_mode & 0o777 != 0o600:
        raise ValueError("Installer marker is missing or has invalid permissions")
    for name in ("management.env", "agent.env"):
        trusted(CONFIG / name)
    with open("/run/lock/cloudvirt-install.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return purge_installation(args, project, source, parser)


def purge_installation(args, project, source, parser):
    agent = env_file("agent.env")
    database = urlparse(env_file("management.env").get("DATABASE_URL", ""))
    if (
        database.hostname not in ("localhost", "127.0.0.1")
        or database.path != "/cloudvirt"
        or database.username != "cloudvirt"
    ):
        raise ValueError(
            "Full purge supports only the installer local cloudvirt database/role"
        )
    package_file = STATE / "added-packages.txt"
    packages = args.packages
    if packages is None:
        if package_file.exists() and not (STATE / "provenance-incomplete").exists():
            trusted(package_file)
            packages = package_file.read_text().splitlines()
        elif args.apply and not args.dry_run:
            raise ValueError(
                "Old install has no complete package provenance. Preview first; supply --packages with an audited package list"
            )
        else:
            packages = []
            print(
                "PACKAGE PROVENANCE MISSING: apply requires an explicit audited --packages list."
            )
    if any(
        not re.fullmatch(r"[a-z0-9][a-z0-9+.-]*(?::[a-z0-9]+)?", package)
        for package in packages
    ):
        raise ValueError("Invalid package name")
    if packages:
        simulation = run("apt-get", "-s", "purge", "--", *packages, capture=True)
        removals = {
            line.split()[1].split(":")[0]
            for line in simulation.splitlines()
            if line.startswith(("Remv ", "Purg "))
        }
        if removals - {package.split(":")[0] for package in packages}:
            raise ValueError(
                "Package purge would remove unrecorded packages; review the package list"
            )
    service_users = []
    for name, home in (
        ("cloudvirt", "/var/lib/cloudvirt"),
        ("cloudvirt-agent", "/var/lib/cloudvirt-agent"),
    ):
        try:
            user = pwd.getpwnam(name)
        except KeyError:
            continue
        if user.pw_dir != home or user.pw_shell not in (
            "/usr/sbin/nologin",
            "/bin/false",
        ):
            raise ValueError(f"Service account has nonstandard configuration: {name}")
        try:
            if set(grp.getgrnam(name).gr_mem) - {name}:
                raise ValueError(f"Service group has other members: {name}")
        except KeyError:
            pass
        service_users.append(name)
    ovs = env_file("ovs.env") if (CONFIG / "ovs.env").exists() else None
    if ovs and (
        ovs.get("OVS_BRIDGE") != "ovsbr0"
        or ovs.get("OVS_INTERNAL") != "ovsbr0-int"
        or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,15}", ovs.get("OVS_UPLINK", ""))
    ):
        raise ValueError("Dedicated OVS configuration is nonstandard")
    if ovs:
        ipaddress.ip_network(ovs["OVS_SUBNET"], strict=True)
    if any(package.startswith("postgresql") for package in packages):
        others = run(
            "runuser",
            "-u",
            "postgres",
            "--",
            "psql",
            "-Atc",
            "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname NOT IN ('postgres','cloudvirt');",
            capture=True,
        )
        if others:
            raise ValueError("Other PostgreSQL databases exist; refusing package purge")
    data = inventory()
    mounts = [
        Path(line)
        for line in run("findmnt", "-rn", "-o", "TARGET", capture=True).splitlines()
    ]
    for path in TREES + [STATE]:
        check_tree(path, project, mounts)
        check_tree(path, source, mounts)
    roots = [Path(agent[key]) for key in ("CLOUDVIRT_DISK_DIR", "CLOUDVIRT_IMAGE_DIR")]
    roots += [
        Path(root)
        for root in agent.get("CLOUDVIRT_STORAGE_ROOTS", "").split(",")
        if root
    ]
    for path in roots:
        forbidden = (
            Path("/etc"),
            Path("/usr"),
            Path("/root"),
            Path("/home"),
            Path("/proc"),
            Path("/sys"),
            Path("/dev"),
            Path("/run"),
        )
        if (
            not path.is_absolute()
            or path == Path("/")
            or path.resolve() != path
            or any(path == entry or entry in path.parents for entry in forbidden)
        ):
            raise ValueError("Invalid configured data root")
    files = [Path(value) for value in data["files"]]
    created_directories = []
    directory_record = STATE / "created-storage-directories.txt"
    if directory_record.exists():
        trusted(directory_record)
        for value in directory_record.read_text().splitlines():
            path = Path(value)
            if (
                not path.is_absolute()
                or path.resolve() != path
                or path == Path("/")
                or overlaps(path, project)
                or overlaps(path, source)
                or not (
                    path in roots or path == Path("/var/lib/libvirt/images/cloudvirt")
                )
            ):
                raise ValueError(f"Invalid recorded storage directory: {path}")
            created_directories.append(path)
    for path in files:
        if (
            not path.is_absolute()
            or ".." in path.parts
            or path.is_symlink()
            or path.resolve() != path
            or overlaps(path, project)
            or overlaps(path, source)
            or not any(root in path.parents for root in roots)
        ):
            raise ValueError(f"Unsafe managed file: {path}")
    for original in map(Path, data["preserved_originals"]):
        if any(tree == original or tree in original.parents for tree in TREES):
            raise ValueError(
                f"External original is inside an application purge tree; move it first: {original}"
            )
    print(
        json.dumps(
            {
                "mode": "APPLY" if args.apply and not args.dry_run else "PREVIEW",
                "preserve_project": str(project),
                "domains": data["domains"],
                "managed_files": data["files"],
                "preserve_external_originals": data["preserved_originals"],
                "remove_trees": list(map(str, TREES)),
                "purge_new_packages": packages,
                "remove_service_accounts": service_users,
                "remove_empty_created_storage_directories": list(
                    map(str, created_directories)
                ),
                "database": "cloudvirt (DROP)",
                "units": UNITS,
            },
            indent=2,
        )
    )
    if not args.apply or args.dry_run:
        return
    if args.confirm != "DELETE-CLOUDVIRT":
        parser.error("Destructive apply requires --confirm DELETE-CLOUDVIRT")
    dependencies = run(
        "runuser",
        "-u",
        "postgres",
        "--",
        "psql",
        "-Atc",
        "SELECT DISTINCT d.datname FROM pg_shdepend s JOIN pg_database d ON d.oid=s.dbid "
        "WHERE s.refclassid='pg_authid'::regclass AND s.refobjid=(SELECT oid FROM pg_roles WHERE rolname='cloudvirt') "
        "AND d.datname<>'cloudvirt' UNION SELECT datname FROM pg_database "
        "WHERE datdba=(SELECT oid FROM pg_roles WHERE rolname='cloudvirt') AND datname<>'cloudvirt';",
        capture=True,
    )
    if dependencies:
        raise ValueError("cloudvirt role is used by other databases; refusing purge")
    # Verify domain ownership before stopping services or removing resources.
    existing = set(
        run(
            "virsh", "-c", "qemu:///system", "list", "--all", "--name", capture=True
        ).splitlines()
    )
    owned = {row["libvirt_domain_name"]: row["uuid"] for row in data["domains"]}
    if existing - set(owned):
        raise ValueError("Other libvirt domains exist; refusing full purge")
    for name in existing:
        if (
            not re.fullmatch(r"cv-[A-Za-z0-9_-]+", name)
            or run("virsh", "-c", "qemu:///system", "domuuid", name, capture=True)
            != owned[name]
        ):
            raise ValueError(f"Domain ownership mismatch: {name}")
    remove_nginx()
    # Stop producers before collecting a fresh resource inventory.
    for unit in UNITS:
        subprocess.run(
            ["systemctl", "disable", "--now", unit],
            check=False,
            stdout=subprocess.DEVNULL,
        )
    fresh = inventory()
    if fresh != data:
        raise ValueError(
            "Resources changed during preflight; services stopped, rerun preview"
        )
    existing = set(
        run(
            "virsh", "-c", "qemu:///system", "list", "--all", "--name", capture=True
        ).splitlines()
    )
    owned = {row["libvirt_domain_name"]: row["uuid"] for row in data["domains"]}
    if existing - set(owned):
        raise ValueError(
            "Other libvirt domains exist; refusing to remove shared virtualization packages"
        )
    for name in existing:
        if not re.fullmatch(r"cv-[A-Za-z0-9_-]+", name):
            raise ValueError(f"Unexpected owned domain name: {name}")
        if (
            run("virsh", "-c", "qemu:///system", "domuuid", name, capture=True)
            != owned[name]
        ):
            raise ValueError(f"Domain UUID mismatch: {name}")
    for name in existing:
        active = set(
            run(
                "virsh", "-c", "qemu:///system", "list", "--name", capture=True
            ).splitlines()
        )
        if name in active:
            run("virsh", "-c", "qemu:///system", "destroy", name)
        xml = run("virsh", "-c", "qemu:///system", "dumpxml", name, capture=True)
        flags = ["--managed-save", "--snapshots-metadata"] + (
            ["--nvram"] if "<nvram" in xml else []
        )
        run("virsh", "-c", "qemu:///system", "undefine", name, *flags)
    # Only remove individually inventoried files from external/shared roots.
    for path in files:
        path.unlink(missing_ok=True)
    for path in sorted(
        {
            parent
            for file in files
            for parent in file.parents
            if parent not in roots and any(root in parent.parents for root in roots)
        },
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        try:
            path.rmdir()
        except OSError:
            pass  # Preserve directories containing unowned files.
    for pool in data["pools"]:
        name = pool["name"]
        if not re.fullmatch(r"cv-[A-Za-z0-9_-]+", name):
            raise ValueError("Unexpected pool name")
        if (
            name
            in run(
                "virsh", "-c", "qemu:///system", "pool-list", "--name", capture=True
            ).splitlines()
        ):
            run("virsh", "-c", "qemu:///system", "pool-destroy", name)
        if (
            name
            in run(
                "virsh",
                "-c",
                "qemu:///system",
                "pool-list",
                "--all",
                "--name",
                capture=True,
            ).splitlines()
        ):
            run("virsh", "-c", "qemu:///system", "pool-undefine", name)
    if (STATE / "created-default-network").exists():
        active = run(
            "virsh", "-c", "qemu:///system", "net-list", "--name", capture=True
        ).splitlines()
        if "default" in active:
            run("virsh", "-c", "qemu:///system", "net-destroy", "default")
        all_networks = run(
            "virsh", "-c", "qemu:///system", "net-list", "--all", "--name", capture=True
        ).splitlines()
        if "default" in all_networks:
            run("virsh", "-c", "qemu:///system", "net-undefine", "default")
    # Network teardown must succeed before deleting durable network state.
    network_dir = Path("/var/lib/cloudvirt/network")
    for path in sorted(network_dir.glob("*.json")):
        trusted(path)
        spec = json.loads(path.read_text())
        bridge, uplink = spec["bridge"], spec["uplink"]
        if not all(
            re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,14}", name)
            for name in (bridge, uplink)
        ):
            raise ValueError("Invalid managed network configuration")
        if (Path("/sys/class/net") / bridge).exists():
            if spec["type"] == "OVS":
                ports = run(
                    "ovs-vsctl", "list-ports", bridge, capture=True
                ).splitlines()
                if set(ports) - {uplink}:
                    raise ValueError(f"Bridge has non-owned ports: {bridge}")
                run("ovs-vsctl", "--if-exists", "del-br", bridge)
            elif spec["type"] == "BRIDGE":
                members = {
                    item.name
                    for item in (Path("/sys/class/net") / bridge / "brif").iterdir()
                }
                if members - {uplink}:
                    raise ValueError(f"Bridge has non-owned members: {bridge}")
                run("ip", "link", "delete", "dev", bridge, "type", "bridge")
            else:
                raise ValueError("Unknown managed bridge type")
    if ovs:
        if (Path("/sys/class/net") / "ovsbr0").exists():
            ports = set(
                run("ovs-vsctl", "list-ports", "ovsbr0", capture=True).splitlines()
            )
            if ports - {"ovsbr0-int"}:
                raise ValueError("Dedicated OVS bridge still has non-owned ports")
            run("ovs-vsctl", "--if-exists", "del-br", "ovsbr0")
        if shutil.which("nft"):
            tables = run("nft", "list", "tables", capture=True).splitlines()
            if "table inet cloudvirt_ovs" in tables:
                run("nft", "delete", "table", "inet", "cloudvirt_ovs")
        Path("/etc/sysctl.d/99-cloudvirt-ovs.conf").unlink(missing_ok=True)
    if shutil.which("ufw"):
        for line in run("ufw", "show", "added", capture=True).splitlines():
            tokens = shlex.split(line)
            if (
                len(tokens) >= 5
                and tokens[0] == "ufw"
                and tokens[1] in ("allow", "route")
                and tokens[-2] == "comment"
                and tokens[-1]
                in ("CloudVirt console", "CloudVirt OVS egress", "CloudVirt DHCP")
            ):
                run("ufw", "--force", "delete", *tokens[1:-2])
    for unit in UNITS:
        (Path("/etc/systemd/system") / unit).unlink(missing_ok=True)
        for link in Path("/etc/systemd/system").glob("*.wants/" + unit):
            if not link.is_symlink():
                raise ValueError(f"Unexpected service enablement file: {link}")
            link.unlink()
    Path("/etc/systemd/system/cloudvirt-agent.service.d/install.conf").unlink(
        missing_ok=True
    )
    Path("/usr/local/sbin/cloudvirtctl").unlink(missing_ok=True)
    run("systemctl", "daemon-reload")
    run(
        "runuser",
        "-u",
        "postgres",
        "--",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        "DROP DATABASE IF EXISTS cloudvirt WITH (FORCE);",
    )
    run(
        "runuser",
        "-u",
        "postgres",
        "--",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        "DROP ROLE IF EXISTS cloudvirt;",
    )
    for tree in TREES:
        current_mounts = [
            Path(line)
            for line in run("findmnt", "-rn", "-o", "TARGET", capture=True).splitlines()
        ]
        check_tree(tree, project, current_mounts)
        check_tree(tree, source, current_mounts)
        if tree.exists():
            shutil.rmtree(tree)
    for directory in sorted(
        set(created_directories), key=lambda path: len(path.parts), reverse=True
    ):
        try:
            directory.rmdir()
        except FileNotFoundError:
            pass
        except OSError:
            print(f"Preserved nonempty storage directory: {directory}")
    for user in service_users:
        run("userdel", user)
        try:
            group = grp.getgrnam(user)
        except KeyError:
            continue
        if not group.gr_mem:
            run("groupdel", user)
    if packages:
        os.environ["DEBIAN_FRONTEND"] = "noninteractive"
        run("apt-get", "purge", "-y", "--", *packages)
    if STATE.exists():
        shutil.rmtree(STATE)
    print(
        "Full purge completed. Project/source checkout preserved; no uninstall was performed merely by preview."
    )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Purge stopped: {error}") from None
