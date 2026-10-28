from django.core.management.base import BaseCommand

from apps.console.services import gateway_key


class Command(BaseCommand):
    help = '输出仅供 nginx 内部授权子请求使用的网关密钥'

    def handle(self, *args, **options):
        self.stdout.write(gateway_key())
