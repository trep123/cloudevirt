from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('infrastructure', '0003_managedstoragepool'),
        ('instances', '0009_instance_user_hardware_permissions'),
    ]

    operations = [
        migrations.AddField(
            model_name='instance',
            name='storage_pool',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='instances',
                to='infrastructure.managedstoragepool',
                verbose_name='存储池',
            ),
        ),
        migrations.AddField(
            model_name='resourcereservation',
            name='storage_pool',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='reservations',
                to='infrastructure.managedstoragepool',
                verbose_name='存储池',
            ),
        ),
    ]
