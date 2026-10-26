#!/usr/bin/env python3
"""CloudVirt 管理后端命令行入口。

常用命令:
    python manage.py check
    python manage.py migrate
    python manage.py runserver 127.0.0.1:8000
    python manage.py test
"""

import os
import sys


def main() -> None:
    """执行 Django 管理命令，默认加载 config.settings。"""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            '无法导入 Django，请先安装依赖: pip install -r requirements/dev.txt'
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
