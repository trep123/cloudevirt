from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('accounts', '0004_account_administration')]

    operations = [
        migrations.CreateModel(
            name='LoginRateBucket',
            fields=[
                ('key', models.CharField(max_length=64, primary_key=True, serialize=False)),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('expires_at', models.DateTimeField(db_index=True)),
            ],
            options={'verbose_name': '登录限流计数'},
        ),
    ]
