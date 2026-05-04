from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import canteen.managers


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('is_superuser', models.BooleanField(default=False, help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('university_id', models.CharField(max_length=32, unique=True)),
                ('full_name', models.CharField(max_length=120)),
                ('role', models.CharField(choices=[('student', 'Student'), ('staff', 'Staff'), ('admin', 'Admin')], default='student', max_length=20)),
                ('is_active', models.BooleanField(default=True)),
                ('is_staff', models.BooleanField(default=False)),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now)),
                ('groups', models.ManyToManyField(blank=True, help_text='The groups this user belongs to.', related_name='user_set', related_query_name='user', to='auth.group', verbose_name='groups')),
                ('user_permissions', models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='user_set', related_query_name='user', to='auth.permission', verbose_name='user permissions')),
            ],
            options={},
            managers=[('objects', canteen.managers.UserManager())],
        ),
        migrations.CreateModel(
            name='Meal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('description', models.CharField(blank=True, max_length=255, null=True)),
                ('price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('active', models.BooleanField(default=True)),
            ],
        ),
        migrations.CreateModel(
            name='FraudAlert',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('alert_type', models.CharField(max_length=80)),
                ('severity', models.CharField(default='medium', max_length=20)),
                ('detail', models.TextField()),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
            ],
        ),
        migrations.CreateModel(
            name='PickupSlot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slot_date', models.DateField(db_index=True)),
                ('start_time', models.TimeField()),
                ('end_time', models.TimeField()),
                ('capacity', models.IntegerField()),
            ],
            options={'unique_together': {('slot_date', 'start_time', 'end_time')}},
        ),
        migrations.CreateModel(
            name='Wallet',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(default='active', max_length=20)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='wallet', to='canteen.user')),
            ],
        ),
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_ref', models.CharField(db_index=True, max_length=64, unique=True)),
                ('quantity', models.IntegerField(default=1)),
                ('total_amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('status', models.CharField(choices=[('paid', 'Paid'), ('served', 'Served'), ('cancelled', 'Cancelled')], default='paid', max_length=20)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('meal', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='canteen.meal')),
                ('slot', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='canteen.pickupslot')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='canteen.user')),
            ],
        ),
        migrations.CreateModel(
            name='PaymentTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tx_id', models.CharField(db_index=True, max_length=64, unique=True)),
                ('provider', models.CharField(max_length=40)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('succeeded', 'Succeeded'), ('failed', 'Failed')], default='pending', max_length=20)),
                ('provider_ref', models.CharField(blank=True, max_length=128, null=True, unique=True)),
                ('callback_verified', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='canteen.user')),
                ('wallet', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='canteen.wallet')),
            ],
        ),
        migrations.CreateModel(
            name='MealTicket',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ticket_id', models.CharField(db_index=True, max_length=64, unique=True)),
                ('token', models.TextField(unique=True)),
                ('qr_svg', models.TextField()),
                ('status', models.CharField(choices=[('issued', 'Issued'), ('redeemed', 'Redeemed'), ('expired', 'Expired')], default='issued', max_length=20)),
                ('expires_at', models.DateTimeField()),
                ('redeemed_at', models.DateTimeField(blank=True, null=True)),
                ('order', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='canteen.order')),
            ],
        ),
        migrations.CreateModel(
            name='IdempotencyKey',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('endpoint', models.CharField(max_length=120)),
                ('idem_key', models.CharField(max_length=120)),
                ('response_body', models.JSONField()),
                ('status_code', models.IntegerField(default=200)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='canteen.user')),
            ],
            options={'unique_together': {('user', 'endpoint', 'idem_key')}},
        ),
        migrations.CreateModel(
            name='DailyDemandSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('snapshot_date', models.DateField(db_index=True)),
                ('orders_count', models.IntegerField()),
                ('meal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='canteen.meal')),
            ],
        ),
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(max_length=80)),
                ('entity', models.CharField(max_length=80)),
                ('entity_id', models.CharField(max_length=80)),
                ('detail', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('actor_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='canteen.user')),
            ],
        ),
        migrations.CreateModel(
            name='WalletLedgerEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tx_id', models.CharField(db_index=True, max_length=64, unique=True)),
                ('entry_type', models.CharField(choices=[('credit', 'Credit'), ('debit', 'Debit')], max_length=20)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('provider', models.CharField(blank=True, max_length=40, null=True)),
                ('note', models.CharField(blank=True, max_length=255, null=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('wallet', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='entries', to='canteen.wallet')),
            ],
        ),
    ]
