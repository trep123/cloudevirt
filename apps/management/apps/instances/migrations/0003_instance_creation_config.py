from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('instances', '0002_instance_vnc_password')]
    operations = [
        migrations.AddField(
            model_name='instance',
            name='creation_config',
            field=models.JSONField(default=dict, blank=True),
        )
    ]
