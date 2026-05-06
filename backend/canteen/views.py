import json
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

from django.conf import settings
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from django.db import IntegrityError, transaction, models
from django.db.models import Sum
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate

DEMO_PASSWORD = 'Demo@1234'
DEMO_EMAILS = {'student@hit.ac.zw', 'staff@hit.ac.zw', 'admin@hit.ac.zw'}

from .models import AdminSetting, AuditLog, CashDeposit, DailyReconciliationReport, FraudAlert, Meal, MealTicket, NotificationLog, Order, PaymentTransaction, PickupSlot, User, Wallet, WalletLedgerEntry
from .serializers import AdminSettingsSerializer, LoginSerializer, NotificationEmailSerializer, OrderCreateSerializer, PasswordChangeSerializer, PaynowOrderInitiateSerializer, PaymentWebhookSerializer, ProfileUpdateSerializer, RegisterSerializer, ScanSerializer, TopUpInitiateSerializer
from .tokens import email_verification_token
from .utils import PAYNOW_FAILURE_STATUSES, PAYNOW_SUCCESS_STATUSES, add_audit, add_fraud_alert, cache_idempotency_response, create_ticket, demand_forecast_for_date, estimated_wait_minutes, gen_tx_id, get_cached_idempotency, notify_work_email, parse_paynow_message, paynow_error_message, paynow_initiate, paynow_poll_status, paynow_validate_hash, send_notification_email, slot_booked_qty, verify_ticket_payload, verify_webhook_signature, wallet_balance


def _client_context(request):
    return f"ip={request.META.get('REMOTE_ADDR', '')}, ua={request.META.get('HTTP_USER_AGENT', '')[:120]}"


def _token_payload(user):
    try:
        refresh = RefreshToken.for_user(user)
        refresh['role'] = user.role
        return {
            'access_token': str(refresh.access_token),
            'refresh_token': str(refresh),
            'token_type': 'bearer',
            'role': user.role,
            'email_verified': user.is_email_verified,
            'is_suspended': user.is_suspended,
        }
    except Exception as err:
        raise RuntimeError(f'Token generation failed: {err}')


def _require_role(request, *roles):
    if request.user.role not in roles:
        return Response({'detail': 'Insufficient role'}, status=status.HTTP_403_FORBIDDEN)
    return None


def _ensure_not_suspended(user):
    if getattr(user, 'is_suspended', False):
        return Response({'detail': 'Account is suspended. Contact support or administration.'}, status=status.HTTP_403_FORBIDDEN)
    return None


def _safe_send_user_email(user, subject, body, category):
    if not getattr(user, 'email', ''):
        return None
    return send_notification_email(user.email, subject, body, category=category, user=user)


def _masked_phone(phone_number):
    digits = ''.join(ch for ch in str(phone_number or '') if ch.isdigit())
    if len(digits) <= 4:
        return digits
    return ('*' * max(0, len(digits) - 4)) + digits[-4:]


def _paynow_callback_urls(request, return_path='/student/'):
    result_url = (getattr(settings, 'PAYNOW_RESULT_URL', '') or '').strip()
    return_url = (getattr(settings, 'PAYNOW_RETURN_URL', '') or '').strip()
    if not result_url:
        result_url = request.build_absolute_uri('/api/v1/payments/paynow/result')
    if not return_url:
        return_url = request.build_absolute_uri(return_path)
    return result_url, return_url

def _validate_public_paynow_urls(result_url, return_url):
    local_hosts = {'127.0.0.1', 'localhost'}
    result_host = (urlparse(result_url).hostname or '').lower()
    return_host = (urlparse(return_url).hostname or '').lower()
    if result_host in local_hosts or return_host in local_hosts:
        raise ValueError(
            'Paynow requires public callback URLs. Replace localhost/127.0.0.1 with your ngrok URL in PAYNOW_RESULT_URL and PAYNOW_RETURN_URL, then restart Django.'
        )


def _default_admin_settings_data():
    return {
        'paynow_integration_id': '',
        'paynow_return_url': '',
        'smtp_host': 'smtp.gmail.com',
        'default_from_email': 'smakudza@gmail.com',
        'qr_expiry_minutes': 30,
        'email_alerts_enabled': True,
        'fraud_alerts_enabled': True,
        'session_timeout_minutes': 30,
    }


def _admin_settings_fallback_path():
    return Path(__file__).resolve().parent / 'admin_settings_store.json'


def _load_admin_settings_fallback():
    path = _admin_settings_fallback_path()
    data = _default_admin_settings_data()
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(stored, dict):
                data.update(stored)
        except Exception:
            pass
    return data


def _save_admin_settings_fallback(data):
    path = _admin_settings_fallback_path()
    payload = _default_admin_settings_data()
    payload.update(data)
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def _meal_image_store_path():
    return Path(__file__).resolve().parent / 'meal_images_store.json'


def _load_meal_images():
    path = _meal_image_store_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_meal_images(data):
    path = _meal_image_store_path()
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')


def _get_meal_image(meal_id):
    return str(_load_meal_images().get(str(meal_id), '') or '')


def _set_meal_image(meal_id, image_data):
    data = _load_meal_images()
    key = str(meal_id)
    if image_data:
        data[key] = str(image_data)
    else:
        data.pop(key, None)
    _save_meal_images(data)


def _admin_settings():
    settings_obj, _ = AdminSetting.objects.get_or_create(
        pk=1,
        defaults={
            'smtp_host': 'smtp.gmail.com',
            'default_from_email': 'smakudza@gmail.com',
            'qr_expiry_minutes': 30,
            'email_alerts_enabled': True,
            'fraud_alerts_enabled': True,
            'session_timeout_minutes': 30,
        },
    )
    return settings_obj


def _build_verification_url(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    return request.build_absolute_uri(f"/api/v1/auth/verify-email/{uid}/{token}")


def _ensure_demo_user(*, email, password, university_id, full_name, role, is_staff):
    user = User.objects.filter(email=email).first()
    if not user:
        user = User.objects.create_user(
            email=email,
            password=password,
            university_id=university_id,
            full_name=full_name,
            role=role,
            is_staff=is_staff,
        )
    updated_fields = []
    if not user.is_email_verified:
        user.is_email_verified = True
        updated_fields.append('is_email_verified')
    if user.is_suspended:
        user.is_suspended = False
        updated_fields.append('is_suspended')
    if user.suspended_at is not None:
        user.suspended_at = None
        updated_fields.append('suspended_at')
    if updated_fields:
        user.save(update_fields=updated_fields)
    Wallet.objects.get_or_create(user=user)
    return user


def _ensure_seed_data():
    if not Meal.objects.exists():
        Meal.objects.bulk_create([
            Meal(name='Sadza + Beef Stew', description='Traditional meal', price=Decimal('2.50')),
            Meal(name='Rice + Chicken', description='Rice with grilled chicken', price=Decimal('3.00')),
            Meal(name='Veggie Plate', description='Healthy vegetarian option', price=Decimal('2.20')),
            Meal(name='Mazoe Orange', description='Fruit drink', price=Decimal('1.10')),
            Meal(name='Water 500ml', description='Still water', price=Decimal('0.80')),
        ])
    if not PickupSlot.objects.filter(slot_date=date.today()).exists():
        PickupSlot.objects.bulk_create([
            PickupSlot(slot_date=date.today(), start_time=time(13, 0), end_time=time(13, 30), capacity=100),
            PickupSlot(slot_date=date.today(), start_time=time(17, 0), end_time=time(17, 30), capacity=100),
        ])
    for seed in [
        {'email': 'admin@hit.ac.zw', 'password': DEMO_PASSWORD, 'university_id': 'HITADMIN001', 'full_name': 'System Admin', 'role': 'admin', 'is_staff': True},
        {'email': 'staff@hit.ac.zw', 'password': DEMO_PASSWORD, 'university_id': 'HITSTAFF001', 'full_name': 'Canteen Staff', 'role': 'staff', 'is_staff': True},
        {'email': 'student@hit.ac.zw', 'password': DEMO_PASSWORD, 'university_id': 'HITSTUDENT001', 'full_name': 'Demo Student', 'role': 'student', 'is_staff': False},
    ]:
        _ensure_demo_user(**seed)


def _apply_successful_topup(tx, provider_ref, provider_note, verified=True):
    first_success = not WalletLedgerEntry.objects.filter(tx_id=tx.tx_id).exists()
    if first_success:
        WalletLedgerEntry.objects.create(wallet=tx.wallet, tx_id=tx.tx_id, entry_type='credit', amount=tx.amount, provider=tx.provider, note=provider_note)
    tx.status = 'succeeded'
    tx.callback_verified = verified
    if provider_ref:
        tx.provider_ref = provider_ref[:128]
    tx.updated_at = timezone.now()
    tx.save(update_fields=['status', 'callback_verified', 'provider_ref', 'updated_at'])
    if first_success:
        _safe_send_user_email(
            tx.user,
            'HIT Canteen wallet top-up confirmed',
            f'Hello {tx.user.full_name},\n\nYour wallet top-up of ${tx.amount:.2f} has been confirmed through {tx.provider}.\nTransaction ID: {tx.tx_id}\nReference: {tx.provider_ref or provider_ref or "pending"}\n\nYour wallet is ready for canteen orders.',
            'wallet_topup_confirmation',
        )



def _ticket_payload(order, ticket):
    return {
        'order_id': order.id,
        'order_ref': order.order_ref,
        'status': order.status,
        'ticket_id': ticket.ticket_id,
        'ticket_token': ticket.token,
        'ticket_qr_svg': ticket.qr_svg,
        'expires_at': ticket.expires_at.isoformat(),
    }


def _create_paid_order_ticket(user, meal, slot, quantity):
    total_amount = meal.price * quantity
    meal.stock_quantity = max(0, meal.stock_quantity - quantity)
    meal.save(update_fields=['stock_quantity'])
    order = Order.objects.create(
        order_ref=gen_tx_id('ORD'),
        user=user,
        meal=meal,
        slot=slot,
        quantity=quantity,
        total_amount=total_amount,
        status='paid',
    )
    token, qr_svg, expires_at = create_ticket(order.id, user.id, slot.id)
    ticket = MealTicket.objects.create(
        ticket_id=gen_tx_id('TKT'),
        order=order,
        token=token,
        qr_svg=qr_svg,
        expires_at=expires_at,
    )
    return order, ticket


def _apply_successful_order_payment(tx, provider_ref, verified=True):
    meta = tx.meta_json or {}
    if meta.get('fulfilled'):
        tx.status = 'succeeded'
        tx.callback_verified = verified
        if provider_ref:
            tx.provider_ref = provider_ref[:128]
        tx.updated_at = timezone.now()
        tx.save(update_fields=['status', 'callback_verified', 'provider_ref', 'updated_at'])
        return

    slot_id = meta.get('slot_id')
    items = meta.get('items') or []
    slot = PickupSlot.objects.filter(id=slot_id).first()
    if not slot or not items:
        _apply_successful_topup(tx, provider_ref, 'Paynow payment settled as wallet credit because the order payload was incomplete.', verified=verified)
        meta['wallet_credited'] = True
        meta['fallback_reason'] = 'missing_slot_or_items'
        tx.meta_json = meta
        tx.save(update_fields=['meta_json'])
        return

    meals = {meal.id: meal for meal in Meal.objects.filter(id__in=[item.get('meal_id') for item in items], active=True)}
    booked_total = sum(int(item.get('quantity') or 0) for item in items)
    if slot_booked_qty(slot) + booked_total > slot.capacity:
        _apply_successful_topup(tx, provider_ref, 'Paynow payment settled as wallet credit because the selected pickup slot became full.', verified=verified)
        meta['wallet_credited'] = True
        meta['fallback_reason'] = 'slot_full'
        tx.meta_json = meta
        tx.save(update_fields=['meta_json'])
        return

    for item in items:
        meal = meals.get(item.get('meal_id'))
        quantity = int(item.get('quantity') or 0)
        if not meal or quantity < 1 or meal.stock_quantity < quantity:
            _apply_successful_topup(tx, provider_ref, 'Paynow payment settled as wallet credit because one of the selected meals is no longer available.', verified=verified)
            meta['wallet_credited'] = True
            meta['fallback_reason'] = 'meal_unavailable'
            tx.meta_json = meta
            tx.save(update_fields=['meta_json'])
            return

    created_orders = []
    with transaction.atomic():
        slot = PickupSlot.objects.select_for_update().get(id=slot.id)
        if slot_booked_qty(slot) + booked_total > slot.capacity:
            raise ValueError('Pickup slot became full before payment confirmation.')
        meals = {meal.id: meal for meal in Meal.objects.select_for_update().filter(id__in=meals.keys(), active=True)}
        for item in items:
            meal = meals[item['meal_id']]
            quantity = int(item['quantity'])
            if meal.stock_quantity < quantity:
                raise ValueError(f'{meal.name} is no longer available in the requested quantity.')
            order, ticket = _create_paid_order_ticket(tx.user, meal, slot, quantity)
            created_orders.append(_ticket_payload(order, ticket))

    tx.status = 'succeeded'
    tx.callback_verified = verified
    if provider_ref:
        tx.provider_ref = provider_ref[:128]
    meta['fulfilled'] = True
    meta['created_orders'] = created_orders
    tx.meta_json = meta
    tx.updated_at = timezone.now()
    tx.save(update_fields=['status', 'callback_verified', 'provider_ref', 'meta_json', 'updated_at'])
    add_audit(tx.user, 'paynow_order_fulfilled', 'payment_transaction', tx.tx_id, f'orders={len(created_orders)}')
    _safe_send_user_email(
        tx.user,
        'HIT Canteen Paynow order confirmed',
        f'Hello {tx.user.full_name},\n\nYour Paynow payment of ${tx.amount:.2f} has been confirmed and your order is now ready in the portal. Open the student portal to view your QR ticket(s).',
        'order_confirmation',
    )


def _refresh_pending_paynow_transaction(tx):
    if tx.provider != 'online_payment' or tx.status != 'pending':
        return tx
    meta = tx.meta_json or {}
    poll_url = (meta.get('pollurl') or '').strip()
    if not poll_url:
        return tx
    try:
        polled = paynow_poll_status(poll_url)
    except Exception as err:
        add_fraud_alert('paynow_poll_failure', 'low', f"tx={tx.tx_id}, detail={err}")
        return tx

    status_text = (polled.get('status') or '').strip().lower()
    provider_ref = polled.get('paynowreference', '') or tx.provider_ref
    if status_text in PAYNOW_SUCCESS_STATUSES:
        if tx.purpose == 'order_payment':
            _apply_successful_order_payment(tx, provider_ref, verified=True)
        else:
            _apply_successful_topup(tx, provider_ref, 'Paynow confirmed top-up', verified=True)
        tx.refresh_from_db()
    elif status_text in PAYNOW_FAILURE_STATUSES:
        tx.status = 'failed'
        tx.callback_verified = True
        tx.provider_ref = (provider_ref or '')[:128] or tx.provider_ref
        tx.updated_at = timezone.now()
        tx.save(update_fields=['status', 'callback_verified', 'provider_ref', 'updated_at'])
    return tx


def _build_reconciliation(target_date):
    payments = PaymentTransaction.objects.filter(status='succeeded', created_at__date=target_date)
    paid_orders = Order.objects.filter(status__in=['paid', 'served'], created_at__date=target_date)
    served_orders = Order.objects.filter(status='served', created_at__date=target_date)
    payments_total = payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    orders_total = paid_orders.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    served_count = served_orders.count()
    notes = []
    if payments_total != orders_total:
        notes.append('Payment total does not match paid order total.')
    if paid_orders.count() < served_count:
        notes.append('More served orders than paid orders detected.')
    report, _ = DailyReconciliationReport.objects.update_or_create(
        report_date=target_date,
        defaults={
            'payments_received': payments_total,
            'paid_orders_total': orders_total,
            'meals_collected_total': served_count,
            'successful_payments_count': payments.count(),
            'paid_orders_count': paid_orders.count(),
            'served_orders_count': served_count,
            'discrepancy_amount': payments_total - orders_total,
            'notes': ' '.join(notes),
            'updated_at': timezone.now(),
        },
    )
    return report


def _flag_duplicate_provider_ref(provider_ref, tx_id):
    if not provider_ref:
        return
    if PaymentTransaction.objects.filter(provider_ref=provider_ref).exclude(tx_id=tx_id).exists():
        add_fraud_alert('duplicate_payment_reference', 'high', f"provider_ref={provider_ref}, tx_id={tx_id}")


def _flag_repeated_failed_scans(request):
    window_start = timezone.now() - timedelta(minutes=10)
    recent_failures = FraudAlert.objects.filter(
        alert_type__in=['invalid_ticket_signature', 'missing_ticket_record', 'duplicate_ticket_scan', 'expired_ticket_scan'],
        created_at__gte=window_start,
        detail__icontains=request.user.email,
    ).count()
    if recent_failures >= 3:
        add_fraud_alert('repeated_failed_scans', 'high', f"scanner={request.user.email}, failures_last_10m={recent_failures}, {_client_context(request)}")


def _flag_rapid_ordering(user, request):
    window_start = timezone.now() - timedelta(minutes=5)
    recent_orders = Order.objects.filter(user=user, created_at__gte=window_start).count()
    if recent_orders >= 5:
        add_fraud_alert('rapid_ordering_pattern', 'medium', f"user={user.email}, orders_last_5m={recent_orders}, {_client_context(request)}")


@api_view(['GET'])
@permission_classes([AllowAny])
def healthz(_request):
    _ensure_seed_data()
    return Response({'status': 'ok'})


@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    try:
        _ensure_seed_data()
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        errors = {}
        if User.objects.filter(email=data['email']).exists():
            errors['email'] = ['This HIT email is already registered.']
        if User.objects.filter(university_id=data['university_id']).exists():
            errors['university_id'] = ['This university ID is already in use.']
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.create_user(
            email=data['email'],
            password=data['password'],
            university_id=data['university_id'],
            full_name=data['full_name'],
            role=data['role'],
            is_staff=data['role'] in {'staff', 'admin'},
        )
        Wallet.objects.create(user=user)

        verification_url = _build_verification_url(request, user)
        plain_body = (
            f"Hello {user.full_name},\n\n"
            f"Welcome to the HIT Canteen system. Please verify your account using the link below before logging in:\n"
            f"{verification_url}\n\n"
            f"If you did not request this account, please ignore this email."
        )
        html_body = render_to_string(
            'emails/verify_email.html',
            {
                'user': user,
                'verify_url': verification_url,
            },
        )

        add_audit(user, 'register_user', 'user', user.id, f"role={user.role}, {_client_context(request)}")
        send_notification_email(
            user.email,
            'Verify your HIT Canteen account',
            plain_body,
            category='registration_confirmation',
            user=user,
            html_body=html_body,
        )
        notify_work_email(
            subject='New HIT Canteen registration',
            body=f'User: {user.full_name}\nEmail: {user.email}\nRole: {user.role}\nUniversity ID: {user.university_id}',
            category='registration_alert',
            user=user,
        )
        return Response(
            {
                'detail': 'Registration created. Verify the HIT email before login.',
                'verification_required': True,
                'verification_url': verification_url,
            },
            status=status.HTTP_201_CREATED,
        )
    except IntegrityError:
        fallback_errors = {}
        email = (request.data.get('email') or '').strip().lower()
        university_id = (request.data.get('university_id') or '').strip()
        if email and User.objects.filter(email=email).exists():
            fallback_errors['email'] = ['This HIT email is already registered.']
        if university_id and User.objects.filter(university_id=university_id).exists():
            fallback_errors['university_id'] = ['This university ID is already in use.']
        if fallback_errors:
            return Response(fallback_errors, status=status.HTTP_400_BAD_REQUEST)
        return Response({'detail': 'A registration integrity error occurred. Please verify the email and university ID and try again.'}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as err:
        return Response({'detail': f'Registration failed on the server: {err}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def check_account_availability(request):
    _ensure_seed_data()
    email = (request.query_params.get('email') or '').strip().lower()
    university_id = (request.query_params.get('university_id') or '').strip()
    response = {}
    if email:
        hit_email = email.endswith('@hit.ac.zw')
        available = hit_email and not User.objects.filter(email=email).exists()
        response['email'] = {
            'value': email,
            'is_hit_email': hit_email,
            'available': available,
            'message': 'Email is available.' if available else ('Only official HIT email addresses can register.' if not hit_email else 'This HIT email is already registered.'),
        }
    if university_id:
        available = not User.objects.filter(university_id=university_id).exists()
        response['university_id'] = {
            'value': university_id,
            'available': available,
            'message': 'University ID is available.' if available else 'This university ID is already in use.',
        }
    return Response(response)


@api_view(['GET'])
@permission_classes([AllowAny])
def verify_email(request, uidb64, token):
    login_path = '/staff-login/'
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
        login_path = '/login/'
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return redirect('/login/?verification=invalid')

    if user.is_email_verified:
        return redirect(f'{login_path}?verification=already')

    if not email_verification_token.check_token(user, token):
        return redirect(f'{login_path}?verification=invalid')

    user.is_email_verified = True
    user.email_verification_sent_at = timezone.now()
    user.save(update_fields=['is_email_verified', 'email_verification_sent_at'])
    add_audit(user, 'verify_email', 'user', user.id, _client_context(request))
    return redirect(f'{login_path}?verification=success')

@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    try:
        _ensure_seed_data()
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email'].strip().lower()
        password = serializer.validated_data['password']
        user = authenticate(request, email=email, password=password)
        if not user and email in DEMO_EMAILS and password == DEMO_PASSWORD:
            user = User.objects.filter(email=email).first()
        if not user:
            return Response({'detail': 'Invalid credentials. For the demo, use the seeded HIT account and the temporary demo password.'}, status=status.HTTP_401_UNAUTHORIZED)
        if user.is_suspended:
            return Response({'detail': 'Account is suspended. Contact support or administration.'}, status=status.HTTP_403_FORBIDDEN)
        if not user.is_email_verified:
            verification_url = _build_verification_url(request, user)
            return Response({'detail': 'Email verification required before login.', 'verification_required': True, 'verification_url': verification_url}, status=status.HTTP_403_FORBIDDEN)
        add_audit(user, 'login', 'user', user.id, _client_context(request))
        return Response(_token_payload(user))
    except Exception as err:
        return Response({'detail': f'Login failed on the server: {err}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def suspend_self(request):
    request.user.is_suspended = True
    request.user.suspended_at = timezone.now()
    request.user.save(update_fields=['is_suspended', 'suspended_at'])
    add_audit(request.user, 'self_suspend', 'user', request.user.id, _client_context(request))
    return Response({'detail': 'Account suspended successfully.'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def wallet_detail(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    wallet = getattr(request.user, 'wallet', None)
    if not wallet:
        return Response({'detail': 'Wallet not found'}, status=status.HTTP_404_NOT_FOUND)
    return Response({'wallet_id': wallet.id, 'balance': float(wallet_balance(wallet)), 'status': wallet.status})



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def student_lookup_by_id(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    role_error = _require_role(request, 'staff', 'admin')
    if role_error:
        return role_error
    student_id = (request.query_params.get('student_id') or '').strip()
    if not student_id:
        return Response({'detail': 'Student ID is required.'}, status=status.HTTP_400_BAD_REQUEST)
    student = User.objects.filter(university_id=student_id, role='student').first()
    if not student:
        return Response({'detail': 'Student account not found.'}, status=status.HTTP_404_NOT_FOUND)
    wallet = Wallet.objects.get_or_create(user=student)[0]
    return Response({
        'student_id': student.university_id,
        'full_name': student.full_name,
        'email': student.email,
        'wallet_balance': float(wallet_balance(wallet)),
    })


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def cash_deposits(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    role_error = _require_role(request, 'staff', 'admin')
    if role_error:
        return role_error

    if request.method == 'GET':
        student_id = (request.query_params.get('student_id') or '').strip()
        deposits = CashDeposit.objects.select_related('student', 'cashier').order_by('-timestamp')
        if student_id:
            deposits = deposits.filter(student_identifier=student_id)
        deposits = deposits[:20]
        return Response([
            {
                'id': deposit.id,
                'student_id': deposit.student_identifier,
                'student_name': deposit.student.full_name,
                'amount': float(deposit.amount),
                'cashier': deposit.cashier.full_name if deposit.cashier else 'Unknown',
                'timestamp': deposit.timestamp.isoformat(),
            }
            for deposit in deposits
        ])

    student_id = (request.data.get('student_id') or '').strip()
    amount_raw = request.data.get('amount')
    if not student_id:
        return Response({'detail': 'Student ID is required.'}, status=status.HTTP_400_BAD_REQUEST)
    if amount_raw in [None, '']:
        return Response({'detail': 'Deposit amount is required.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        amount = Decimal(str(amount_raw))
    except Exception:
        return Response({'detail': 'Enter a valid deposit amount.'}, status=status.HTTP_400_BAD_REQUEST)
    if amount <= 0:
        return Response({'detail': 'Deposits must be greater than zero.'}, status=status.HTTP_400_BAD_REQUEST)

    student = User.objects.filter(university_id=student_id, role='student').first()
    if not student:
        return Response({'detail': 'Student account not found.'}, status=status.HTTP_404_NOT_FOUND)

    wallet, _ = Wallet.objects.get_or_create(user=student)
    with transaction.atomic():
        deposit = CashDeposit.objects.create(
            student=student,
            student_identifier=student.university_id,
            amount=amount,
            cashier=request.user,
        )
        WalletLedgerEntry.objects.create(
            wallet=wallet,
            tx_id=gen_tx_id('CASH'),
            entry_type='credit',
            amount=amount,
            provider='cash_deposit',
            note=f'Cash deposit processed by {request.user.full_name or request.user.email}',
        )

    add_audit(request.user, 'cash_deposit', 'cash_deposit', deposit.id, f'student={student.university_id}, amount={amount}, {_client_context(request)}')
    return Response({
        'detail': 'Deposit successful. Student wallet updated.',
        'student_id': student.university_id,
        'student_name': student.full_name,
        'amount': float(amount),
        'wallet_balance': float(wallet_balance(wallet)),
        'cashier': request.user.full_name or request.user.email,
        'timestamp': deposit.timestamp.isoformat(),
    }, status=status.HTTP_201_CREATED)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def wallet_ledger(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    wallet = getattr(request.user, 'wallet', None)
    if not wallet:
        return Response({'detail': 'Wallet not found'}, status=status.HTTP_404_NOT_FOUND)
    entries = wallet.entries.order_by('-created_at')[:50]
    return Response([{'tx_id': e.tx_id, 'type': e.entry_type, 'amount': float(e.amount), 'provider': e.provider, 'note': e.note, 'created_at': e.created_at.isoformat()} for e in entries])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def transaction_history(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    wallet = getattr(request.user, 'wallet', None)
    if not wallet:
        return Response({'detail': 'Wallet not found'}, status=status.HTTP_404_NOT_FOUND)
    payments = list(PaymentTransaction.objects.filter(user=request.user).order_by('-created_at')[:50])
    for payment in payments:
        if payment.provider in {'online_payment', 'mobile_money', 'bank_card'} and payment.status == 'pending':
            _refresh_pending_paynow_transaction(payment)
    payments = list(PaymentTransaction.objects.filter(user=request.user).order_by('-created_at')[:50])
    orders = Order.objects.filter(user=request.user).select_related('meal', 'slot').order_by('-created_at')[:50]
    ledger = wallet.entries.order_by('-created_at')[:50]
    return Response({
        'payments': [{'tx_id': p.tx_id, 'amount': float(p.amount), 'provider': p.provider, 'status': p.status, 'purpose': p.purpose, 'meta_json': p.meta_json, 'provider_ref': p.provider_ref, 'created_at': p.created_at.isoformat()} for p in payments],
        'orders': [{'order_ref': o.order_ref, 'meal': o.meal.name, 'quantity': o.quantity, 'total_amount': float(o.total_amount), 'status': o.status, 'created_at': o.created_at.isoformat(), 'pickup_slot': f"{o.slot.start_time.strftime('%H:%M')} - {o.slot.end_time.strftime('%H:%M')}"} for o in orders],
        'ledger': [{'tx_id': l.tx_id, 'type': l.entry_type, 'amount': float(l.amount), 'provider': l.provider, 'note': l.note, 'created_at': l.created_at.isoformat()} for l in ledger],
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def notification_history(request):
    role_error = None if request.user.role in {'staff', 'admin'} else 'student'
    logs = NotificationLog.objects.all().order_by('-created_at')[:100] if role_error is None else NotificationLog.objects.filter(user=request.user).order_by('-created_at')[:50]
    return Response([
        {
            'id': item.id,
            'category': item.category,
            'channel': item.channel,
            'recipient_email': item.recipient_email,
            'subject': item.subject,
            'status': item.status,
            'error_message': item.error_message,
            'sent_at': item.sent_at.isoformat() if item.sent_at else None,
            'created_at': item.created_at.isoformat(),
        }
        for item in logs
    ])


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_notification_email_view(request):
    serializer = NotificationEmailSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    recipient = serializer.validated_data.get('recipient_email') or request.user.email
    if recipient != request.user.email and request.user.role not in {'staff', 'admin'}:
        return Response({'detail': 'You can only send test emails to your own account.'}, status=status.HTTP_403_FORBIDDEN)
    notification = send_notification_email(
        recipient,
        serializer.validated_data['subject'],
        serializer.validated_data['body'],
        category=serializer.validated_data.get('category', 'general'),
        user=request.user,
    )
    payload = {
        'id': notification.id,
        'recipient_email': notification.recipient_email,
        'subject': notification.subject,
        'status': notification.status,
        'error_message': notification.error_message,
    }
    status_code = status.HTTP_200_OK if notification.status == 'sent' else status.HTTP_400_BAD_REQUEST
    return Response(payload, status=status_code)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_work_alert(request):
    subject = (request.data.get('subject') or '').strip()
    body = (request.data.get('body') or '').strip()
    if not subject or not body:
        return Response({'detail': 'Subject and body are required.'}, status=status.HTTP_400_BAD_REQUEST)
    if request.user.role not in {'staff', 'admin'}:
        return Response({'detail': 'Only staff or admin can send work alerts.'}, status=status.HTTP_403_FORBIDDEN)
    notification = notify_work_email(subject, body, category='system_alert', user=request.user)
    if notification is None:
        return Response({'detail': 'WORK_NOTIFICATION_EMAIL is not configured.'}, status=status.HTTP_400_BAD_REQUEST)
    status_code = status.HTTP_200_OK if notification.status == 'sent' else status.HTTP_400_BAD_REQUEST
    return Response({'id': notification.id, 'status': notification.status, 'error_message': notification.error_message}, status=status_code)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def topup_initiate(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    serializer = TopUpInitiateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    idem_key = request.headers.get('Idempotency-Key')
    if idem_key:
        cached = get_cached_idempotency(request.user, 'wallet/topup/initiate', idem_key)
        if cached:
            return Response(cached.response_body, status=cached.status_code)
    wallet = request.user.wallet
    tx = PaymentTransaction.objects.create(
        tx_id=gen_tx_id('TOPUP'),
        user=request.user,
        wallet=wallet,
        provider=serializer.validated_data['provider'],
        amount=serializer.validated_data['amount'],
        status='pending',
        meta_json={
            'payment_method': serializer.validated_data['provider'],
            'phone_number_masked': _masked_phone(serializer.validated_data.get('phone_number')),
        },
    )
    payload = {'payment_transaction_id': tx.tx_id, 'status': tx.status}
    if tx.provider in {'mobile_money', 'bank_card', 'online_payment'}:
        try:
            result_url, return_url = _paynow_callback_urls(request, '/student/?topup=processing')
            _validate_public_paynow_urls(result_url, return_url)
            result = paynow_initiate(
                reference=tx.tx_id,
                amount=tx.amount,
                email=None,
                additional_info=f"HIT Canteen Wallet Top Up ({'Mobile Money' if tx.provider == 'mobile_money' else 'Bank/Card'})",
                result_url=result_url,
                return_url=return_url,
            )
            redirect_url = result.get('browserurl') or result.get('pollurl')
            poll_url = result.get('pollurl')
            tx.provider_ref = result.get('paynowreference', '')[:128] or None
            tx.meta_json = {
                **(tx.meta_json or {}),
                'browserurl': result.get('browserurl') or '',
                'pollurl': poll_url or '',
                'resulturl': result_url,
                'returnurl': return_url,
                'payment_method': tx.provider,
            }
            tx.save(update_fields=['provider_ref', 'meta_json'])
            payload['redirect_url'] = redirect_url
            payload['poll_url'] = poll_url
        except (ValueError, HTTPError, URLError) as err:
            tx.status = 'failed'
            tx.meta_json = {
                **(tx.meta_json or {}),
                'resulturl': result_url if 'result_url' in locals() else '',
                'returnurl': return_url if 'return_url' in locals() else '',
                'gateway_error': str(err),
                'gateway_provider': 'paynow',
            }
            tx.save(update_fields=['status', 'meta_json'])
            add_fraud_alert('payment_gateway_error', 'medium', f"tx={tx.tx_id}, detail={err}")
            return Response({'detail': str(err)}, status=status.HTTP_400_BAD_REQUEST)
    add_audit(request.user, 'wallet_topup_initiated', 'payment_transaction', tx.tx_id, _client_context(request))
    if idem_key:
        cache_idempotency_response(request.user, 'wallet/topup/initiate', idem_key, payload, 200)
    return Response(payload)


@api_view(['POST'])
@permission_classes([AllowAny])
def payment_webhook(request, provider):
    raw_body = request.body
    signature = request.headers.get('X-Signature', '')
    if not verify_webhook_signature(provider, raw_body, signature):
        add_fraud_alert('invalid_webhook_signature', 'high', f"provider={provider}")
        return Response({'detail': 'Invalid signature'}, status=status.HTTP_403_FORBIDDEN)
    serializer = PaymentWebhookSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    try:
        tx = PaymentTransaction.objects.get(tx_id=data['tx_id'])
    except PaymentTransaction.DoesNotExist:
        return Response({'detail': 'Transaction not found'}, status=status.HTTP_404_NOT_FOUND)
    _flag_duplicate_provider_ref(data['provider_ref'], tx.tx_id)
    if data['status'] == 'succeeded':
        _apply_successful_topup(tx, data['provider_ref'], f"Verified {provider} callback", verified=True)
    else:
        tx.status = 'failed'
        tx.callback_verified = True
        tx.provider_ref = data['provider_ref'][:128]
        tx.updated_at = timezone.now()
        tx.save(update_fields=['status', 'callback_verified', 'provider_ref', 'updated_at'])
    add_audit(tx.user, 'payment_webhook', 'payment_transaction', tx.tx_id, f"provider={provider}")
    return Response({'detail': 'Webhook processed'})


@api_view(['POST'])
@permission_classes([AllowAny])
def paynow_result(request):
    raw_message = request.body or '&'.join(f"{k}={v}" for k, v in request.data.items()).encode('utf-8')
    pairs, payload = parse_paynow_message(raw_message)
    if not paynow_validate_hash(pairs, payload.get('hash', '')):
        add_fraud_alert('invalid_paynow_hash', 'high', 'Invalid Paynow hash on result callback')
        return Response({'detail': 'Invalid hash'}, status=status.HTTP_403_FORBIDDEN)
    reference = payload.get('reference')
    if not reference:
        return Response({'detail': 'Missing reference'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        tx = PaymentTransaction.objects.get(tx_id=reference)
    except PaymentTransaction.DoesNotExist:
        return Response({'detail': 'Transaction not found'}, status=status.HTTP_404_NOT_FOUND)
    status_text = (payload.get('status') or '').lower()
    provider_ref = payload.get('paynowreference', '')
    if payload.get('pollurl'):
        try:
            polled = paynow_poll_status(payload['pollurl'])
            status_text = (polled.get('status') or status_text).lower()
            provider_ref = polled.get('paynowreference') or provider_ref
            payload.update(polled)
        except Exception as err:
            add_fraud_alert('paynow_poll_failure', 'medium', f"tx={reference}, detail={err}")
    provider_error = paynow_error_message(payload)
    if not status_text:
        add_fraud_alert('paynow_missing_status', 'medium', f"tx={reference}, detail={provider_error or 'missing status'}")
        return Response({'detail': provider_error or 'Paynow did not return a payment status yet.', 'status': 'pending'}, status=status.HTTP_202_ACCEPTED)
    _flag_duplicate_provider_ref(provider_ref, tx.tx_id)
    if status_text in PAYNOW_SUCCESS_STATUSES:
        if tx.purpose == 'order_payment':
            _apply_successful_order_payment(tx, provider_ref, verified=True)
        else:
            _apply_successful_topup(tx, provider_ref, 'Paynow confirmed top-up', verified=True)
    elif status_text in PAYNOW_FAILURE_STATUSES:
        tx.status = 'failed'
        tx.callback_verified = True
        tx.provider_ref = (provider_ref or '')[:128] or tx.provider_ref
        tx.updated_at = timezone.now()
        tx.save(update_fields=['status', 'callback_verified', 'provider_ref', 'updated_at'])
    else:
        return Response({'detail': provider_error or f'Paynow returned an unrecognized status: {status_text}', 'status': 'pending'}, status=status.HTTP_202_ACCEPTED)
    add_audit(tx.user, 'paynow_result', 'payment_transaction', tx.tx_id, f"status={status_text}")
    return Response({'detail': 'Paynow result processed', 'status': status_text})


@api_view(['POST'])
@permission_classes([AllowAny])
def simulate_payment_success(_request, tx_id):
    try:
        tx = PaymentTransaction.objects.get(tx_id=tx_id)
    except PaymentTransaction.DoesNotExist:
        return Response({'detail': 'Transaction not found'}, status=status.HTTP_404_NOT_FOUND)
    if tx.purpose == 'order_payment':
        _apply_successful_order_payment(tx, f'SIM-{tx.tx_id}', verified=True)
    else:
        _apply_successful_topup(tx, f'SIM-{tx.tx_id}', 'Development simulated success', verified=True)
    return Response({'detail': 'Simulated payment success applied'})


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def menu(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    _ensure_seed_data()
    if request.method == 'GET':
        meals = Meal.objects.filter(active=True).order_by('id')
        return Response([{'id': meal.id, 'name': meal.name, 'description': meal.description, 'price': float(meal.price), 'image_data': _get_meal_image(meal.id), 'stock_quantity': meal.stock_quantity, 'active': meal.active} for meal in meals])
    role_error = _require_role(request, 'staff', 'admin')
    if role_error:
        return role_error
    name = (request.data.get('name') or '').strip()
    price = request.data.get('price')
    stock_quantity = request.data.get('stock_quantity', 50)
    if not name or not price:
        return Response({'detail': 'Name, price, and stock are required'}, status=status.HTTP_400_BAD_REQUEST)
    meal = Meal.objects.create(
        name=name,
        description=(request.data.get('description') or '').strip(),
        price=Decimal(str(price)),
        stock_quantity=max(0, int(stock_quantity)),
        active=bool(request.data.get('active', True)),
    )
    _set_meal_image(meal.id, (request.data.get('image_data') or '').strip())
    add_audit(request.user, 'create_meal', 'meal', meal.id, _client_context(request))
    return Response({'id': meal.id, 'name': meal.name, 'description': meal.description, 'price': float(meal.price), 'image_data': _get_meal_image(meal.id), 'stock_quantity': meal.stock_quantity, 'active': meal.active}, status=status.HTTP_201_CREATED)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def manage_meal(request, meal_id):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    role_error = _require_role(request, 'staff', 'admin')
    if role_error:
        return role_error
    meal = Meal.objects.filter(id=meal_id).first()
    if not meal:
        return Response({'detail': 'Meal not found'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'DELETE':
        meal.active = False
        meal.save(update_fields=['active'])
        add_audit(request.user, 'remove_meal', 'meal', meal.id, _client_context(request))
        return Response({'detail': 'Meal removed from active menu.'})
    updated_fields = []
    name = request.data.get('name')
    description = request.data.get('description')
    price = request.data.get('price')
    image_data = request.data.get('image_data')
    stock_delta = request.data.get('stock_delta')
    stock_quantity = request.data.get('stock_quantity')
    if name is not None:
        meal.name = str(name).strip()
        updated_fields.append('name')
    if description is not None:
        meal.description = str(description).strip()
        updated_fields.append('description')
    if price is not None:
        meal.price = Decimal(str(price))
        updated_fields.append('price')
    if stock_delta is not None:
        meal.stock_quantity = max(0, meal.stock_quantity + int(stock_delta))
        updated_fields.append('stock_quantity')
    elif stock_quantity is not None:
        meal.stock_quantity = max(0, int(stock_quantity))
        updated_fields.append('stock_quantity')
    if 'active' in request.data:
        meal.active = bool(request.data.get('active'))
        updated_fields.append('active')
    if image_data is not None:
        _set_meal_image(meal.id, str(image_data).strip())
    if not updated_fields:
        return Response({'detail': 'No meal fields were provided for update.'}, status=status.HTTP_400_BAD_REQUEST)
    meal.save(update_fields=list(dict.fromkeys(updated_fields)))
    add_audit(request.user, 'update_meal', 'meal', meal.id, f"fields={','.join(dict.fromkeys(updated_fields))}, stock={meal.stock_quantity}, {_client_context(request)}")
    return Response({'id': meal.id, 'name': meal.name, 'description': meal.description, 'price': float(meal.price), 'image_data': _get_meal_image(meal.id), 'stock_quantity': meal.stock_quantity, 'active': meal.active})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def pickup_slots(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    _ensure_seed_data()
    slots = PickupSlot.objects.filter(slot_date__gte=date.today()).order_by('slot_date', 'start_time')[:12]
    return Response([
        {
            'id': slot.id,
            'slot_date': slot.slot_date.isoformat(),
            'start_time': slot.start_time.strftime('%H:%M'),
            'end_time': slot.end_time.strftime('%H:%M'),
            'capacity': slot.capacity,
            'booked': slot_booked_qty(slot),
            'estimated_wait_minutes': estimated_wait_minutes(slot_booked_qty(slot)),
        }
        for slot in slots
    ])


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def create_order(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    if request.method == 'GET':
        role_error = _require_role(request, 'staff', 'admin')
        if role_error:
            return role_error
        orders = Order.objects.select_related('user', 'meal', 'slot').order_by('-created_at')[:50]
        return Response([
            {
                'order_id': order.id,
                'order_ref': order.order_ref,
                'student_name': order.user.full_name,
                'student_email': order.user.email,
                'meal': order.meal.name,
                'quantity': order.quantity,
                'total_amount': float(order.total_amount),
                'status': order.status,
                'created_at': order.created_at.isoformat(),
            }
            for order in orders
        ])
    serializer = OrderCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    idem_key = request.headers.get('Idempotency-Key')
    if idem_key:
        cached = get_cached_idempotency(request.user, 'orders', idem_key)
        if cached:
            return Response(cached.response_body, status=cached.status_code)
    meal = Meal.objects.filter(id=serializer.validated_data['meal_id'], active=True).first()
    slot = PickupSlot.objects.filter(id=serializer.validated_data['slot_id']).first()
    if not meal or not slot:
        return Response({'detail': 'Meal or pickup slot not found'}, status=status.HTTP_404_NOT_FOUND)
    if slot_booked_qty(slot) + serializer.validated_data['quantity'] > slot.capacity:
        return Response({'detail': 'Pickup slot is full'}, status=status.HTTP_400_BAD_REQUEST)
    if meal.stock_quantity < serializer.validated_data['quantity']:
        return Response({'detail': 'Meal stock is not enough for this order'}, status=status.HTTP_400_BAD_REQUEST)
    total_amount = meal.price * serializer.validated_data['quantity']
    if wallet_balance(request.user.wallet) < total_amount:
        return Response({'detail': 'Insufficient wallet balance'}, status=status.HTTP_400_BAD_REQUEST)
    with transaction.atomic():
        order, ticket = _create_paid_order_ticket(request.user, meal, slot, serializer.validated_data['quantity'])
        WalletLedgerEntry.objects.create(wallet=request.user.wallet, tx_id=gen_tx_id('DEBIT'), entry_type='debit', amount=total_amount, provider='wallet', note=f'Order payment {order.order_ref}')
    payload = _ticket_payload(order, ticket)
    _flag_rapid_ordering(request.user, request)
    add_audit(request.user, 'create_order', 'order', order.id, _client_context(request))
    _safe_send_user_email(
        request.user,
        'HIT Canteen order confirmation',
        f'Hello {request.user.full_name},\n\nYour order has been confirmed.\nOrder reference: {order.order_ref}\nMeal: {meal.name}\nQuantity: {order.quantity}\nPickup slot: {slot.start_time.strftime("%H:%M")} - {slot.end_time.strftime("%H:%M")}\nTotal paid from wallet: ${order.total_amount:.2f}\n\nPresent your QR ticket at pickup.',
        'order_confirmation',
    )
    if idem_key:
        cache_idempotency_response(request.user, 'orders', idem_key, payload, 201)
    return Response(payload, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_paynow_order_payment(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    serializer = PaynowOrderInitiateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    items = serializer.validated_data['items']
    if not items:
        return Response({'detail': 'Add at least one item to continue with Paynow.'}, status=status.HTTP_400_BAD_REQUEST)
    idem_key = request.headers.get('Idempotency-Key')
    if idem_key:
        cached = get_cached_idempotency(request.user, 'orders/paynow/initiate', idem_key)
        if cached:
            return Response(cached.response_body, status=cached.status_code)

    slot = PickupSlot.objects.filter(id=serializer.validated_data['slot_id']).first()
    if not slot:
        return Response({'detail': 'Pickup slot not found.'}, status=status.HTTP_404_NOT_FOUND)

    meal_ids = [item['meal_id'] for item in items]
    meals = {meal.id: meal for meal in Meal.objects.filter(id__in=meal_ids, active=True)}
    total_amount = Decimal('0.00')
    booked_total = 0
    normalized_items = []
    for item in items:
        meal = meals.get(item['meal_id'])
        if not meal:
            return Response({'detail': 'One of the selected meals is no longer available.'}, status=status.HTTP_404_NOT_FOUND)
        quantity = int(item['quantity'])
        if meal.stock_quantity < quantity:
            return Response({'detail': f'{meal.name} does not have enough stock for this order.'}, status=status.HTTP_400_BAD_REQUEST)
        booked_total += quantity
        total_amount += meal.price * quantity
        normalized_items.append({'meal_id': meal.id, 'quantity': quantity, 'meal_name': meal.name, 'price': float(meal.price)})

    if slot_booked_qty(slot) + booked_total > slot.capacity:
        return Response({'detail': 'Pickup slot is full.'}, status=status.HTTP_400_BAD_REQUEST)

    tx = PaymentTransaction.objects.create(
        tx_id=gen_tx_id('PON'),
        user=request.user,
        wallet=request.user.wallet,
        provider=serializer.validated_data['provider'],
        amount=total_amount,
        status='pending',
        purpose='order_payment',
        meta_json={
            'slot_id': slot.id,
            'items': normalized_items,
            'payment_method': serializer.validated_data['provider'],
            'phone_number_masked': _masked_phone(serializer.validated_data.get('phone_number')),
        },
    )
    try:
        result_url, return_url = _paynow_callback_urls(request, '/student/?paynow=processing')
        _validate_public_paynow_urls(result_url, return_url)
        result = paynow_initiate(
            reference=tx.tx_id,
            amount=tx.amount,
            email=None,
            additional_info=f"HIT Canteen Order Payment ({'Mobile Money' if tx.provider == 'mobile_money' else 'Bank/Card'}, {len(normalized_items)} item(s))",
            result_url=result_url,
            return_url=return_url,
        )
        tx.provider_ref = result.get('paynowreference', '')[:128] or None
        tx.meta_json = {
            **(tx.meta_json or {}),
            'browserurl': result.get('browserurl') or '',
            'pollurl': result.get('pollurl') or '',
            'resulturl': result_url,
            'returnurl': return_url,
            'payment_method': tx.provider,
        }
        tx.save(update_fields=['provider_ref', 'meta_json'])
    except (ValueError, HTTPError, URLError) as err:
        tx.status = 'failed'
        tx.meta_json = {
            **(tx.meta_json or {}),
            'resulturl': result_url if 'result_url' in locals() else '',
            'returnurl': return_url if 'return_url' in locals() else '',
            'gateway_error': str(err),
            'gateway_provider': 'paynow',
        }
        tx.save(update_fields=['status', 'meta_json'])
        add_fraud_alert('payment_gateway_error', 'medium', f"tx={tx.tx_id}, detail={err}")
        return Response({'detail': str(err)}, status=status.HTTP_400_BAD_REQUEST)

    payload = {
        'payment_transaction_id': tx.tx_id,
        'status': tx.status,
        'total_amount': float(total_amount),
        'redirect_url': result.get('browserurl') or result.get('pollurl'),
        'poll_url': result.get('pollurl'),
    }
    add_audit(request.user, 'paynow_order_initiated', 'payment_transaction', tx.tx_id, _client_context(request))
    if idem_key:
        cache_idempotency_response(request.user, 'orders/paynow/initiate', idem_key, payload, 200)
    return Response(payload)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def walkin_order(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    role_error = _require_role(request, 'staff', 'admin')
    if role_error:
        return role_error
    meal = Meal.objects.filter(id=request.data.get('meal_id'), active=True).first()
    quantity = max(1, int(request.data.get('quantity', 1)))
    customer_name = (request.data.get('customer_name') or 'Walk-in').strip()
    if not meal:
        return Response({'detail': 'Meal not found'}, status=status.HTTP_404_NOT_FOUND)
    if meal.stock_quantity < quantity:
        return Response({'detail': 'Not enough stock available for this walk-in order'}, status=status.HTTP_400_BAD_REQUEST)
    meal.stock_quantity = max(0, meal.stock_quantity - quantity)
    meal.save(update_fields=['stock_quantity'])
    add_audit(request.user, 'walkin_order', 'meal', meal.id, f"customer={customer_name}, quantity={quantity}, {_client_context(request)}")
    return Response({'detail': f'Walk-in order recorded for {customer_name}.', 'meal_id': meal.id, 'stock_quantity': meal.stock_quantity})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def order_detail(request, order_id):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    order = Order.objects.select_related('meal', 'slot', 'user').filter(id=order_id).first()
    if not order:
        return Response({'detail': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)
    if request.user.role == 'student' and order.user_id != request.user.id:
        return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    return Response({'order_id': order.id, 'order_ref': order.order_ref, 'meal': order.meal.name, 'quantity': order.quantity, 'total_amount': float(order.total_amount), 'status': order.status, 'student_name': order.user.full_name, 'pickup_slot': f"{order.slot.start_time.strftime('%H:%M')} - {order.slot.end_time.strftime('%H:%M')}"})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ticket_by_order(request, order_id):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    ticket = MealTicket.objects.select_related('order__user').filter(order_id=order_id).first()
    if not ticket:
        return Response({'detail': 'Ticket not found'}, status=status.HTTP_404_NOT_FOUND)
    if request.user.role == 'student' and ticket.order.user_id != request.user.id:
        return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    return Response({'ticket_id': ticket.ticket_id, 'token': ticket.token, 'qr_svg': ticket.qr_svg, 'status': ticket.status, 'expires_at': ticket.expires_at.isoformat()})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_tickets(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    tickets = MealTicket.objects.select_related('order').filter(order__user=request.user).order_by('-order__created_at')[:12]
    return Response([
        {
            'ticket_id': ticket.ticket_id,
            'token': ticket.token,
            'qr_svg': ticket.qr_svg,
            'status': ticket.status,
            'expires_at': ticket.expires_at.isoformat(),
            'order_ref': ticket.order.order_ref,
        }
        for ticket in tickets
    ])


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def validate_scan(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    role_error = _require_role(request, 'staff', 'admin')
    if role_error:
        return role_error
    serializer = ScanSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    payload = verify_ticket_payload(serializer.validated_data['token'])
    if not payload:
        add_fraud_alert('invalid_ticket_signature', 'high', f"scanner={request.user.email}, {_client_context(request)}")
        _flag_repeated_failed_scans(request)
        return Response({'detail': 'Invalid ticket token'}, status=status.HTTP_400_BAD_REQUEST)
    data = json.loads(payload)
    ticket = MealTicket.objects.select_related('order').filter(order_id=data.get('order_id'), token=serializer.validated_data['token']).first()
    if not ticket:
        add_fraud_alert('missing_ticket_record', 'high', f"order_id={data.get('order_id')}, scanner={request.user.email}, {_client_context(request)}")
        _flag_repeated_failed_scans(request)
        return Response({'detail': 'Ticket record not found'}, status=status.HTTP_404_NOT_FOUND)
    if ticket.status == 'redeemed':
        add_fraud_alert('duplicate_ticket_scan', 'high', f"ticket={ticket.ticket_id}, scanner={request.user.email}, {_client_context(request)}")
        _flag_repeated_failed_scans(request)
        return Response({'detail': 'Ticket already redeemed'}, status=status.HTTP_400_BAD_REQUEST)
    if ticket.expires_at <= timezone.now():
        ticket.status = 'expired'
        ticket.save(update_fields=['status'])
        add_fraud_alert('expired_ticket_scan', 'medium', f"ticket={ticket.ticket_id}, scanner={request.user.email}, {_client_context(request)}")
        _flag_repeated_failed_scans(request)
        return Response({'detail': 'Ticket expired'}, status=status.HTTP_400_BAD_REQUEST)
    with transaction.atomic():
        ticket.status = 'redeemed'
        ticket.redeemed_at = timezone.now()
        ticket.save(update_fields=['status', 'redeemed_at'])
        ticket.order.status = 'served'
        ticket.order.save(update_fields=['status'])
    add_audit(request.user, 'scan_ticket', 'ticket', ticket.ticket_id, f"served order={ticket.order_id}, {_client_context(request)}")
    return Response({'detail': 'Ticket valid and redeemed.', 'order_id': ticket.order.id, 'order_ref': ticket.order.order_ref, 'student_id': ticket.order.user_id})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_kpis(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    role_error = _require_role(request, 'staff', 'admin')
    if role_error:
        return role_error
    successful_payments_total = PaymentTransaction.objects.filter(status='succeeded').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    cash_deposits_total = CashDeposit.objects.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    total_revenue = successful_payments_total + cash_deposits_total
    return Response({
        'total_revenue': float(total_revenue),
        'total_transactions': PaymentTransaction.objects.count() + CashDeposit.objects.count(),
        'successful_transactions': PaymentTransaction.objects.filter(status='succeeded').count(),
        'failed_payments': PaymentTransaction.objects.filter(status='failed').count(),
        'active_students': User.objects.filter(role='student', is_active=True, is_suspended=False).count(),
        'active_staff': User.objects.filter(role__in=['staff', 'admin'], is_active=True).count(),
        'meals_active': Meal.objects.filter(active=True).count(),
        'paid_orders': Order.objects.filter(status='paid').count(),
        'served_orders': Order.objects.filter(status='served').count(),
        'wallet_topups': PaymentTransaction.objects.filter(status='succeeded', purpose='wallet_topup').count() + CashDeposit.objects.count(),
        'cash_deposits': CashDeposit.objects.count(),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_students(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    role_error = _require_role(request, 'admin')
    if role_error:
        return role_error
    query = (request.query_params.get('q') or '').strip().lower()
    users = User.objects.filter(role='student').order_by('full_name')
    if query:
        users = users.filter(models.Q(full_name__icontains=query) | models.Q(email__icontains=query) | models.Q(university_id__icontains=query))
    users = users[:100]
    return Response([
        {
            'id': user.id,
            'name': user.full_name,
            'student_id': user.university_id,
            'email': user.email,
            'balance': float(wallet_balance(user.wallet)) if hasattr(user, 'wallet') else 0.0,
            'is_suspended': user.is_suspended,
            'status': 'Suspended' if user.is_suspended else ('Verified' if user.is_email_verified else 'Pending Verification'),
        }
        for user in users
    ])


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def admin_student_status(request, user_id):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    role_error = _require_role(request, 'admin')
    if role_error:
        return role_error
    student = User.objects.filter(id=user_id, role='student').first()
    if not student:
        return Response({'detail': 'Student not found.'}, status=status.HTTP_404_NOT_FOUND)
    action_name = str(request.data.get('action') or '').strip().lower()
    if action_name not in {'activate', 'suspend'}:
        return Response({'detail': 'Action must be activate or suspend.'}, status=status.HTTP_400_BAD_REQUEST)
    student.is_suspended = action_name == 'suspend'
    student.suspended_at = timezone.now() if student.is_suspended else None
    student.save(update_fields=['is_suspended', 'suspended_at'])
    add_audit(
        request.user,
        'admin_student_status_updated',
        'user',
        student.id,
        f'action={action_name}, target={student.email}, {_client_context(request)}',
    )
    return Response({
        'detail': f"Student account {'suspended' if student.is_suspended else 'activated'} successfully.",
        'student_id': student.id,
        'is_suspended': student.is_suspended,
        'status': 'Suspended' if student.is_suspended else ('Verified' if student.is_email_verified else 'Pending Verification'),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_staff_members(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    role_error = _require_role(request, 'admin')
    if role_error:
        return role_error
    query = (request.query_params.get('q') or '').strip().lower()
    users = User.objects.filter(role__in=['staff', 'admin']).order_by('full_name')
    if query:
        users = users.filter(models.Q(full_name__icontains=query) | models.Q(email__icontains=query))
    users = users[:100]
    return Response([
        {
            'id': user.id,
            'name': user.full_name,
            'email': user.email,
            'role': user.role.title(),
            'status': 'Suspended' if user.is_suspended else 'Active',
        }
        for user in users
    ])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_food_items(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    role_error = _require_role(request, 'admin')
    if role_error:
        return role_error
    meals = Meal.objects.filter(active=True).order_by('name')[:100]
    return Response([
        {
            'id': meal.id,
            'name': meal.name,
            'category': 'Drinks' if 'water' in meal.name.lower() or 'orange' in meal.name.lower() or 'juice' in meal.name.lower() else ('Snacks' if 'pie' in meal.name.lower() or 'snack' in (meal.description or '').lower() else 'Meals'),
            'price': float(meal.price),
            'image_data': _get_meal_image(meal.id),
            'availability': 'Active' if meal.active else 'Inactive',
            'stock_quantity': meal.stock_quantity,
        }
        for meal in meals
    ])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_all_transactions(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    role_error = _require_role(request, 'admin')
    if role_error:
        return role_error
    payments = [
        {
            'transaction_id': tx.tx_id,
            'student': tx.user.full_name,
            'student_email': tx.user.email,
            'item': tx.meta_json.get('created_orders', [{}])[0].get('order_ref', tx.purpose.replace('_', ' ').title()) if isinstance(tx.meta_json, dict) else tx.purpose,
            'amount': float(tx.amount),
            'method': tx.provider.replace('_', ' ').title(),
            'status': tx.status.title(),
            'time': tx.created_at.isoformat(),
        }
        for tx in PaymentTransaction.objects.select_related('user').order_by('-created_at')[:150]
    ]
    cash_deposits = [
        {
            'transaction_id': f'CASH-{deposit.id}',
            'student': deposit.student.full_name,
            'student_email': deposit.student.email,
            'item': 'Wallet Top Up',
            'amount': float(deposit.amount),
            'method': 'Cash Deposit',
            'status': 'Succeeded',
            'time': deposit.timestamp.isoformat(),
        }
        for deposit in CashDeposit.objects.select_related('student').order_by('-timestamp')[:150]
    ]
    items = sorted(payments + cash_deposits, key=lambda item: item['time'], reverse=True)[:150]
    return Response(items)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_reports_summary(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    role_error = _require_role(request, 'admin')
    if role_error:
        return role_error
    top_items = (
        Order.objects.values('meal__name')
        .annotate(total_qty=Sum('quantity'))
        .order_by('-total_qty')[:5]
    )
    method_breakdown = (
        PaymentTransaction.objects.filter(status='succeeded')
        .values('provider')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )
    failed = PaymentTransaction.objects.select_related('user').filter(status='failed').order_by('-created_at')[:10]
    return Response({
        'top_items': [{'name': row['meal__name'], 'quantity': row['total_qty']} for row in top_items],
        'payment_methods': [{'method': row['provider'], 'amount': float(row['total'] or 0)} for row in method_breakdown],
        'failed_payments': [{'tx_id': tx.tx_id, 'student': tx.user.full_name, 'amount': float(tx.amount), 'time': tx.created_at.isoformat()} for tx in failed],
    })


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def admin_settings(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    role_error = _require_role(request, 'admin')
    if role_error:
        return role_error

    serializer = AdminSettingsSerializer(data=request.data, partial=True) if request.method == 'PATCH' else None
    if serializer is not None:
        serializer.is_valid(raise_exception=True)

    try:
        settings_obj = _admin_settings()
        if request.method == 'GET':
            return Response({
                'paynow_integration_id': settings_obj.paynow_integration_id,
                'paynow_return_url': settings_obj.paynow_return_url,
                'smtp_host': settings_obj.smtp_host,
                'default_from_email': settings_obj.default_from_email,
                'qr_expiry_minutes': settings_obj.qr_expiry_minutes,
                'email_alerts_enabled': settings_obj.email_alerts_enabled,
                'fraud_alerts_enabled': settings_obj.fraud_alerts_enabled,
                'session_timeout_minutes': settings_obj.session_timeout_minutes,
                'updated_at': settings_obj.updated_at.isoformat() if settings_obj.updated_at else None,
            })

        for field, value in serializer.validated_data.items():
            setattr(settings_obj, field, value)
        settings_obj.updated_at = timezone.now()
        settings_obj.save()
        add_audit(request.user, 'admin_settings_updated', 'AdminSetting', str(settings_obj.pk), f"fields={','.join(serializer.validated_data.keys())}")
        return Response({
            'detail': 'Settings saved successfully.',
            'updated_at': settings_obj.updated_at.isoformat(),
        })
    except (OperationalError, ProgrammingError):
        if request.method == 'GET':
            data = _load_admin_settings_fallback()
            data['updated_at'] = None
            return Response(data)

        _save_admin_settings_fallback(serializer.validated_data)
        add_audit(request.user, 'admin_settings_updated', 'AdminSettingFallback', 'local-json', f"fields={','.join(serializer.validated_data.keys())}")
        return Response({
            'detail': 'Settings saved successfully.',
            'updated_at': None,
        })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def auth_me(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    balance = float(wallet_balance(request.user.wallet)) if hasattr(request.user, 'wallet') else 0.0
    return Response({
        'id': request.user.id,
        'full_name': request.user.full_name,
        'student_id': request.user.university_id,
        'email': request.user.email,
        'role': request.user.role,
        'wallet_balance': balance,
        'is_email_verified': request.user.is_email_verified,
        'is_suspended': request.user.is_suspended,
    })


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    serializer = ProfileUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    if User.objects.filter(email=data['email']).exclude(id=request.user.id).exists():
        return Response({'email': ['This HIT email is already in use.']}, status=status.HTTP_400_BAD_REQUEST)
    request.user.full_name = data['full_name']
    request.user.email = data['email']
    request.user.save(update_fields=['full_name', 'email'])
    add_audit(request.user, 'profile_updated', 'user', request.user.id, _client_context(request))
    return Response({
        'detail': 'Account updated successfully.',
        'full_name': request.user.full_name,
        'email': request.user.email,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    serializer = PasswordChangeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    if not request.user.check_password(data['current_password']):
        return Response({'current_password': ['Current password is incorrect.']}, status=status.HTTP_400_BAD_REQUEST)
    request.user.set_password(data['new_password'])
    request.user.save(update_fields=['password'])
    add_audit(request.user, 'password_changed', 'user', request.user.id, _client_context(request))
    return Response({'detail': 'Password changed successfully. Please log in again.'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def served_meals(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    role_error = _require_role(request, 'staff', 'admin')
    if role_error:
        return role_error
    orders = (
        Order.objects.filter(status='served')
        .select_related('user', 'meal', 'slot', 'mealticket')
        .order_by('-created_at')[:50]
    )
    return Response([
        {
            'order_id': order.id,
            'order_ref': order.order_ref,
            'student_name': order.user.full_name,
            'student_email': order.user.email,
            'meal': order.meal.name,
            'quantity': order.quantity,
            'total_amount': float(order.total_amount),
            'served_at': order.mealticket.redeemed_at.isoformat() if getattr(order, 'mealticket', None) and order.mealticket.redeemed_at else None,
            'pickup_slot': f"{order.slot.start_time.strftime('%H:%M')} - {order.slot.end_time.strftime('%H:%M')}",
        }
        for order in orders
    ])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def revenue_report(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    role_error = _require_role(request, 'staff', 'admin')
    if role_error:
        return role_error
    total = PaymentTransaction.objects.filter(status='succeeded').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    return Response({'payments_received': float(total), 'successful_payments_count': PaymentTransaction.objects.filter(status='succeeded').count()})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def fraud_report(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    role_error = _require_role(request, 'staff', 'admin')
    if role_error:
        return role_error
    alerts = FraudAlert.objects.order_by('-created_at')[:50]
    return Response([{'alert_type': alert.alert_type, 'severity': alert.severity, 'detail': alert.detail, 'created_at': alert.created_at.isoformat()} for alert in alerts])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def demand_forecast(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    role_error = _require_role(request, 'staff', 'admin')
    if role_error:
        return role_error
    target = request.query_params.get('date')
    target_date = timezone.localdate() if not target else date.fromisoformat(target)
    return Response(demand_forecast_for_date(target_date))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def daily_reconciliation(request):
    suspension = _ensure_not_suspended(request.user)
    if suspension:
        return suspension
    role_error = _require_role(request, 'staff', 'admin')
    if role_error:
        return role_error
    target = request.query_params.get('date')
    target_date = timezone.localdate() if not target else date.fromisoformat(target)
    report = _build_reconciliation(target_date)
    add_audit(request.user, 'daily_reconciliation', 'daily_reconciliation_report', report.id, _client_context(request))
    return Response({
        'report_date': report.report_date.isoformat(),
        'payments_received': float(report.payments_received),
        'paid_orders_total': float(report.paid_orders_total),
        'meals_collected_total': report.meals_collected_total,
        'successful_payments_count': report.successful_payments_count,
        'paid_orders_count': report.paid_orders_count,
        'served_orders_count': report.served_orders_count,
        'discrepancy_amount': float(report.discrepancy_amount),
        'notes': report.notes,
    })








































