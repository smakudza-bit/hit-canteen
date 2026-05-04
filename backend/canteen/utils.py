import hmac
import hashlib
import io
import json
import uuid
from decimal import Decimal
from datetime import timedelta
from urllib.parse import urlencode, parse_qsl, urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

import qrcode
from qrcode.image.svg import SvgPathImage
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Sum
from django.utils import timezone

from .models import WalletLedgerEntry, AuditLog, FraudAlert, NotificationLog, Order, PickupSlot, IdempotencyKey, Meal


PAYNOW_DEFAULT_INITIATE_URL = 'https://www.paynow.co.zw/interface/initiatetransaction'
PAYNOW_SUCCESS_STATUSES = {'paid', 'awaiting delivery', 'delivered'}
PAYNOW_FAILURE_STATUSES = {'failed', 'cancelled'}


def gen_tx_id(prefix='TX'):
    return f'{prefix}-{uuid.uuid4().hex[:20].upper()}'


def wallet_balance(wallet):
    credits = wallet.entries.filter(entry_type='credit').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    debits = wallet.entries.filter(entry_type='debit').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    return credits - debits


def add_audit(actor, action, entity, entity_id, detail=''):
    AuditLog.objects.create(actor_user=actor, action=action, entity=entity, entity_id=str(entity_id), detail=detail)


def add_fraud_alert(alert_type, severity, detail):
    alert = FraudAlert.objects.create(alert_type=alert_type, severity=severity, detail=detail)
    if severity.lower() in {'high', 'critical'}:
        notify_work_email(
            subject=f'HIT Canteen fraud alert: {alert_type}',
            body=f'Severity: {severity}\n\nDetail:\n{detail}',
            category='fraud_alert',
        )
    return alert

def send_notification_email(recipient_email, subject, body, *, category='general', user=None, html_body=None):
    notification = NotificationLog.objects.create(
        user=user,
        category=category,
        recipient_email=recipient_email,
        subject=subject,
        body=body,
        status='pending',
    )
    if not settings.EMAIL_NOTIFICATIONS_ENABLED:
        notification.status = 'failed'
        notification.error_message = 'Email notifications are disabled.'
        notification.save(update_fields=['status', 'error_message'])
        return notification
    if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
        notification.status = 'failed'
        notification.error_message = 'SMTP credentials are not configured.'
        notification.save(update_fields=['status', 'error_message'])
        return notification
    try:
        message = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email],
        )
        if html_body:
            message.attach_alternative(html_body, 'text/html')
        message.send(fail_silently=False)
        notification.status = 'sent'
        notification.sent_at = timezone.now()
        notification.save(update_fields=['status', 'sent_at'])
    except Exception as err:
        notification.status = 'failed'
        notification.error_message = str(err)
        notification.save(update_fields=['status', 'error_message'])
    return notification


def notify_work_email(subject, body, *, category='system_alert', user=None):
    work_email = getattr(settings, 'WORK_NOTIFICATION_EMAIL', '')
    if not work_email:
        return None
    return send_notification_email(work_email, subject, body, category=category, user=user)


def sign_ticket_payload(payload):
    signature = hmac.new(settings.HIT_TICKET_SECRET.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).hexdigest()
    return f'{payload}.{signature}'


def verify_ticket_payload(token):
    parts = token.rsplit('.', 1)
    if len(parts) != 2:
        return None
    payload, signature = parts
    expected = hmac.new(settings.HIT_TICKET_SECRET.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return None
    return payload


def create_ticket(order_id, user_id, slot_id):
    expires = timezone.now() + timedelta(minutes=120)
    payload = json.dumps(
        {
            'order_id': order_id,
            'user_id': user_id,
            'slot_id': slot_id,
            'nonce': uuid.uuid4().hex,
            'exp': int(expires.timestamp()),
        },
        separators=(',', ':'),
    )
    token = sign_ticket_payload(payload)

    qr = qrcode.QRCode(version=1, box_size=8, border=1)
    qr.add_data(token)
    qr.make(fit=True)
    out = io.BytesIO()
    qr.make_image(image_factory=SvgPathImage).save(out)
    return token, out.getvalue().decode('utf-8'), expires


def slot_booked_qty(slot):
    total = Order.objects.filter(slot=slot, status__in=['paid', 'served']).aggregate(total=Sum('quantity'))['total']
    return total or 0


def estimated_wait_minutes(booked, service_rate_per_15min=40):
    if booked <= 0:
        return 0
    return max(2, int((booked / max(1, service_rate_per_15min)) * 15))


def provider_secret(provider):
    mapping = {
        'mobile_money': settings.WEBHOOK_SECRET_MOBILE_MONEY,
        'bank_card': settings.WEBHOOK_SECRET_BANK_CARD,
        'online_payment': settings.WEBHOOK_SECRET_ONLINE_PAYMENT,
    }
    return mapping.get(provider)


def verify_webhook_signature(provider, raw_body, signature):
    secret = provider_secret(provider)
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode('utf-8'), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def get_cached_idempotency(user, endpoint, idem_key):
    return IdempotencyKey.objects.filter(user=user, endpoint=endpoint, idem_key=idem_key).first()


def cache_idempotency_response(user, endpoint, idem_key, response_payload, status_code=200):
    IdempotencyKey.objects.create(
        user=user,
        endpoint=endpoint,
        idem_key=idem_key,
        response_body=response_payload,
        status_code=status_code,
    )


def _paynow_hash_from_pairs(pairs):
    joined = ''.join(value for key, value in pairs if key.lower() != 'hash') + settings.PAYNOW_INTEGRATION_KEY
    return hashlib.sha512(joined.encode('utf-8')).hexdigest().upper()


def paynow_generate_hash(pairs):
    return _paynow_hash_from_pairs(list(pairs))


def parse_paynow_message(raw_message):
    if isinstance(raw_message, bytes):
        raw_message = raw_message.decode('utf-8')
    pairs = parse_qsl(raw_message, keep_blank_values=True)
    normalized = {key.lower(): value for key, value in pairs}
    return pairs, normalized


def paynow_error_message(payload):
    if not isinstance(payload, dict):
        return ''
    return (
        payload.get('error')
        or payload.get('errormessage')
        or payload.get('statusmessage')
        or payload.get('message')
        or ''
    ).strip()


def paynow_response_summary(payload):
    if not isinstance(payload, dict):
        return 'unparseable response'
    safe_keys = [
        'status',
        'statusmessage',
        'message',
        'error',
        'errormessage',
        'browserurl',
        'pollurl',
        'paynowreference',
    ]
    parts = []
    for key in safe_keys:
        value = str(payload.get(key, '') or '').strip()
        if value:
            if key in {'browserurl', 'pollurl'} and len(value) > 80:
                value = value[:77] + '...'
            parts.append(f'{key}={value}')
    return ', '.join(parts) or 'no diagnostic fields returned'


def mask_secret(value, visible=4):
    text = str(value or '').strip()
    if len(text) <= visible:
        return '*' * len(text)
    return ('*' * max(0, len(text) - visible)) + text[-visible:]


def paynow_env_status():
    return {
        'integration_id_loaded': bool(settings.PAYNOW_INTEGRATION_ID),
        'integration_id_preview': str(settings.PAYNOW_INTEGRATION_ID or '')[:6],
        'integration_key_loaded': bool(settings.PAYNOW_INTEGRATION_KEY),
        'integration_key_masked': mask_secret(settings.PAYNOW_INTEGRATION_KEY),
        'result_url': settings.PAYNOW_RESULT_URL,
        'return_url': settings.PAYNOW_RETURN_URL,
        'initiate_url': settings.PAYNOW_INITIATE_URL or PAYNOW_DEFAULT_INITIATE_URL,
        'include_auth_email': bool(getattr(settings, 'PAYNOW_INCLUDE_AUTH_EMAIL', True)),
    }


def validate_paynow_request_payload(pairs):
    payload = {key: str(value or '').strip() for key, value in pairs if key.lower() != 'hash'}
    required = ['id', 'reference', 'amount', 'additionalinfo', 'resulturl', 'returnurl', 'status']
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError(f"Missing Paynow fields: {', '.join(missing)}")

    if payload.get('status', '').lower() != 'message':
        raise ValueError("Paynow 'status' must be set to 'Message' when initiating a transaction.")

    for key in ('resulturl', 'returnurl'):
        parsed = urlparse(payload[key])
        if parsed.scheme.lower() != 'https':
            raise ValueError(f'{key} must use HTTPS for Paynow.')
        if not parsed.netloc:
            raise ValueError(f'{key} must be a fully qualified public URL.')

    if payload.get('authemail') and '@' not in payload['authemail']:
        raise ValueError('authemail must be a valid email address if provided.')

    if '"' in payload['id'] or "'" in payload['id']:
        raise ValueError('PAYNOW_INTEGRATION_ID contains quotes. Remove extra quotes from the .env value.')

    if '"' in settings.PAYNOW_INTEGRATION_KEY or "'" in settings.PAYNOW_INTEGRATION_KEY:
        raise ValueError('PAYNOW_INTEGRATION_KEY contains quotes. Remove extra quotes from the .env value.')


def paynow_validate_hash(pairs, provided_hash):
    if not settings.PAYNOW_INTEGRATION_KEY or not provided_hash:
        return False
    expected = _paynow_hash_from_pairs(pairs)
    return hmac.compare_digest(expected, provided_hash.upper())


def paynow_initiate(reference, amount, email, additional_info, result_url, return_url):
    if not settings.PAYNOW_INTEGRATION_ID or not settings.PAYNOW_INTEGRATION_KEY:
        raise ValueError(f"Paynow credentials are not configured ({paynow_env_status()})")

    pairs = [
        ('id', settings.PAYNOW_INTEGRATION_ID),
        ('reference', reference),
        ('amount', f'{Decimal(amount):.2f}'),
        ('additionalinfo', additional_info),
        ('status', 'Message'),
        ('resulturl', result_url),
        ('returnurl', return_url),
    ]
    if email and getattr(settings, 'PAYNOW_INCLUDE_AUTH_EMAIL', True):
        pairs.append(('authemail', email))
    validate_paynow_request_payload(pairs)
    pairs.append(('hash', paynow_generate_hash(pairs)))

    request = Request(
        settings.PAYNOW_INITIATE_URL or PAYNOW_DEFAULT_INITIATE_URL,
        data=urlencode(pairs).encode('utf-8'),
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST',
    )
    with urlopen(request, timeout=20) as response:
        body = response.read().decode('utf-8')
    response_pairs, payload = parse_paynow_message(body)
    status_text = payload.get('status', '').strip().lower()
    error_message = paynow_error_message(payload)
    response_summary = paynow_response_summary(payload)
    if status_text == 'error':
        raise ValueError(
            f"{error_message or 'Paynow initiate failed.'} "
            f"(Provider response: {response_summary})"
        )
    if not paynow_validate_hash(response_pairs, payload.get('hash', '')):
        raise ValueError(f'Invalid hash returned by Paynow ({response_summary})')
    if error_message and not (payload.get('browserurl') or payload.get('pollurl')):
        raise ValueError(f'{error_message} ({response_summary})')
    if not (payload.get('browserurl') or payload.get('pollurl')):
        raise ValueError(
            'Paynow did not return a payment link. '
            f'Provider response: {response_summary}. '
            'Check the merchant configuration, callback URLs, and Paynow account setup.'
        )
    return payload


def paynow_poll_status(poll_url):
    request = Request(poll_url, data=b'', headers={'Content-Type': 'application/x-www-form-urlencoded'}, method='POST')
    with urlopen(request, timeout=20) as response:
        body = response.read().decode('utf-8')
    response_pairs, payload = parse_paynow_message(body)
    if not paynow_validate_hash(response_pairs, payload.get('hash', '')):
        raise ValueError(f'Invalid hash returned by Paynow poll ({paynow_response_summary(payload)})')
    status_text = payload.get('status', '').strip()
    error_message = paynow_error_message(payload)
    if not status_text and error_message:
        raise ValueError(f'{error_message} ({paynow_response_summary(payload)})')
    return payload


def demand_forecast_for_date(target_date):
    weekday = target_date.weekday()
    start_date = target_date - timedelta(days=35)
    result = []
    for meal in Meal.objects.filter(active=True):
        rows = (
            Order.objects.filter(meal=meal, slot__slot_date__gte=start_date, slot__slot_date__lt=target_date)
            .values('slot__slot_date')
            .annotate(total=Sum('quantity'))
            .order_by('slot__slot_date')
        )
        qtys = [int(r['total']) for r in rows if r['slot__slot_date'].weekday() == weekday][-4:]
        forecast = round(sum(qtys) / len(qtys), 0) if qtys else 0
        result.append({'meal_id': meal.id, 'meal_name': meal.name, 'forecast_qty': int(forecast)})
    return result




