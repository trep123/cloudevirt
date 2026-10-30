from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('infrastructure', '0002_storagebackend'),
        ('nodes', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ManagedStoragePool',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name='ID'
                    ),
                ),
                ('name', models.CharField(max_length=64)),
                ('path', models.CharField(max_length=4096)),
                ('is_default', models.BooleanField(default=False)),
                ('revision', models.PositiveIntegerField(default=1)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'allowed_users',
                    models.ManyToManyField(
                        blank=True, related_name='storage_pools', to=settings.AUTH_USER_MODEL
                    ),
                ),
                (
                    'default_users',
                    models.ManyToManyField(
                        blank=True,
                        related_name='default_storage_pools',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'node',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='managed_storage_pools',
                        to='nodes.node',
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name='managedstoragepool',
            constraint=models.UniqueConstraint(
                fields=('node', 'name'), name='uniq_managed_storage_pool_node_name'
            ),
        ),
        migrations.AddConstraint(
            model_name='managedstoragepool',
            constraint=models.UniqueConstraint(
                condition=models.Q(is_default=True),
                fields=('node',),
                name='uniq_default_storage_pool_per_node',
            ),
        ),
    ]
