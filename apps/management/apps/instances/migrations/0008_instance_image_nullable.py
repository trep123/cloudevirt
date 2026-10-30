from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('instances', '0007_alter_instance_options')]
    operations = [
        migrations.AlterField(
            model_name='instance',
            name='image',
            field=models.ForeignKey(
                to='images.image',
                on_delete=django.db.models.deletion.PROTECT,
                related_name='instances',
                verbose_name='镜像',
                null=True,
                blank=True,
            ),
        )
    ]
