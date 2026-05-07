from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
import uuid

from .managers import UserManager


def generate_verification_token():
    return uuid.uuid4().hex


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = (
        ('student', 'Student'),
        ('staff', 'Staff'),
        ('admin', 'Admin'),
    )

    email = models.EmailField(unique=True)
    university_id = models.CharField(max_length=32, unique=True)
    full_name = models.CharField(max_length=120)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    is_email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=64, unique=True, default=generate_verification_token, db_index=True)
    email_verification_sent_at = models.DateTimeField(default=timezone.now)
    is_suspended = models.BooleanField(default=False)
    suspended_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['university_id', 'full_name']

    def __str__(self):
        return self.email


class Wallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    status = models.CharField(max_length=20, default='active')


class WalletLedgerEntry(models.Model):
    ENTRY_CHOICES = (('credit', 'Credit'), ('debit', 'Debit'))
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='entries')
    tx_id = models.CharField(max_length=64, unique=True, db_index=True)
    entry_type = models.CharField(max_length=20, choices=ENTRY_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    provider = models.CharField(max_length=40, null=True, blank=True)
    note = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)


class PaymentTransaction(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('succeeded', 'Succeeded'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    )
    PURPOSE_CHOICES = (('wallet_topup', 'Wallet Top Up'), ('order_payment', 'Order Payment'))

    tx_id = models.CharField(max_length=64, unique=True, db_index=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE)
    provider = models.CharField(max_length=40)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    purpose = models.CharField(max_length=30, choices=PURPOSE_CHOICES, default='wallet_topup')
    meta_json = models.JSONField(default=dict, blank=True)
    provider_ref = models.CharField(max_length=128, unique=True, null=True, blank=True)
    callback_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)


class IdempotencyKey(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    endpoint = models.CharField(max_length=120)
    idem_key = models.CharField(max_length=120)
    response_body = models.JSONField()
    status_code = models.IntegerField(default=200)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('user', 'endpoint', 'idem_key')



class CashDeposit(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="cash_deposits")
    student_identifier = models.CharField(max_length=32, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    cashier = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="processed_cash_deposits")
    timestamp = models.DateTimeField(default=timezone.now)

class Meal(models.Model):
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=255, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.IntegerField(default=50)
    active = models.BooleanField(default=True)


class PickupSlot(models.Model):
    slot_date = models.DateField(db_index=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    capacity = models.IntegerField()

    class Meta:
        unique_together = ('slot_date', 'start_time', 'end_time')


class Order(models.Model):
    STATUS_CHOICES = (('paid', 'Paid'), ('served', 'Served'), ('cancelled', 'Cancelled'))

    order_ref = models.CharField(max_length=64, unique=True, db_index=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    meal = models.ForeignKey(Meal, on_delete=models.PROTECT)
    slot = models.ForeignKey(PickupSlot, on_delete=models.PROTECT)
    quantity = models.IntegerField(default=1)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='paid')
    created_at = models.DateTimeField(default=timezone.now)


class MealTicket(models.Model):
    STATUS_CHOICES = (('issued', 'Issued'), ('scanned', 'Scanned'), ('redeemed', 'Redeemed'), ('expired', 'Expired'))

    ticket_id = models.CharField(max_length=64, unique=True, db_index=True)
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    token = models.TextField(unique=True)
    qr_svg = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='issued')
    expires_at = models.DateTimeField()
    redeemed_at = models.DateTimeField(null=True, blank=True)


class CollectionOrder(models.Model):
    order_number = models.CharField(max_length=16)
    service_date = models.DateField(db_index=True)
    ticket = models.OneToOneField(MealTicket, on_delete=models.CASCADE)
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='collection_orders')
    meal_name = models.CharField(max_length=120)
    meal_type = models.CharField(max_length=80)
    quantity = models.IntegerField(default=1)
    price_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    special_notes = models.CharField(max_length=255, blank=True, default='')
    scanned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='scanned_collection_orders')
    scanned_at = models.DateTimeField(default=timezone.now)
    served_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='served_collection_orders')
    served_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = (('service_date', 'order_number'),)
        ordering = ('-scanned_at',)


class AuditLog(models.Model):
    actor_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=80)
    entity = models.CharField(max_length=80)
    entity_id = models.CharField(max_length=80)
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)


class FraudAlert(models.Model):
    alert_type = models.CharField(max_length=80)
    severity = models.CharField(max_length=20, default='medium')
    detail = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)



class NotificationLog(models.Model):
    CHANNEL_CHOICES = (('email', 'Email'),)
    STATUS_CHOICES = (('pending', 'Pending'), ('sent', 'Sent'), ('failed', 'Failed'))

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    category = models.CharField(max_length=40, default='general')
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='email')
    recipient_email = models.EmailField()
    subject = models.CharField(max_length=180)
    body = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

class DailyDemandSnapshot(models.Model):
    snapshot_date = models.DateField(db_index=True)
    meal = models.ForeignKey(Meal, on_delete=models.CASCADE)
    orders_count = models.IntegerField()


class DailyReconciliationReport(models.Model):
    report_date = models.DateField(unique=True, db_index=True)
    payments_received = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_orders_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    meals_collected_total = models.IntegerField(default=0)
    successful_payments_count = models.IntegerField(default=0)
    paid_orders_count = models.IntegerField(default=0)
    served_orders_count = models.IntegerField(default=0)
    discrepancy_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)


class AdminSetting(models.Model):
    paynow_integration_id = models.CharField(max_length=120, blank=True, default='')
    paynow_return_url = models.URLField(blank=True, default='')
    smtp_host = models.CharField(max_length=255, blank=True, default='')
    default_from_email = models.EmailField(blank=True, default='')
    qr_expiry_minutes = models.IntegerField(default=30)
    email_alerts_enabled = models.BooleanField(default=True)
    fraud_alerts_enabled = models.BooleanField(default=True)
    session_timeout_minutes = models.IntegerField(default=30)
    updated_at = models.DateTimeField(default=timezone.now)





