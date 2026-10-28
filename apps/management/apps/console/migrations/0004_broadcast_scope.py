from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('console', '0003_user_workspaces')]

    operations = [
        migrations.AddConstraint(
            model_name='broadcast',
            constraint=models.CheckConstraint(
                condition=models.Q(instance__isnull=True, kind='page', workspace__isnull=False)
                | models.Q(
                    instance__isnull=False, kind__in=['desktop', 'source'], workspace__isnull=True
                ),
                name='broadcast_scope_matches_kind',
            ),
        ),
    ]
