#!/usr/bin/env python3
"""Root CLI for optional CloudVirt controls; never removes VM resources."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

CONFIG = Path('/etc/cloudvirt')


def run(*args):
    subprocess.run(args, check=True)


def read_env(name):
    path = CONFIG / name
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'Invalid configuration file: {path}')
    return path.read_text().splitlines()


def value(lines, key):
    return next((line.split('=', 1)[1] for line in reversed(lines)
                 if line.startswith(key + '=')), '')


def update(name, key, new_value):
    path = CONFIG / name
    lines = read_env(name)
    metadata = path.stat()
    lines = [line for line in lines if not line.startswith(key + '=')]
    lines.append(key + '=' + new_value)
    with tempfile.NamedTemporaryFile(mode='w', dir=CONFIG, delete=False) as output:
        temporary = output.name
        output.write('\n'.join(lines) + '\n')
    try:
        os.chmod(temporary, metadata.st_mode & 0o777)
        os.chown(temporary, metadata.st_uid, metadata.st_gid)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description='CloudVirt 模块与网卡过滤管理工具')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status', help='查看模块状态和网卡豁免')
    for operation in ('enable', 'disable'):
        command = commands.add_parser(operation, help='启用或禁用模块')
        command.add_argument('module', choices=['network-bridge', 'destructive'])
    interface = commands.add_parser('interface', help='管理网卡自动过滤豁免')
    interface.add_argument('action', choices=['allow', 'protect'])
    interface.add_argument('name')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('请使用 sudo cloudvirtctl')
    if CONFIG.is_symlink() or CONFIG.resolve() != CONFIG:
        parser.error('配置目录不允许符号链接')
    if args.command == 'status':
        for unit in ('cloudvirt-network', 'cloudvirt-agent'):
            result = subprocess.run(['systemctl', 'is-active', unit], capture_output=True, text=True)
            print(f'{unit}: {result.stdout.strip()}')
        print('destructive:', value(read_env('agent.env'), 'CLOUDVIRT_ALLOW_DESTRUCTIVE') or 'false')
        print('bridge exemptions:', value(read_env('network.env'), 'CLOUDVIRT_BRIDGE_ALLOWED_INTERFACES') or '(none)')
        return
    if args.command == 'interface':
        if (not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,14}', args.name)
                or args.name == 'lo' or not (Path('/sys/class/net') / args.name).exists()):
            parser.error('网卡不存在或名称无效')
        key = 'CLOUDVIRT_BRIDGE_ALLOWED_INTERFACES'
        names = set(filter(None, value(read_env('network.env'), key).split(',')))
        if args.action == 'allow':
            names.add(args.name)
            print('跳过此网卡的管理地址和路由过滤；现有地址和路由不会迁移。')
        else:
            names.discard(args.name)
        update('network.env', key, ','.join(sorted(names)))
        # Do not re-enable a module the administrator deliberately disabled.
        run('systemctl', 'try-restart', 'cloudvirt-network')
    elif args.module == 'destructive':
        update('agent.env', 'CLOUDVIRT_ALLOW_DESTRUCTIVE', str(args.command == 'enable').lower())
        run('systemctl', 'try-restart', 'cloudvirt-agent')
    else:
        update('network.env', 'CLOUDVIRT_NETWORK_BRIDGE_ENABLED',
               str(args.command == 'enable').lower())
        run('systemctl', args.command, '--now', 'cloudvirt-network')
    print('配置已应用；已有虚拟机、网桥和磁盘不会被删除。')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'操作失败：{error}') from None
