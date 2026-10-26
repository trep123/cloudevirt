"""结构化日志支持：为日志补充 request_id 等链路字段。"""

import logging
from contextvars import ContextVar

# 当前请求的 request_id，由 RequestIDMiddleware 写入
request_id_var: ContextVar[str] = ContextVar('cloudvirt_request_id', default='')
# 当前请求的 task_id，由任务执行器写入（模块 J 使用）
task_id_var: ContextVar[str] = ContextVar('cloudvirt_task_id', default='')


def get_request_id() -> str:
    """返回当前上下文的 request_id。"""
    return request_id_var.get()


def get_task_id() -> str:
    """返回当前上下文的 task_id。"""
    return task_id_var.get()


class RequestContextFilter(logging.Filter):
    """为日志记录注入 request_id 与 task_id 字段。"""

    def filter(self, record: logging.LogRecord) -> bool:
        """补充上下文字段，始终返回 True 表示不丢弃记录。

        Args:
            record: 待处理的日志记录。

        Returns:
            恒为 True。
        """
        record.request_id = request_id_var.get()
        record.task_id = task_id_var.get()
        return True
