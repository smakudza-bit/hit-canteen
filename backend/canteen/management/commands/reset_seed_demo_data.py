from datetime import datetime, timedelta, time
from decimal import Decimal
import random

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from canteen.models import (
    AdminSetting,
    AuditLog,
    CashDeposit,
    DailyDemandSnapshot,
    DailyReconciliationReport,
    FraudAlert,
    IdempotencyKey,
    Meal,
    MealTicket,
    NotificationLog,
    Order,
    PaymentTransaction,
    PickupSlot,
    User,
    Wallet,
    WalletLedgerEntry,
)
from canteen.utils import create_ticket, gen_tx_id


DEMO_PASSWORD = 'Demo@1234'
STUDENT_SEEDS = [
    ('Sample Student 001', 'HITDEMO001'),
    ('Sample Student 002', 'HITDEMO002'),
    ('Sample Student 003', 'HITDEMO003'),
    ('Sample Student 004', 'HITDEMO004'),
    ('Sample Student 005', 'HITDEMO005'),
    ('Sample Student 006', 'HITDEMO006'),
    ('Sample Student 007', 'HITDEMO007'),
    ('Sample Student 008', 'HITDEMO008'),
]
FRAUD_STUDENT_SEEDS = [
    ('Sample Student 009', 'HITDEMO009'),
    ('Sample Student 010', 'HITDEMO010'),
    ('Sample Student 011', 'HITDEMO011'),
]
MEAL_SEEDS = [
    ('Sadza + Beef Stew', 'Traditional meal with beef stew', Decimal('2.50'), 420),
    ('Rice + Chicken', 'Rice served with grilled chicken', Decimal('3.00'), 360),
    ('Veggie Plate', 'Healthy vegetarian option', Decimal('2.20'), 260),
    ('Chips + Sausage', 'Quick hot meal option', Decimal('2.80'), 240),
    ('Mazoe Orange', 'Fruit drink', Decimal('1.10'), 300),
    ('Water 500ml', 'Still water', Decimal('0.80'), 320),
]


class Command(BaseCommand):
    help = 'Reset canteen data and seed one month of demo records for testing.'

    def handle(self, *args, **options):
        rng = random.Random(240400)
        self.stdout.write('Resetting existing canteen data...')
        with transaction.atomic():
            self._reset_all_data()
            seeded = self._seed_demo_data(rng)
        self.stdout.write(self.style.SUCCESS(
            f"Demo data loaded successfully for {seeded['student_count']} provided students, "
            f"{seeded['order_count']} orders, and {seeded['payment_count']} payment records."
        ))

    def _reset_all_data(self):
        MealTicket.objects.all().delete()
        Order.objects.all().delete()
        PaymentTransaction.objects.all().delete()
        CashDeposit.objects.all().delete()
        WalletLedgerEntry.objects.all().delete()
        DailyDemandSnapshot.objects.all().delete()
        DailyReconciliationReport.objects.all().delete()
        NotificationLog.objects.all().delete()
        FraudAlert.objects.all().delete()
        AuditLog.objects.all().delete()
        IdempotencyKey.objects.all().delete()
        PickupSlot.objects.all().delete()
        Meal.objects.all().delete()
        Wallet.objects.all().delete()
        User.objects.all().delete()
        AdminSetting.objects.all().delete()

    def _seed_demo_data(self, rng):
        admin = self._create_user(
            email='admin@hit.ac.zw',
            full_name='System Admin',
            university_id='HITADMIN001',
            role='admin',
            is_staff=True,
            password=DEMO_PASSWORD,
        )
        staff = self._create_user(
            email='staff@hit.ac.zw',
            full_name='Canteen Staff',
            university_id='HITSTAFF001',
            role='staff',
            is_staff=True,
            password=DEMO_PASSWORD,
        )

        students = [
            self._create_user(
                email=f'{university_id.lower()}@hit.ac.zw',
                full_name=full_name,
                university_id=university_id,
                role='student',
                is_staff=False,
                password=DEMO_PASSWORD,
            )
            for full_name, university_id in STUDENT_SEEDS
        ]
        fraud_students = [
            self._create_user(
                email=f'{university_id.lower()}@hit.ac.zw',
                full_name=full_name,
                university_id=university_id,
                role='student',
                is_staff=False,
                password=DEMO_PASSWORD,
            )
            for full_name, university_id in FRAUD_STUDENT_SEEDS
        ]

        meals = {
            meal.name: meal
            for meal in [
                Meal.objects.create(name=name, description=description, price=price, stock_quantity=stock, active=True)
                for name, description, price, stock in MEAL_SEEDS
            ]
        }

        slots_by_date = {}
        today = timezone.localdate()
        for day_offset in range(-29, 8):
            slot_date = today + timedelta(days=day_offset)
            lunch = PickupSlot.objects.create(slot_date=slot_date, start_time=time(13, 0), end_time=time(13, 30), capacity=120)
            supper = PickupSlot.objects.create(slot_date=slot_date, start_time=time(17, 0), end_time=time(17, 30), capacity=120)
            slots_by_date[slot_date] = [lunch, supper]

        order_count = 0
        payment_count = 0
        topup_counter = 0
        order_counter = 0
        deposit_counter = 0

        for index, student in enumerate(students):
            wallet = student.wallet
            opening_amount = Decimal(str(18 + (index * 2)))
            opening_time = self._aware(today - timedelta(days=29), time(8, 30))
            self._create_topup(student, wallet, opening_amount, opening_time, provider='cash_seed', provider_ref=f'OPEN-{index + 1:03d}')
            payment_count += 1

            for day_offset in range(-29, 1):
                slot_date = today + timedelta(days=day_offset)
                if rng.random() < 0.23:
                    topup_counter += 1
                    deposit_amount = Decimal(str(rng.choice([5, 8, 10, 12, 15])))
                    deposit_time = self._aware(slot_date, time(9, rng.choice([5, 15, 25, 35, 45])))
                    if rng.random() < 0.55:
                        self._create_cash_deposit(student, wallet, staff, deposit_amount, deposit_time, topup_counter)
                    else:
                        self._create_topup(student, wallet, deposit_amount, deposit_time, provider=rng.choice(['mobile_money', 'bank_card', 'online_payment']), provider_ref=f'TOP-{topup_counter:04d}')
                        payment_count += 1

                order_attempts = rng.randint(0, 2)
                for _ in range(order_attempts):
                    available_meals = [meal for meal in meals.values() if meal.stock_quantity > 3]
                    if not available_meals:
                        break
                    meal = rng.choice(available_meals)
                    quantity = 1 if meal.price >= Decimal('2.80') else rng.choice([1, 1, 2])
                    if meal.stock_quantity < quantity:
                        continue
                    slot = rng.choice(slots_by_date[slot_date])
                    order_counter += 1
                    ordered_at = self._aware(slot_date, time(rng.choice([10, 11, 12, 15, 16]), rng.choice([0, 10, 20, 30, 40, 50])))
                    total_amount = meal.price * quantity
                    order_ref = f'ORD-DEMO-{order_counter:04d}'
                    order = Order.objects.create(
                        order_ref=order_ref,
                        user=student,
                        meal=meal,
                        slot=slot,
                        quantity=quantity,
                        total_amount=total_amount,
                        status='paid',
                        created_at=ordered_at,
                    )
                    token, qr_svg, expires_at = create_ticket(order.id, student.id, slot.id)
                    ticket = MealTicket.objects.create(
                        ticket_id=f'TKT-DEMO-{order_counter:04d}',
                        order=order,
                        token=token,
                        qr_svg=qr_svg,
                        status='issued',
                        expires_at=expires_at,
                    )
                    WalletLedgerEntry.objects.create(
                        wallet=wallet,
                        tx_id=f'DEBIT-DEMO-{order_counter:04d}',
                        entry_type='debit',
                        amount=total_amount,
                        provider='wallet',
                        note=f'Order payment {order_ref}',
                        created_at=ordered_at,
                    )
                    meal.stock_quantity -= quantity
                    meal.save(update_fields=['stock_quantity'])

                    if day_offset <= -2 and rng.random() < 0.82:
                        served_at = ordered_at + timedelta(hours=rng.choice([1, 2, 3]))
                        order.status = 'served'
                        order.save(update_fields=['status'])
                        ticket.status = 'redeemed'
                        ticket.redeemed_at = served_at
                        ticket.save(update_fields=['status', 'redeemed_at'])
                    elif day_offset <= -1:
                        ticket.status = 'expired'
                        ticket.save(update_fields=['status'])
                    order_count += 1

        fraud_payment_count = self._seed_suspicious_transactions(fraud_students, staff, today)
        self._seed_daily_reporting(today)
        self._seed_fraud_alerts(staff, fraud_students, today)
        return {
            'student_count': len(students) + len(fraud_students),
            'order_count': order_count,
            'payment_count': payment_count + fraud_payment_count,
        }

    def _create_user(self, *, email, full_name, university_id, role, is_staff, password):
        user = User.objects.create_user(
            email=email,
            password=password,
            university_id=university_id,
            full_name=full_name,
            role=role,
            is_staff=is_staff,
        )
        user.is_email_verified = True
        user.is_suspended = False
        user.suspended_at = None
        user.save(update_fields=['is_email_verified', 'is_suspended', 'suspended_at'])
        Wallet.objects.create(user=user)
        return user

    def _create_topup(self, user, wallet, amount, created_at, *, provider, provider_ref):
        tx_id = gen_tx_id('TOPUP')
        PaymentTransaction.objects.create(
            tx_id=tx_id,
            user=user,
            wallet=wallet,
            provider=provider,
            amount=amount,
            status='succeeded',
            purpose='wallet_topup',
            provider_ref=provider_ref,
            callback_verified=True,
            created_at=created_at,
            updated_at=created_at,
        )
        WalletLedgerEntry.objects.create(
            wallet=wallet,
            tx_id=tx_id,
            entry_type='credit',
            amount=amount,
            provider=provider,
            note=f'Demo wallet top-up via {provider.replace("_", " ")}',
            created_at=created_at,
        )

    def _create_cash_deposit(self, student, wallet, staff, amount, created_at, counter):
        CashDeposit.objects.create(
            student=student,
            student_identifier=student.university_id,
            amount=amount,
            cashier=staff,
            timestamp=created_at,
        )
        WalletLedgerEntry.objects.create(
            wallet=wallet,
            tx_id=f'CASH-DEMO-{counter:04d}',
            entry_type='credit',
            amount=amount,
            provider='cash_deposit',
            note=f'Cash deposit processed by {staff.full_name}',
            created_at=created_at,
        )

    def _seed_daily_reporting(self, today):
        start_date = today - timedelta(days=29)
        for offset in range(30):
            report_date = start_date + timedelta(days=offset)
            day_orders = Order.objects.filter(created_at__date=report_date)
            served_orders = day_orders.filter(status='served')
            paid_total = sum((order.total_amount for order in day_orders), Decimal('0.00'))
            successful_payments = PaymentTransaction.objects.filter(created_at__date=report_date, status='succeeded')
            payments_total = sum((payment.amount for payment in successful_payments), Decimal('0.00'))
            DailyReconciliationReport.objects.create(
                report_date=report_date,
                payments_received=payments_total,
                paid_orders_total=paid_total,
                meals_collected_total=sum(order.quantity for order in served_orders),
                successful_payments_count=successful_payments.count(),
                paid_orders_count=day_orders.count(),
                served_orders_count=served_orders.count(),
                discrepancy_amount=payments_total - paid_total,
                notes='Auto-generated demo reconciliation data.',
            )
            meal_totals = {}
            for order in day_orders:
                meal_totals[order.meal_id] = meal_totals.get(order.meal_id, 0) + order.quantity
            for meal_id, quantity in meal_totals.items():
                DailyDemandSnapshot.objects.create(
                    snapshot_date=report_date,
                    meal_id=meal_id,
                    orders_count=quantity,
                )

    def _seed_suspicious_transactions(self, fraud_students, staff, today):
        patterns = [
            ('mobile_money', Decimal('18.00'), 'failed', 'Repeated wallet top-up attempt blocked after invalid mobile money confirmation.'),
            ('bank_card', Decimal('24.50'), 'failed', 'Card payment rejected after mismatch between payer details and account owner.'),
            ('online_payment', Decimal('31.20'), 'failed', 'Gateway declined order payment after multiple rapid retries.'),
        ]
        count = 0
        for index, student in enumerate(fraud_students):
            wallet = student.wallet
            success_amount = Decimal(str(6 + index * 2))
            success_time = self._aware(today - timedelta(days=12 - index), time(8, 20))
            self._create_topup(student, wallet, success_amount, success_time, provider='mobile_money', provider_ref=f'FRAUD-SEED-{index + 1:03d}')
            count += 1

            provider, amount, status, note = patterns[index % len(patterns)]
            failed_time = self._aware(today - timedelta(days=4 - index), time(11 + index, 10))
            PaymentTransaction.objects.create(
                tx_id=gen_tx_id('FRD'),
                user=student,
                wallet=wallet,
                provider=provider,
                amount=amount,
                status=status,
                purpose='wallet_topup' if index != 2 else 'order_payment',
                meta_json={
                    'gateway_error': note,
                    'flagged_demo': True,
                    'review_reason': ['invalid_confirmation', 'identity_mismatch', 'rapid_retry'][index % 3],
                },
                provider_ref=f'FLAG-{index + 1:03d}',
                callback_verified=True,
                created_at=failed_time,
                updated_at=failed_time,
            )
            AuditLog.objects.create(
                actor_user=staff,
                action='flagged_demo_transaction',
                entity='payment_transaction',
                entity_id=f'{student.university_id}-{index + 1}',
                detail=f'student={student.university_id}, reason={note}',
                created_at=failed_time,
            )
            count += 1
        return count

    def _seed_fraud_alerts(self, staff, fraud_students, today):
        samples = [
            ('duplicate_ticket_scan', 'high', f'Repeated scan attempt detected during lunch service for {fraud_students[0].full_name}.'),
            ('rapid_ordering', 'medium', f'High-frequency ordering pattern flagged for review for {fraud_students[1].full_name}.'),
            ('payment_gateway_error', 'low', f'Online payment retry failed before confirmation for {fraud_students[2].full_name}.'),
        ]
        for index, (alert_type, severity, detail) in enumerate(samples, start=1):
            FraudAlert.objects.create(
                alert_type=alert_type,
                severity=severity,
                detail=f'{detail} Seeded demo alert #{index}.',
                created_at=self._aware(today - timedelta(days=index * 3), time(14, 15)),
            )
        AuditLog.objects.create(
            actor_user=staff,
            action='seed_demo_data',
            entity='system',
            entity_id='demo-seed',
            detail='Demo dataset generated for one-month testing window.',
            created_at=self._aware(today, time(7, 45)),
        )

    def _aware(self, day, clock):
        return timezone.make_aware(datetime.combine(day, clock), timezone.get_current_timezone())
