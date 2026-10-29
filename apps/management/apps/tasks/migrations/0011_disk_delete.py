from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('tasks', '0010_network_bridge_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='task',
            name='type',
            field=models.CharField(
                choices=[
                    ('NODE_REFRESH', '刷新节点资源'),
                    ('NETWORK_BRIDGE_CREATE', '创建桥接网络'),
                    ('DISK_DELETE', '删除保留磁盘'),
                    ('ACCOUNT_BATCH', '用户导入导出'),
                    ('INSTANCE_CREATE', '创建虚拟机'),
                    ('INSTANCE_DISPLAY', '修改虚拟机显示配置'),
                    ('INSTANCE_HARDWARE', '虚拟机硬件变更'),
                    ('INSTANCE_START', '启动虚拟机'),
                    ('INSTANCE_SHUTDOWN', '关闭虚拟机'),
                    ('INSTANCE_FORCE_STOP', '强制停止虚拟机'),
                    ('INSTANCE_REBOOT', '重启虚拟机'),
                    ('INSTANCE_DELETE', '删除虚拟机'),
                    ('IMAGE_IMPORT', '导入镜像'),
                    ('IMAGE_DELETE', '删除镜像'),
                    ('RECONCILE', '状态对账'),
                    ('STORAGE_POOL_CREATE', '创建存储池'),
                    ('INSTANCE_SNAPSHOT', '虚拟机快照'),
                ],
                max_length=32,
                verbose_name='类型',
            ),
        ),
    ]
