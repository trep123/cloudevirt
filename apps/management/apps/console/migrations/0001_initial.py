import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('instances', '0002_instance_vnc_password'),
    ]
    operations = [
        migrations.CreateModel(
            name='ConsoleSession',
            fields=[
                (
                    'id',
                    models.UUIDField(
                        primary_key=True, default=uuid.uuid4, editable=False, serialize=False
                    ),
                ),
                ('login_hash', models.CharField(max_length=64)),
                ('claimed', models.BooleanField(default=False)),
                ('revoked', models.BooleanField(default=False)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'user',
                    models.ForeignKey(
                        to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE
                    ),
                ),
                (
                    'instance',
                    models.ForeignKey(
                        to='instances.instance', on_delete=django.db.models.deletion.PROTECT
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='MediaSource',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        primary_key=True, auto_created=True, serialize=False, verbose_name='ID'
                    ),
                ),
                ('name', models.CharField(max_length=64)),
                ('stream_path', models.CharField(max_length=64)),
                ('enabled', models.BooleanField(default=True)),
                (
                    'instance',
                    models.ForeignKey(
                        to='instances.instance', on_delete=django.db.models.deletion.PROTECT
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='MediaSession',
            fields=[
                (
                    'id',
                    models.UUIDField(
                        primary_key=True, default=uuid.uuid4, editable=False, serialize=False
                    ),
                ),
                ('login_hash', models.CharField(max_length=64)),
                ('upstream_resource', models.CharField(max_length=1024, blank=True, default='')),
                ('closed', models.BooleanField(default=False)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'user',
                    models.ForeignKey(
                        to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE
                    ),
                ),
                (
                    'source',
                    models.ForeignKey(
                        to='console.mediasource', on_delete=django.db.models.deletion.PROTECT
                    ),
                ),
            ],
        ),
    ]
