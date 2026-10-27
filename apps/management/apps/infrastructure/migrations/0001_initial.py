from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [('nodes', '0002_nodeaccess'), ('instances', '0002_instance_vnc_password')]
    operations = [
        migrations.CreateModel(
            name='Cluster',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        primary_key=True, serialize=False, auto_created=True, verbose_name='ID'
                    ),
                ),
                ('name', models.CharField(max_length=64, unique=True)),
                ('description', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='ClusterNode',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        primary_key=True, serialize=False, auto_created=True, verbose_name='ID'
                    ),
                ),
                (
                    'cluster',
                    models.ForeignKey(
                        to='infrastructure.cluster',
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='members',
                    ),
                ),
                (
                    'node',
                    models.OneToOneField(
                        to='nodes.node', on_delete=django.db.models.deletion.CASCADE
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='ResourcePool',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        primary_key=True, serialize=False, auto_created=True, verbose_name='ID'
                    ),
                ),
                ('name', models.CharField(max_length=64, unique=True)),
                ('description', models.TextField(blank=True, default='')),
                ('vcpu_limit', models.PositiveIntegerField(default=32)),
                ('memory_mib_limit', models.PositiveIntegerField(default=65536)),
                ('disk_gib_limit', models.PositiveIntegerField(default=1024)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'cluster',
                    models.ForeignKey(
                        to='infrastructure.cluster',
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='pools',
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='PoolInstance',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        primary_key=True, serialize=False, auto_created=True, verbose_name='ID'
                    ),
                ),
                (
                    'pool',
                    models.ForeignKey(
                        to='infrastructure.resourcepool',
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='members',
                    ),
                ),
                (
                    'instance',
                    models.OneToOneField(
                        to='instances.instance', on_delete=django.db.models.deletion.CASCADE
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='ConsoleConfiguration',
            fields=[
                (
                    'id',
                    models.PositiveSmallIntegerField(
                        primary_key=True, default=1, editable=False, serialize=False
                    ),
                ),
                ('revision', models.PositiveIntegerField(default=1)),
                ('values', models.JSONField(default=dict)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
