from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        # Use getattr so custom-user fields remain safe for runtime and editor type-checking.
        return f"{user.pk}{timestamp}{getattr(user, 'is_email_verified', False)}"


email_verification_token = EmailVerificationTokenGenerator()
