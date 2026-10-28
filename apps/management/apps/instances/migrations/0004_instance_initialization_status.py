from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('instances', '0003_instance_creation_config')]
    operations = [
        migrations.AddField(
            model_name='instance',
            name='initialization_status',
            field=models.CharField(default='NOT_CONFIGURED', max_length=20),
        )
    ]
