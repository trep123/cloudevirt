"""CloudVirt 管理后端 Django 配置。

所有配置项来自环境变量，禁止在代码中硬编码地址、端口、路径与密钥。
变量说明见 .env.example 与 docs/ENVIRONMENT_DEPLOYMENT.md 第 3 章。
"""

import os
from pathlib import Path
from urllib.parse import urlparse

# 应用版本，用于健康检查与升级追踪（见 docs/ENVIRONMENT_DEPLOYMENT.md 第 8 章）
APP_VERSION = '0.1.0'

BASE_DIR = Path(__file__).resolve().parent.parent

# 默认数据库：本机 PostgreSQL，仅用于未设置 DATABASE_URL 时的回退
DEFAULT_DATABASE_URL = 'postgresql://cloudvirt:change-me@127.0.0.1:5432/cloudvirt'


def read_bool(name: str, default: bool = False) -> bool:
    """读取布尔型环境变量。

    Args:
        name: 环境变量名。
        default: 未设置或无法解析时的默认值。

    Returns:
        解析后的布尔值，接受 1/true/yes/on（大小写不敏感）。
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


def read_list(name: str, default: list[str]) -> list[str]:
    """读取逗号分隔的列表型环境变量。

    Args:
        name: 环境变量名。
        default: 未设置时的默认值。

    Returns:
        去除空白后的非空列表。
    """
    raw = os.environ.get(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(',') if item.strip()]


def parse_database_url(url: str) -> dict[str, object]:
    """解析 PostgreSQL 连接串为 Django DATABASES 配置。

    Args:
        url: 形如 postgresql://user:password@host:port/name 的连接串。

    Returns:
        Django 数据库配置字典。

    Raises:
        ValueError: 连接串协议不是 postgres/postgresql，或缺少数据库名时抛出。
    """
    parsed = urlparse(url)
    if parsed.scheme not in {'postgres', 'postgresql'}:
        raise ValueError(f'DATABASE_URL 协议必须为 postgres/postgresql，当前为: {parsed.scheme}')
    database = parsed.path.lstrip('/')
    if not database:
        raise ValueError('DATABASE_URL 缺少数据库名')
    return {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': database,
        'USER': parsed.username or '',
        'PASSWORD': parsed.password or '',
        'HOST': parsed.hostname or '127.0.0.1',
        'PORT': str(parsed.port or 5432),
        'CONN_MAX_AGE': 60,
    }


DEBUG = read_bool('DJANGO_DEBUG', False)
ALLOWED_HOSTS = read_list('DJANGO_ALLOWED_HOSTS', ['localhost', '127.0.0.1'])

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError('生产环境必须设置 DJANGO_SECRET_KEY 环境变量')
    # 开发环境生成临时密钥，重启即失效，禁止用于生产
    from django.core.management.utils import get_random_secret_key

    SECRET_KEY = get_random_secret_key()

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'common',
    'apps.accounts',
    'apps.nodes',
    'apps.images',
    'apps.instances',
    'apps.tasks',
    'apps.networks',
    'apps.monitoring',
    'apps.audit',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'common.middleware.RequestIDMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': parse_database_url(os.environ.get('DATABASE_URL', DEFAULT_DATABASE_URL)),
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

REST_FRAMEWORK = {
    # 仅返回 JSON，避免在生产环境暴露可浏览 API 页面
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    # 默认要求认证，白名单视图（如健康检查）需显式放开
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    # 统一异常结构：{error:{code,message,details,request_id}}
    'EXCEPTION_HANDLER': 'common.exceptions.api_exception_handler',
    'DEFAULT_PAGINATION_CLASS': 'common.pagination.StandardPagination',
    'PAGE_SIZE': 20,
    # 时间统一 ISO 8601 UTC
    'DATETIME_FORMAT': '%Y-%m-%dT%H:%M:%SZ',
    # 输出 UTF-8 原文，不做 \uXXXX 转义
    'UNICODE_JSON': False,
}

# 列表接口每页条数上限，防止一次性拉取全表
API_MAX_PAGE_SIZE = int(os.environ.get('API_MAX_PAGE_SIZE', '100'))

# 登录安全策略（后续迁移到系统设置表，由管理员在线调整）
SECURITY_LOGIN_MAX_FAILED = int(os.environ.get('SECURITY_LOGIN_MAX_FAILED', '5'))
SECURITY_LOGIN_LOCK_SECONDS = int(os.environ.get('SECURITY_LOGIN_LOCK_SECONDS', '900'))
SECURITY_PASSWORD_MIN_LENGTH = int(os.environ.get('SECURITY_PASSWORD_MIN_LENGTH', '12'))
SECURITY_LOGIN_MAX_ATTEMPTS = int(os.environ.get('SECURITY_LOGIN_MAX_ATTEMPTS', '10'))
SECURITY_LOGIN_WINDOW_SECONDS = int(os.environ.get('SECURITY_LOGIN_WINDOW_SECONDS', '300'))

# 节点 Agent 调用配置（模块 C 起使用）
AGENT_SHARED_TOKEN = os.environ.get('AGENT_SHARED_TOKEN', '')
AGENT_REQUEST_TIMEOUT_SECONDS = int(os.environ.get('AGENT_REQUEST_TIMEOUT_SECONDS', '30'))

# 实例规格上限（后续迁移到系统设置表）
INSTANCE_MAX_VCPU = int(os.environ.get('INSTANCE_MAX_VCPU', '64'))
INSTANCE_MAX_MEMORY_MIB = int(os.environ.get('INSTANCE_MAX_MEMORY_MIB', '131072'))
INSTANCE_MAX_DISK_GIB = int(os.environ.get('INSTANCE_MAX_DISK_GIB', '2048'))

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'request_context': {
            '()': 'common.logging.RequestContextFilter',
        },
    },
    'formatters': {
        'standard': {
            'format': '%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s '
            'task_id=%(task_id)s %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
            'filters': ['request_context'],
        },
    },
    'root': {'handlers': ['console'], 'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO')},
    'loggers': {
        'django': {'handlers': ['console'], 'propagate': False},
    },
}
