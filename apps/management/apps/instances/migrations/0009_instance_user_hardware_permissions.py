from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('instances', '0008_instance_image_nullable')]

    operations = [
        migrations.AlterModelOptions(
            name='instance',
            options={
                'ordering': ['-created_at'],
                'permissions': [
                    ('ssh_instance', '可以通过 Web SSH 连接虚拟机'),
                    ('manage_snapshot_instance', '可以管理虚拟机快照'),
                    ('start_instance', '可以启动虚拟机'),
                    ('shutdown_instance', '可以关闭虚拟机'),
                    ('reboot_instance', '可以重启虚拟机'),
                    ('force_stop_instance', '可以强制停止虚拟机'),
                    ('delete_disk_instance', '可以在删除实例时删除磁盘'),
                    ('connect_network_instance', '可以为自己的虚拟机连接已授权网络'),
                    ('manage_data_disk_instance', '可以管理自己的虚拟机数据盘'),
                ],
                'verbose_name': '虚拟机实例',
                'verbose_name_plural': '虚拟机实例',
            },
        )
    ]
