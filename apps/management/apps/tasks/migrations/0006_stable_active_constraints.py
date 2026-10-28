"""Only normalize equivalent predicate ordering in migration state; existing indexes are unchanged."""

from django.db import migrations, models

ACTIVE = ['CREATING', 'PENDING', 'PREPARING', 'RECONCILING', 'VALIDATING', 'VERIFYING']


class Migration(migrations.Migration):
    dependencies = [('tasks', '0005_infrastructure_task_types')]
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RemoveConstraint(
                    model_name='task', name='uniq_active_task_per_resource'
                ),
                migrations.RemoveConstraint(model_name='task', name='uniq_active_idempotency_key'),
                migrations.AddConstraint(
                    model_name='task',
                    constraint=models.UniqueConstraint(
                        fields=['resource_type', 'resource_id'],
                        condition=models.Q(status__in=ACTIVE),
                        name='uniq_active_task_per_resource',
                    ),
                ),
                migrations.AddConstraint(
                    model_name='task',
                    constraint=models.UniqueConstraint(
                        fields=['idempotency_key'],
                        condition=models.Q(status__in=ACTIVE) & ~models.Q(idempotency_key=''),
                        name='uniq_active_idempotency_key',
                    ),
                ),
            ],
        )
    ]
