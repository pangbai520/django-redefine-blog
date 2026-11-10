"""Email activation tokens are separate from password reset credentials."""

from django.contrib.auth.tokens import PasswordResetTokenGenerator

from blog.models import PendingRegistration


class RegistrationTokenGenerator(PasswordResetTokenGenerator):
    key_salt = "blog.registration.activation"

    def check_token(self, user, token):
        if (
            not user
            or user.is_active
            or user.is_staff
            or user.is_superuser
            or not PendingRegistration.objects.filter(user=user).exists()
        ):
            return False
        return super().check_token(user, token)

    def _make_hash_value(self, user, timestamp):
        pending = PendingRegistration.objects.filter(user=user).first()
        registration = f"{pending.pk}:{pending.created_at.isoformat()}" if pending else ""
        return (
            super()._make_hash_value(user, timestamp)
            + f":{user.is_active}:{user.is_staff}:{user.is_superuser}:{registration}"
        )


registration_token_generator = RegistrationTokenGenerator()
