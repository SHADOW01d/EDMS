from django.contrib.auth.views import LoginView
from django.urls import reverse
from django.utils import translation

from .forms import EnglishAuthenticationForm
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
