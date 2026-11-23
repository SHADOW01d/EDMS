from django.core.exceptions import ValidationError
from django.contrib.auth.forms import AuthenticationForm

from .models import User


class EnglishAuthenticationForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "Please enter a correct username and password.",
        "inactive": "This account is inactive.",
        "unassigned_role": "This account has no assigned EDMS role. Contact an administrator.",
    }

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        self.fields["username"].error_messages["required"] = "Please enter your username."
        self.fields["password"].error_messages["required"] = "Please enter your password."

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_superuser and user.role not in User.Role.values:
            raise ValidationError(
                self.error_messages["unassigned_role"],
                code="unassigned_role",
            )
