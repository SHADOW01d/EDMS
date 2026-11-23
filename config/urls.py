from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.urls import path
from django.views.generic import RedirectView

from apps.accounts import views as accounts_views
from apps.core import views as core_views
from apps.dashboard import views as dashboard_views

urlpatterns = [
    path("", accounts_views.CustomLoginView.as_view(), name="login"),
    path("home/", core_views.home, name="home"),
    path("dashboard/manager/", dashboard_views.manager_dashboard, name="manager_dashboard"),
    path(
        "dashboard/admin/",
        RedirectView.as_view(pattern_name="admin:index", permanent=False),
        name="dashboard_admin",
    ),
    path("dashboard/factory/", dashboard_views.factory_dashboard, name="factory_dashboard"),
    path("dashboard/branch/mwanza/", dashboard_views.mwanza_dashboard, name="mwanza_dashboard"),
    path("dashboard/branch/dar/", dashboard_views.dar_dashboard, name="dar_dashboard"),
    path(
        "mwanza_manager.html",
        RedirectView.as_view(pattern_name="mwanza_dashboard", permanent=False),
        name="mwanza-manager-page",
    ),
    path(
        "dar_manager.html",
        RedirectView.as_view(pattern_name="dar_dashboard", permanent=False),
        name="dar-manager-page",
    ),
    path(
        "kiwandani.html",
        dashboard_views.factory_standalone_dashboard,
        name="factory-workspace-page",
    ),
    path("logout/", LogoutView.as_view(next_page="login"), name="logout"),
    path("admin/", admin.site.urls),
    path("sw.js", core_views.service_worker, name="service-worker"),
    path("manifest.json", core_views.web_manifest, name="web-manifest"),
    path("offline/", core_views.offline, name="offline"),
    path("operations/purchases/record/", dashboard_views.record_purchase, name="record_purchase"),
    path("operations/purchases/<int:purchase_id>/receive/", dashboard_views.receive_saved_purchase, name="receive_saved_purchase"),
    path("operations/production/record/", dashboard_views.record_production, name="record_production"),
    path("operations/transfers/record/", dashboard_views.record_dispatch, name="record_dispatch"),
    path("operations/transfers/<int:transfer_id>/receive/", dashboard_views.receive_transfer, name="receive_transfer"),
    path("operations/sales/record/", dashboard_views.record_sale, name="record_sale"),
    path("operations/expenses/record/", dashboard_views.record_expense, name="record_expense"),
    path("operations/customers/record/", dashboard_views.record_customer, name="record_customer"),
    path("operations/calls/record/", dashboard_views.record_call, name="record_call"),
    path("operations/loss/record/", dashboard_views.record_loss, name="record_loss"),
    path("operations/reports/submit/", dashboard_views.submit_daily_report, name="submit_daily_report"),
    path("operations/reports/<int:report_id>/approve/", dashboard_views.approve_daily_report, name="approve_daily_report"),
    path("operations/batches/<int:batch_id>/cancel/", dashboard_views.cancel_production, name="cancel_production"),
    path("catalog/products/<int:product_id>/update/", dashboard_views.update_catalog_product, name="update_catalog_product"),
    path("reports/manager/export/", dashboard_views.export_manager_report, name="export_manager_report"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
