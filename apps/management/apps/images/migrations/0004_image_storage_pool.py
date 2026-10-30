import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('images', '0003_image_supports_cloud_init'),
        ('infrastructure', '0003_managedstoragepool'),
    ]
    operations = [
        migrations.RemoveConstraint(model_name='image', name='uniq_image_path_when_active'),
        migrations.AddField(
            model_name='image',
            name='storage_pool',
            field=models.ForeignKey(
                to='infrastructure.managedstoragepool',
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='images',
            ),
        ),
        migrations.AddConstraint(
            model_name='image',
            constraint=models.UniqueConstraint(
                fields=['node', 'storage_pool', 'relative_path'],
                condition=models.Q(is_deleted=False, storage_pool__isnull=False),
                name='uniq_image_path_when_active',
            ),
        ),
        migrations.AddConstraint(
            model_name='image',
            constraint=models.UniqueConstraint(
                fields=['node', 'relative_path'],
                condition=models.Q(is_deleted=False, storage_pool__isnull=True, node__isnull=False),
                name='uniq_legacy_node_image_path',
            ),
        ),
        migrations.AddConstraint(
            model_name='image',
            constraint=models.UniqueConstraint(
                fields=['relative_path'],
                condition=models.Q(is_deleted=False, storage_pool__isnull=True, node__isnull=True),
                name='uniq_unbound_image_path',
            ),
        ),
    ]
