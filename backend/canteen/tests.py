import hashlib
import hmac
import json
from datetime import date, time
from decimal import Decimal

from django.conf import settings
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Meal, PickupSlot, User, Wallet, WalletLedgerEntry, Order, FraudAlert, PaymentTransaction


class CanteenApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.student = User.objects.create_user(
            email='student1@hit.ac.zw',
            password='Student123!',
            university_id='HITSTU001',
            full_name='Student One',
            role='student',
            is_staff=False,
        )
        self.student.is_email_verified = True
        self.student.save(update_fields=['is_email_verified'])

        self.staff = User.objects.create_user(
            email='staff1@hit.ac.zw',
            password='Staff123!',
            university_id='HITSTA001',
            full_name='Staff One',
            role='staff',
            is_staff=True,
        )
        self.staff.is_email_verified = True
        self.staff.save(update_fields=['is_email_verified'])

        self.admin = User.objects.create_user(
            email='admin1@hit.ac.zw',
            password='Admin123!',
            university_id='HITADM001',
            full_name='Admin One',
            role='admin',
            is_staff=True,
        )
        self.admin.is_email_verified = True
        self.admin.save(update_fields=['is_email_verified'])

        self.student_wallet = Wallet.objects.create(user=self.student)
        Wallet.objects.create(user=self.staff)
        Wallet.objects.create(user=self.admin)

        self.meal = Meal.objects.create(name='Sadza + Beans', description='Test meal', price=Decimal('2.50'), active=True)
        self.slot = PickupSlot.objects.create(slot_date=date.today(), start_time=time(13, 0), end_time=time(13, 30), capacity=100)

    def _login(self, email, password):
        res = self.client.post('/api/v1/auth/login', {'email': email, 'password': password}, format='json')
        self.assertEqual(res.status_code, 200)
        return res.data['access_token']

    def _auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_register_requires_hit_email_and_verification(self):
        bad = self.client.post('/api/v1/auth/register', {
            'full_name': 'Bad User',
            'university_id': 'BAD001',
            'email': 'bad@gmail.com',
            'password': 'Password123!',
            'role': 'student',
        }, format='json')
        self.assertEqual(bad.status_code, 400)

        good = self.client.post('/api/v1/auth/register', {
            'full_name': 'Student Two',
            'university_id': 'HITSTU002',
            'email': 'student2@hit.ac.zw',
            'password': 'Password123!',
            'role': 'student',
        }, format='json')
        self.assertEqual(good.status_code, 201)
        self.assertTrue(good.data['verification_required'])

    def test_login_requires_verified_email(self):
        user = User.objects.create_user(
            email='pending@hit.ac.zw',
            password='Password123!',
            university_id='HITSTU003',
            full_name='Pending User',
            role='student',
            is_staff=False,
        )
        Wallet.objects.create(user=user)
        res = self.client.post('/api/v1/auth/login', {'email': 'pending@hit.ac.zw', 'password': 'Password123!'}, format='json')
        self.assertEqual(res.status_code, 403)
        self.assertTrue(res.data['verification_required'])

    def test_topup_idempotency_reuses_transaction(self):
        token = self._login('student1@hit.ac.zw', 'Student123!')
        self._auth(token)
        payload = {'amount': '5.00', 'provider': 'mobile_money'}
        r1 = self.client.post('/api/v1/wallet/topup/initiate', payload, format='json', HTTP_IDEMPOTENCY_KEY='topup-abc-123')
        r2 = self.client.post('/api/v1/wallet/topup/initiate', payload, format='json', HTTP_IDEMPOTENCY_KEY='topup-abc-123')
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.data['payment_transaction_id'], r2.data['payment_transaction_id'])
        self.assertEqual(PaymentTransaction.objects.count(), 1)

    def test_order_idempotency_reuses_order(self):
        WalletLedgerEntry.objects.create(wallet=self.student_wallet, tx_id='SEED-CREDIT-1', entry_type='credit', amount=Decimal('20.00'), provider='seed')
        token = self._login('student1@hit.ac.zw', 'Student123!')
        self._auth(token)
        payload = {'meal_id': self.meal.id, 'slot_id': self.slot.id, 'quantity': 1}
        r1 = self.client.post('/api/v1/orders', payload, format='json', HTTP_IDEMPOTENCY_KEY='order-abc-123')
        r2 = self.client.post('/api/v1/orders', payload, format='json', HTTP_IDEMPOTENCY_KEY='order-abc-123')
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.data['order_ref'], r2.data['order_ref'])
        self.assertEqual(Order.objects.count(), 1)

    def test_payment_webhook_invalid_signature_rejected(self):
        tx = PaymentTransaction.objects.create(tx_id='PAY-INVALID-1', user=self.student, wallet=self.student_wallet, provider='mobile_money', amount=Decimal('5.00'), status='pending')
        payload = {'tx_id': tx.tx_id, 'provider_ref': 'GW-1', 'amount': '5.00', 'status': 'succeeded'}
        body = json.dumps(payload).encode('utf-8')
        r = self.client.post('/api/v1/payments/webhook/mobile_money', data=body, content_type='application/json', HTTP_X_SIGNATURE='bad-signature')
        self.assertEqual(r.status_code, 401)
        self.assertEqual(WalletLedgerEntry.objects.filter(tx_id=tx.tx_id).count(), 0)

    def test_payment_webhook_success_is_idempotent(self):
        tx = PaymentTransaction.objects.create(tx_id='PAY-VALID-1', user=self.student, wallet=self.student_wallet, provider='mobile_money', amount=Decimal('5.00'), status='pending')
        payload = {'tx_id': tx.tx_id, 'provider_ref': 'GW-OK-1', 'amount': '5.00', 'status': 'succeeded'}
        body = json.dumps(payload).encode('utf-8')
        signature = hmac.new(settings.WEBHOOK_SECRET_MOBILE_MONEY.encode('utf-8'), body, hashlib.sha256).hexdigest()
        r1 = self.client.post('/api/v1/payments/webhook/mobile_money', data=body, content_type='application/json', HTTP_X_SIGNATURE=signature)
        r2 = self.client.post('/api/v1/payments/webhook/mobile_money', data=body, content_type='application/json', HTTP_X_SIGNATURE=signature)
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(WalletLedgerEntry.objects.filter(tx_id=tx.tx_id, entry_type='credit').count(), 1)

    def test_ticket_scan_blocks_duplicate_redemption(self):
        WalletLedgerEntry.objects.create(wallet=self.student_wallet, tx_id='SEED-CREDIT-2', entry_type='credit', amount=Decimal('20.00'), provider='seed')
        student_token = self._login('student1@hit.ac.zw', 'Student123!')
        self._auth(student_token)
        order_res = self.client.post('/api/v1/orders', {'meal_id': self.meal.id, 'slot_id': self.slot.id, 'quantity': 1}, format='json', HTTP_IDEMPOTENCY_KEY='order-ticket-1')
        self.assertEqual(order_res.status_code, 200)
        ticket_token = order_res.data['ticket_token']
        staff_token = self._login('staff1@hit.ac.zw', 'Staff123!')
        self._auth(staff_token)
        s1 = self.client.post('/api/v1/tickets/validate-scan', {'token': ticket_token}, format='json')
        s2 = self.client.post('/api/v1/tickets/validate-scan', {'token': ticket_token}, format='json')
        self.assertEqual(s1.status_code, 200)
        self.assertEqual(s2.status_code, 400)
        self.assertTrue(FraudAlert.objects.filter(alert_type='duplicate_scan').exists())

    def test_admin_kpis_requires_admin_role(self):
        staff_token = self._login('staff1@hit.ac.zw', 'Staff123!')
        self._auth(staff_token)
        r_staff = self.client.get('/api/v1/admin/kpis')
        self.assertEqual(r_staff.status_code, 403)
        admin_token = self._login('admin1@hit.ac.zw', 'Admin123!')
        self._auth(admin_token)
        r_admin = self.client.get('/api/v1/admin/kpis')
        self.assertEqual(r_admin.status_code, 200)