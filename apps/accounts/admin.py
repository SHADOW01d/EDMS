from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm

from .models import User


class EDMSUserCreationForm(AdminUserCreationForm):
    role = forms.ChoiceField(choices=User.Role.choices, required=True)

    class Meta(AdminUserCreationForm.Meta):
        model = User
        fields = ("username", "role")


class EDMSUserChangeForm(UserChangeForm):
    role = forms.ChoiceField(
        choices=(("", "---------"), *User.Role.choices),
        required=False,
    )

    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and not self.instance.is_superuser:
            self.fields["role"].choices = User.Role.choices
            self.fields["role"].required = True


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = EDMSUserChangeForm
    add_form = EDMSUserCreationForm
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("EDMS access", {"fields": ("role",)}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("EDMS access", {"fields": ("role",)}),
    )
    list_display = ("username", "email", "first_name", "last_name", "role", "is_staff")
    list_filter = DjangoUserAdmin.list_filter + ("role",)
