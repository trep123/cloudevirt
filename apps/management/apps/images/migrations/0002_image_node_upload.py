import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('images', '0001_initial'),
        ('nodes', '0002_nodeaccess'),
        ('tasks', '0005_infrastructure_task_types'),
    ]
    operations = [
        migrations.AddField(
            model_name='image',
            name='node',
            field=models.ForeignKey(
                to='nodes.node',
                on_delete=django.db.models.deletion.PROTECT,
                null=True,
                blank=True,
                related_name='images',
                verbose_name='所属节点',
            ),
        ),
        migrations.CreateModel(
            name='ImageUpload',
            fields=[
                (
                    'id',
                    models.UUIDField(
                        primary_key=True, default=uuid.uuid4, editable=False, serialize=False
                    ),
                ),
                ('original_name', models.CharField(max_length=255)),
                ('size_bytes', models.BigIntegerField()),
                ('extension', models.CharField(max_length=8)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'image',
                    models.OneToOneField(
                        to='images.image',
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='upload',
                    ),
                ),
                (
                    'task',
                    models.ForeignKey(
                        to='tasks.task',
                        on_delete=django.db.models.deletion.SET_NULL,
                        null=True,
                        blank=True,
                    ),
                ),
            ],
        ),
    ]
