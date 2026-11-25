from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.contrib import messages
from django.urls import reverse, reverse_lazy
from django.utils import translation
from django.shortcuts import render, redirect

from apps.core.models import AuditEvent
from apps.core.services import record_audit_event
from .forms import EnglishAuthenticationForm, ProfileForm
from .models import User


class CustomLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EnglishAuthenticationForm
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        with translation.override("en"):
            return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.POST.get("remember_me"):
            self.request.session.set_expiry(60 * 60 * 24 * 14)
        else:
            self.request.session.set_expiry(0)
        return response

    def get_success_url(self):
        user = self.request.user
        if user.is_superuser:
            return reverse("admin:index")
        if user.role == User.Role.MANAGER:
            return reverse("manager_dashboard")
        if user.role == User.Role.FACTORY:
            return reverse("factory_dashboard")
        if user.role == User.Role.BRANCH_MWANZA:
            return reverse("mwanza_dashboard")
        if user.role == User.Role.BRANCH_DAR:
            return reverse("dar_dashboard")
        return reverse("home")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "EDMS — Login to System"
        return context


def _account_context(request):
    display_name = request.user.get_full_name() or request.user.username
    if request.user.is_superuser:
        dashboard_url = reverse("manager_dashboard")
        account_role = "CEO / Manager"
    elif request.user.role == User.Role.MANAGER:
        dashboard_url = reverse("manager_dashboard")
        account_role = "Manager / CEO"
    elif request.user.role == User.Role.FACTORY:
        dashboard_url = reverse("factory_dashboard")
        account_role = "Factory Manager"
    elif request.user.role == User.Role.BRANCH_MWANZA:
        dashboard_url = reverse("mwanza_dashboard")
        account_role = "Mwanza Branch Manager"
    elif request.user.role == User.Role.BRANCH_DAR:
        dashboard_url = reverse("dar_dashboard")
        account_role = "Dar Branch Manager"
    else:
        dashboard_url = reverse("home")
        account_role = "User"
    return {
        "dashboard_url": dashboard_url,
        "user_name": display_name,
        "user_initial": display_name[:1].upper(),
        "account_menu_role": account_role,
    }


@login_required(login_url="login")
def profile(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect("profile")
    else:
        form = ProfileForm(instance=request.user)

    context = _account_context(request)
    context["form"] = form
    return render(request, "accounts/profile.html", context)


class CustomPasswordChangeView(PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("login")

    def form_valid(self, form):
        super().form_valid(form)
        record_audit_event(
            actor=self.request.user,
            category=AuditEvent.Category.ACCOUNT,
            action="password.changed",
            object_type="User",
            object_id=self.request.user.pk,
            request=self.request,
        )
        auth_logout(self.request)
        return redirect("login")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_account_context(self.request))
        return context
