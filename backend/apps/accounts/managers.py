from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Phone-first accounts: the phone number is the login identifier; email is optional."""

    use_in_migrations = True

    def _create_user(self, phone_number, password, **extra):
        if not phone_number:
            raise ValueError("Phone number is required")
        email = extra.pop("email", None)
        user = self.model(
            phone_number=phone_number, email=self.normalize_email(email).lower() if email else None, **extra
        )
        user.set_password(password)  # None -> unusable: app users sign in with OTP + PIN, never a password
        user.save(using=self._db)
        return user

    def create_user(self, phone_number, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(phone_number, password, **extra)

    def create_superuser(self, phone_number, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if not extra["is_staff"] or not extra["is_superuser"]:
            raise ValueError("Superuser must have is_staff=True and is_superuser=True")
        return self._create_user(phone_number, password, **extra)

    def get_by_natural_key(self, phone_number):
        return self.get(phone_number=phone_number)
