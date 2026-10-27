from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('tasks', '0004_remove_task_uniq_active_task_per_resource_and_more')]
    operations = [
        migrations.AlterField(
            model_name='task',
            name='type',
            field=models.CharField(
                max_length=32,
                verbose_name='类型',
                choices=[
                    ('NODE_REFRESH', '刷新节点资源'),
                    ('INSTANCE_CREATE', '创建虚拟机'),
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
            ),
        )
    ]
