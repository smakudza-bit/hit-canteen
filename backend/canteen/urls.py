from django.urls import path
from . import views

urlpatterns = [
    path('healthz', views.healthz),
    path('auth/register', views.register_user),
    path('auth/register-student', views.register_user),
    path('auth/check-availability', views.check_account_availability),
    path('auth/verify-email/<str:uidb64>/<str:token>', views.verify_email),
    path('auth/login', views.login),
    path('auth/suspend-self', views.suspend_self),
    path('auth/me', views.auth_me),
    path('auth/me/update', views.update_profile),
    path('auth/change-password', views.change_password),
    path('wallet', views.wallet_detail),
    path('wallet/ledger', views.wallet_ledger),
    path('admin/students/lookup', views.student_lookup_by_id),
    path('admin/cash-deposits', views.cash_deposits),
    path('wallet/topup/initiate', views.topup_initiate),
    path('transactions/history', views.transaction_history),
    path('notifications/history', views.notification_history),
    path('notifications/send-email', views.send_notification_email_view),
    path('notifications/send-work-alert', views.send_work_alert),
    path('payments/webhook/<str:provider>', views.payment_webhook),
    path('payments/paynow/result', views.paynow_result),
    path('payments/dev/simulate-success/<str:tx_id>', views.simulate_payment_success),
    path('menu', views.menu),
    path('menu/<int:meal_id>', views.manage_meal),
    path('pickup-slots', views.pickup_slots),
    path('orders', views.create_order),
    path('orders/paynow/initiate', views.initiate_paynow_order_payment),
    path('orders/walkin', views.walkin_order),
    path('orders/<int:order_id>', views.order_detail),
    path('tickets/<int:order_id>', views.ticket_by_order),
    path('tickets/status/<str:ticket_id>', views.ticket_status),
    path('tickets/mine', views.my_tickets),
    path('tickets/validate-scan', views.validate_scan),
    path('collection-orders/active', views.collection_orders_active),
    path('collection-orders/<int:collection_order_id>/serve', views.collection_order_mark_served),
    path('admin/kpis', views.admin_kpis),
    path('admin/students', views.admin_students),
    path('admin/students/<int:user_id>/status', views.admin_student_status),
    path('admin/staff-members', views.admin_staff_members),
    path('admin/food-items', views.admin_food_items),
    path('admin/all-transactions', views.admin_all_transactions),
    path('admin/reports/summary', views.admin_reports_summary),
    path('admin/settings', views.admin_settings),
    path('admin/served-meals', views.served_meals),
    path('admin/reports/revenue', views.revenue_report),
    path('admin/reports/fraud-alerts', views.fraud_report),
    path('admin/reports/demand-forecast', views.demand_forecast),
    path('admin/reports/daily-reconciliation', views.daily_reconciliation),
]








