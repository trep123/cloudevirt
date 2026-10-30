from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('templates', '0003_template_assigned_users')]
    operations = [
        migrations.AddField(
            model_name='templateversion',
            name='is_deleted',
            field=models.BooleanField(default=False),
        )
    ]
