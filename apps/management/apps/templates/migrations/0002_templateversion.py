import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('templates', '0001_initial')]
    operations = [
        migrations.CreateModel(
            name='TemplateVersion',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name='ID'
                    ),
                ),
                ('version', models.PositiveIntegerField()),
                ('configuration', models.JSONField(default=dict)),
                ('constraints', models.JSONField(default=dict)),
                ('published', models.BooleanField(default=False)),
                ('image_checksum', models.CharField(max_length=64, blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'template',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='versions',
                        to='templates.template',
                    ),
                ),
            ],
            options={
                'constraints': [
                    models.UniqueConstraint(
                        fields=('template', 'version'), name='unique_template_version'
                    )
                ]
            },
        )
    ]
