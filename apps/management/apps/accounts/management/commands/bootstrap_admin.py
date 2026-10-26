"""创建首个管理员账户。

受部署保护：必须设置环境变量 CLOUDVIRT_BOOTSTRAP_ADMIN=true，且系统中尚无管理员账户。
禁止提供无认证的公开注册入口。
"""

import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import UserProfile
from apps.accounts.roles import ROLE_ADMIN
from apps.accounts.views import generate_temporary_password

ENV_FLAG = 'CLOUDVIRT_BOOTSTRAP_ADMIN'


class Command(BaseCommand):
    """创建首个管理员，输出一次性口令。"""

    help = '创建首个管理员账户（需设置 CLOUDVIRT_BOOTSTRAP_ADMIN=true）'

    def add_arguments(self, parser) -> None:
        """注册命令行参数。"""
        parser.add_argument('--username', default='admin', help='管理员账号名')
        parser.add_argument('--password', default='', help='初始口令，留空则随机生成')

    def handle(self, *args, **options) -> None:
        """校验部署开关后创建管理员。"""
        if os.environ.get(ENV_FLAG, '') != 'true':
            raise CommandError(f'拒绝执行：请设置环境变量 {ENV_FLAG}=true 以确认这是受控的部署操作')
        user_model = get_user_model()
        if user_model.objects.filter(is_superuser=True).exists():
            raise CommandError('已存在管理员账户；后续账户请使用用户管理接口创建')
        username = options['username']
        if user_model.objects.filter(username=username).exists():
            raise CommandError(f'账号 {username} 已存在')

        password = options['password'] or generate_temporary_password()
        user = user_model(username=username, is_staff=True, is_superuser=True, is_active=True)
        user.set_password(password)
        user.save()
        UserProfile.objects.create(
            user=user,
            display_name=username,
            must_change_password=True,
        )
        admin_group, _ = Group.objects.get_or_create(name=ROLE_ADMIN)
        user.groups.add(admin_group)

        self.stdout.write(self.style.SUCCESS(f'已创建管理员: {username}'))
        self.stdout.write(f'初始口令（仅显示一次）: {password}')
        self.stdout.write('请首次登录后立即修改密码')
