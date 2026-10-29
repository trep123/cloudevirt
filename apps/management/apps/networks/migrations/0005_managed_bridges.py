from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('networks', '0004_instancenic_ippool_iplease_and_more'),
        ('nodes', '0002_nodeaccess'),
    ]
    operations = [
        migrations.AddField(
            model_name='network',
            name='node',
            field=models.ForeignKey(
                to='nodes.node', on_delete=django.db.models.deletion.PROTECT, null=True, blank=True
            ),
        ),
        migrations.AddField(
            model_name='network', name='managed', field=models.BooleanField(default=False)
        ),
        migrations.AddField(
            model_name='network',
            name='uplink',
            field=models.CharField(max_length=15, blank=True, default=''),
        ),
        migrations.AddField(
            model_name='network',
            name='provisioning_status',
            field=models.CharField(max_length=16, default='READY'),
        ),
        migrations.AddField(
            model_name='network',
            name='last_error',
            field=models.CharField(max_length=500, blank=True, default=''),
        ),
    ]
