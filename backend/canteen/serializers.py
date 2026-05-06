from decimal import Decimal

from rest_framework import serializers


class RegisterSerializer(serializers.Serializer):
    university_id = serializers.CharField(min_length=5, max_length=32)
    full_name = serializers.CharField(max_length=120)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)
    role = serializers.ChoiceField(choices=['student', 'staff'], default='student')

    def validate_email(self, value):
        email = value.lower().strip()
        if not email.endswith('@hit.ac.zw'):
            raise serializers.ValidationError('Only official HIT email addresses can register.')
        return email


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class ProfileUpdateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=120)
    email = serializers.EmailField()

    def validate_email(self, value):
        email = value.lower().strip()
        if not email.endswith('@hit.ac.zw'):
            raise serializers.ValidationError('Only official HIT email addresses can be used.')
        return email


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(min_length=8, write_only=True)
    confirm_password = serializers.CharField(min_length=8, write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': ['New passwords do not match.']})
        return attrs


class TopUpInitiateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))
    provider = serializers.ChoiceField(choices=['mobile_money', 'bank_card'])
    phone_number = serializers.CharField(required=False, allow_blank=True, max_length=32)

    def validate(self, attrs):
        provider = attrs.get('provider')
        phone_number = str(attrs.get('phone_number') or '').strip()
        if provider == 'mobile_money' and not phone_number:
            raise serializers.ValidationError({'phone_number': ['Enter the mobile money phone number.']})
        attrs['phone_number'] = phone_number
        return attrs


class PaymentWebhookSerializer(serializers.Serializer):
    tx_id = serializers.CharField(max_length=64)
    provider_ref = serializers.CharField(max_length=128)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    status = serializers.ChoiceField(choices=['succeeded', 'failed'])


class PaynowOrderItemSerializer(serializers.Serializer):
    meal_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, max_value=5, default=1)


class OrderCreateSerializer(serializers.Serializer):
    meal_id = serializers.IntegerField(min_value=1, required=False)
    quantity = serializers.IntegerField(min_value=1, max_value=5, default=1)
    items = PaynowOrderItemSerializer(many=True, required=False)

    def validate(self, attrs):
        items = attrs.get('items') or []
        meal_id = attrs.get('meal_id')
        if items and meal_id:
            raise serializers.ValidationError({'items': ['Provide either a single meal or cart items, not both.']})
        if not items and not meal_id:
            raise serializers.ValidationError({'meal_id': ['Select a meal to order.']})
        return attrs


class PaynowOrderInitiateSerializer(serializers.Serializer):
    items = PaynowOrderItemSerializer(many=True)
    provider = serializers.ChoiceField(choices=['mobile_money', 'bank_card'])
    phone_number = serializers.CharField(required=False, allow_blank=True, max_length=32)

    def validate(self, attrs):
        provider = attrs.get('provider')
        phone_number = str(attrs.get('phone_number') or '').strip()
        if provider == 'mobile_money' and not phone_number:
            raise serializers.ValidationError({'phone_number': ['Enter the mobile money phone number.']})
        attrs['phone_number'] = phone_number
        return attrs


class ScanSerializer(serializers.Serializer):
    token = serializers.CharField()


class NotificationEmailSerializer(serializers.Serializer):
    recipient_email = serializers.EmailField(required=False)
    subject = serializers.CharField(max_length=180)
    body = serializers.CharField()
    category = serializers.CharField(max_length=40, required=False, default='general')


class AdminSettingsSerializer(serializers.Serializer):
    paynow_integration_id = serializers.CharField(max_length=120, allow_blank=True, required=False)
    paynow_return_url = serializers.URLField(allow_blank=True, required=False)
    smtp_host = serializers.CharField(max_length=255, allow_blank=True, required=False)
    default_from_email = serializers.EmailField(allow_blank=True, required=False)
    qr_expiry_minutes = serializers.IntegerField(min_value=1, max_value=1440, required=False)
    email_alerts_enabled = serializers.BooleanField(required=False)
    fraud_alerts_enabled = serializers.BooleanField(required=False)
    session_timeout_minutes = serializers.IntegerField(min_value=1, max_value=1440, required=False)


