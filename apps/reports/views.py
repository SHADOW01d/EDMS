from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.http import FileResponse, Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.accounts.models import User

from .models import GeneratedReport
from .pdf import generate_report_pdf
from .services import build_report_data


def _require_manager(user):
    if not (user.is_superuser or user.role == User.Role.MANAGER):
        raise PermissionDenied("Only managers can generate or download PDF reports.")


def report_history_for_user(user):
    _require_manager(user)
    return GeneratedReport.objects.select_related("generated_by")


def _report_dates(request, report_kind):
    today = timezone.localdate()
    start_date = parse_date(request.GET.get("start_date", ""))
    end_date = parse_date(request.GET.get("end_date", ""))
    if report_kind == "daily":
        selected_date = end_date or start_date or today
        return selected_date, selected_date
    if report_kind == "weekly":
        end_date = end_date or today
        return end_date - timedelta(days=6), end_date
    if report_kind == "monthly":
        end_date = end_date or today
        return end_date - timedelta(days=29), end_date
    if report_kind == "custom":
        if not start_date or not end_date or start_date > end_date:
            raise ValueError("Choose a valid start and end date for a custom report.")
        return start_date, end_date
    raise ValueError("Choose Daily, Weekly, Monthly, or Custom report.")


def _selected_office(request):
    office = request.GET.get("office", GeneratedReport.Office.ALL)
    if office not in GeneratedReport.Office.values:
        raise ValueError("Choose All offices, Mwanza, or Dar es Salaam.")
    return office


def _filename(report):
    if report.report_type == GeneratedReport.ReportType.DAILY:
        return f"Effective_Diet_Daily_Report_{report.to_date.isoformat()}.pdf"
    return (
        f"Effective_Diet_Report_{report.from_date.isoformat()}_to_"
        f"{report.to_date.isoformat()}.pdf"
    )


@login_required(login_url="login")
def generate_report(request):
    _require_manager(request.user)
    try:
        report_kind = request.GET.get("report_type", "daily").strip().lower()
        from_date, to_date = _report_dates(request, report_kind)
        office = _selected_office(request)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))

    report_type = report_kind.upper()
    data = build_report_data(from_date, to_date, office)
    pdf_content = generate_report_pdf(data, report_type)
    report = GeneratedReport(
        report_type=report_type,
        from_date=from_date,
        to_date=to_date,
        office=office,
        generated_by=request.user,
    )
    report.file.save(_filename(report), ContentFile(pdf_content), save=True)
    report.file.open("rb")
    response = FileResponse(
        report.file,
        as_attachment=True,
        filename=_filename(report),
        content_type="application/pdf",
    )
    return response


@login_required(login_url="login")
def download_report(request, report_id):
    _require_manager(request.user)
    reports = GeneratedReport.objects.all()
    report = get_object_or_404(reports, pk=report_id)
    try:
        report.file.open("rb")
    except FileNotFoundError as exc:
        raise Http404("The saved report file is no longer available.") from exc
    return FileResponse(
        report.file,
        as_attachment=True,
        filename=_filename(report),
        content_type="application/pdf",
    )


def report_page_context(user, office):
    _require_manager(user)
    report_office = office
    reports = GeneratedReport.objects.select_related("generated_by")
    return {
        "report_history": reports[:10],
        "report_end_date": timezone.localdate(),
        "report_start_date": timezone.localdate() - timedelta(days=30),
        "report_office": "all" if report_office is None else report_office,
    }


def report_choices():
    return {
        "report_types": (
            ("daily", "Daily / Kila siku"),
            ("weekly", "Weekly / Wiki"),
            ("monthly", "Monthly / Mwezi"),
            ("custom", "Custom / Tarehe maalum"),
        ),
        "report_offices": GeneratedReport.Office.choices,
    }
