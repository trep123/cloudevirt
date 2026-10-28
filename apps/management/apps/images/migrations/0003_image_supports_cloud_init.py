from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('images', '0002_image_node_upload')]
    operations = [
        migrations.AddField(
            model_name='image', name='supports_cloud_init', field=models.BooleanField(default=False)
        )
    ]
