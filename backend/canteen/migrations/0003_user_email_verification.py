from django.db import migrations, models
import django.utils.timezone
import canteen.models


def populate_unique_verification_tokens(apps, schema_editor):
    User = apps.get_model('canteen', 'User')
    for user in User.objects.all():
        user.email_verification_token = canteen.models.generate_verification_token()
        user.save(update_fields=['email_verification_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('canteen', '0002_alter_user_groups'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='email_verification_sent_at',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name='user',
            name='email_verification_token',
            field=models.CharField(db_index=True, max_length=64, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='user',
            name='is_email_verified',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(populate_unique_verification_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='user',
            name='email_verification_token',
            field=models.CharField(db_index=True, default=canteen.models.generate_verification_token, max_length=64, unique=True),
        ),
    ]
