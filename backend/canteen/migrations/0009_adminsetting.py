from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('canteen', '0008_paymenttransaction_meta_json_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='AdminSetting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('paynow_integration_id', models.CharField(blank=True, default='', max_length=120)),
                ('paynow_return_url', models.URLField(blank=True, default='')),
                ('smtp_host', models.CharField(blank=True, default='', max_length=255)),
                ('default_from_email', models.EmailField(blank=True, default='', max_length=254)),
                ('qr_expiry_minutes', models.IntegerField(default=30)),
                ('email_alerts_enabled', models.BooleanField(default=True)),
                ('fraud_alerts_enabled', models.BooleanField(default=True)),
                ('session_timeout_minutes', models.IntegerField(default=30)),
                ('updated_at', models.DateTimeField(default=django.utils.timezone.now)),
            ],
        ),
    ]
