from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone

from .models import (
    AuditLog,
    FraudAlert,
    IdempotencyKey,
    Meal,
    MealTicket,
    Order,
    PaymentTransaction,
    PickupSlot,
    User,
    Wallet,
    WalletLedgerEntry,
)


def _request_role(request):
    if request.user.is_superuser:
        return 'admin'
    return getattr(request.user, 'role', None)


class RoleRestrictedAdmin(admin.ModelAdmin):
    allowed_roles = ('admin',)

    def _is_allowed(self, request):
        return request.user.is_active and request.user.is_staff and _request_role(request) in self.allowed_roles

    def has_module_permission(self, request):
        return self._is_allowed(request)

    def has_view_permission(self, request, obj=None):
        return self._is_allowed(request)

    def has_change_permission(self, request, obj=None):
        return self._is_allowed(request)

    def has_add_permission(self, request):
        return self._is_allowed(request)

    def has_delete_permission(self, request, obj=None):
        return self._is_allowed(request)


@admin.register(User)
class UserAdmin(RoleRestrictedAdmin, BaseUserAdmin):
    allowed_roles = ('admin',)
    list_display = ('id', 'email', 'university_id', 'role', 'is_staff', 'is_active')
    ordering = ('id',)
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('full_name', 'university_id', 'role')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'full_name', 'university_id', 'role', 'password1', 'password2', 'is_staff', 'is_active'),
        }),
    )
    search_fields = ('email', 'university_id', 'full_name')


@admin.register(Meal)
class MealAdmin(RoleRestrictedAdmin):
    allowed_roles = ('admin', 'staff')
    list_display = ('id', 'name', 'price', 'active')
    list_filter = ('active',)
    search_fields = ('name',)


@admin.register(PickupSlot)
class PickupSlotAdmin(RoleRestrictedAdmin):
    allowed_roles = ('admin', 'staff')
    list_display = ('id', 'slot_date', 'start_time', 'end_time', 'capacity')
    list_filter = ('slot_date',)


@admin.register(Order)
class OrderAdmin(RoleRestrictedAdmin):
    allowed_roles = ('admin', 'staff')
    list_display = ('id', 'order_ref', 'user', 'meal', 'quantity', 'total_amount', 'status', 'created_at')
    list_filter = ('status', 'meal', 'slot__slot_date', 'created_at')
    search_fields = ('order_ref', 'user__email', 'user__university_id')


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(RoleRestrictedAdmin):
    allowed_roles = ('admin',)
    list_display = ('tx_id', 'user', 'provider', 'amount', 'status', 'callback_verified', 'created_at')
    list_filter = ('provider', 'status', 'callback_verified', 'created_at')
    search_fields = ('tx_id', 'provider_ref', 'user__email', 'user__university_id')
    readonly_fields = ('tx_id', 'user', 'wallet', 'provider', 'amount', 'status', 'provider_ref', 'callback_verified', 'created_at', 'updated_at')
    change_list_template = 'admin/canteen/paymenttransaction/change_list.html'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('finance-dashboard/', self.admin_site.admin_view(self.finance_dashboard), name='canteen_finance_dashboard'),
        ]
        return custom + urls

    def finance_dashboard(self, request):
        if _request_role(request) != 'admin':
            raise PermissionDenied('Only admins can view finance dashboard')

        paid_orders = Order.objects.filter(status__in=['paid', 'served'])
        revenue_total = paid_orders.aggregate(total=Sum('total_amount'))['total'] or 0
        topup_total = WalletLedgerEntry.objects.filter(entry_type='credit').aggregate(total=Sum('amount'))['total'] or 0
        pending_payments = PaymentTransaction.objects.filter(status='pending').count()
        failed_payments = PaymentTransaction.objects.filter(status='failed').count()

        context = {
            **self.admin_site.each_context(request),
            'title': 'Finance Dashboard',
            'revenue_total': revenue_total,
            'topup_total': topup_total,
            'pending_payments': pending_payments,
            'failed_payments': failed_payments,
            'today': timezone.now(),
            'back_url': reverse('admin:canteen_paymenttransaction_changelist'),
        }
        return TemplateResponse(request, 'admin/canteen/finance_dashboard.html', context)


@admin.register(FraudAlert)
class FraudAlertAdmin(RoleRestrictedAdmin):
    allowed_roles = ('admin', 'staff')
    list_display = ('id', 'alert_type', 'severity', 'created_at')
    list_filter = ('severity', 'alert_type', 'created_at')
    search_fields = ('alert_type', 'detail')
    readonly_fields = ('alert_type', 'severity', 'detail', 'created_at')
    change_list_template = 'admin/canteen/fraudalert/change_list.html'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('fraud-dashboard/', self.admin_site.admin_view(self.fraud_dashboard), name='canteen_fraud_dashboard'),
        ]
        return custom + urls

    def fraud_dashboard(self, request):
        if _request_role(request) not in ('admin', 'staff'):
            raise PermissionDenied('Only staff/admin can view fraud dashboard')

        total_alerts = FraudAlert.objects.count()
        high_severity = FraudAlert.objects.filter(severity='high').count()
        duplicate_scans = FraudAlert.objects.filter(alert_type='duplicate_scan').count()
        invalid_signatures = FraudAlert.objects.filter(alert_type__icontains='signature').count()

        context = {
            **self.admin_site.each_context(request),
            'title': 'Fraud Dashboard',
            'total_alerts': total_alerts,
            'high_severity': high_severity,
            'duplicate_scans': duplicate_scans,
            'invalid_signatures': invalid_signatures,
            'today': timezone.now(),
            'back_url': reverse('admin:canteen_fraudalert_changelist'),
        }
        return TemplateResponse(request, 'admin/canteen/fraud_dashboard.html', context)


@admin.register(Wallet)
class WalletAdmin(RoleRestrictedAdmin):
    allowed_roles = ('admin',)
    list_display = ('id', 'user', 'status')
    search_fields = ('user__email', 'user__university_id')


@admin.register(WalletLedgerEntry)
class WalletLedgerEntryAdmin(RoleRestrictedAdmin):
    allowed_roles = ('admin',)
    list_display = ('tx_id', 'wallet', 'entry_type', 'amount', 'provider', 'created_at')
    list_filter = ('entry_type', 'provider', 'created_at')
    search_fields = ('tx_id', 'wallet__user__email', 'wallet__user__university_id')
    readonly_fields = ('wallet', 'tx_id', 'entry_type', 'amount', 'provider', 'note', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MealTicket)
class MealTicketAdmin(RoleRestrictedAdmin):
    allowed_roles = ('admin', 'staff')
    list_display = ('ticket_id', 'order', 'status', 'expires_at', 'redeemed_at')
    list_filter = ('status', 'expires_at')
    search_fields = ('ticket_id', 'order__order_ref', 'order__user__email')
    readonly_fields = ('ticket_id', 'order', 'token', 'qr_svg', 'status', 'expires_at', 'redeemed_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditLog)
class AuditLogAdmin(RoleRestrictedAdmin):
    allowed_roles = ('admin',)
    list_display = ('id', 'actor_user', 'action', 'entity', 'entity_id', 'created_at')
    list_filter = ('action', 'entity', 'created_at')
    search_fields = ('action', 'entity', 'entity_id', 'detail', 'actor_user__email')
    readonly_fields = ('actor_user', 'action', 'entity', 'entity_id', 'detail', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(RoleRestrictedAdmin):
    allowed_roles = ('admin',)
    list_display = ('id', 'user', 'endpoint', 'idem_key', 'status_code', 'created_at')
    list_filter = ('endpoint', 'status_code', 'created_at')
    search_fields = ('user__email', 'endpoint', 'idem_key')
    readonly_fields = ('user', 'endpoint', 'idem_key', 'response_body', 'status_code', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
