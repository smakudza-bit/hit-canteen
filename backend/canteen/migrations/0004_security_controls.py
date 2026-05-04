from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('canteen', '0003_user_email_verification'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='is_suspended',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='user',
            name='suspended_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='DailyReconciliationReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report_date', models.DateField(db_index=True, unique=True)),
                ('payments_received', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('paid_orders_total', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('meals_collected_total', models.IntegerField(default=0)),
                ('successful_payments_count', models.IntegerField(default=0)),
                ('paid_orders_count', models.IntegerField(default=0)),
                ('served_orders_count', models.IntegerField(default=0)),
                ('discrepancy_amount', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(default=django.utils.timezone.now)),
            ],
        ),
    ]