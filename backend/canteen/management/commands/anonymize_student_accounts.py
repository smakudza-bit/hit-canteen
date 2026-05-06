from django.core.management.base import BaseCommand
from django.db import transaction

from canteen.models import CashDeposit, NotificationLog, User


DEMO_STUDENT_EMAIL = 'student@hit.ac.zw'
DEMO_PASSWORD = 'Demo@1234'


class Command(BaseCommand):
    help = 'Anonymize non-demo student accounts while preserving linked orders, wallets, and reports.'

    def handle(self, *args, **options):
        students = list(
            User.objects.filter(role='student')
            .exclude(email=DEMO_STUDENT_EMAIL)
            .order_by('id')
        )
        if not students:
            self.stdout.write(self.style.WARNING('No non-demo student accounts found to anonymize.'))
            return

        with transaction.atomic():
            for index, user in enumerate(students, start=1):
                original_email = user.email
                new_name = f'Sample Student {index:03d}'
                new_university_id = f'HITDEMO{index:03d}'
                new_email = f'{new_university_id.lower()}@hit.ac.zw'

                user.full_name = new_name
                user.university_id = new_university_id
                user.email = new_email
                user.is_email_verified = True
                user.is_suspended = False
                user.suspended_at = None
                user.set_password(DEMO_PASSWORD)
                user.save(
                    update_fields=[
                        'full_name',
                        'university_id',
                        'email',
                        'is_email_verified',
                        'is_suspended',
                        'suspended_at',
                        'password',
                    ]
                )

                CashDeposit.objects.filter(student=user).update(student_identifier=new_university_id)
                NotificationLog.objects.filter(user=user).update(recipient_email=new_email)

                self.stdout.write(f'Anonymized {original_email} -> {new_email}')

        self.stdout.write(self.style.SUCCESS(f'Anonymized {len(students)} student account(s).'))
