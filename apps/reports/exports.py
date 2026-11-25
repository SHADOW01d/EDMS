import csv
from datetime import timedelta

from django.http import HttpResponse
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

from apps.customers.models import BranchDailyReport, BranchExpense, CustomerCall
from apps.inventory.models import StockLocation
from apps.sales.models import Sale


def _spreadsheet_safe(value):
    if isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def csv_response(filename, headers, rows):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow([_spreadsheet_safe(value) for value in headers])
    writer.writerows(
        [_spreadsheet_safe(value) for value in row]
        for row in rows
    )
    return response


def _money(value):
    return f"TZS {float(value or 0):,.2f}"


def branch_daily_report_pdf(start_date, end_date, branch="all"):
    from io import BytesIO

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title="Effective Diet - Daily Branch Report",
        author="Effective Diet Management System",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=23,
        textColor=colors.HexColor("#0A3A22"),
        alignment=TA_CENTER,
        spaceAfter=3 * mm,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#708174"),
        alignment=TA_CENTER,
        spaceAfter=6 * mm,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#0A3A22"),
        spaceBefore=4 * mm,
        spaceAfter=2 * mm,
    )

    branches = []
    if branch in ("all", "mwanza"):
        branches.append(("Mwanza", StockLocation.LocationType.BRANCH_MWANZA))
    if branch in ("all", "dar"):
        branches.append(("Dar es Salaam", StockLocation.LocationType.BRANCH_DAR))

    story = [
        Paragraph("EFFECTIVE DIET", title_style),
        Paragraph("DAILY BRANCH OPERATIONS REPORT", subtitle_style),
        Paragraph(
            f"Reporting period: {start_date.strftime('%d %B %Y')} - {end_date.strftime('%d %B %Y')}",
            ParagraphStyle("Period", parent=styles["Normal"], fontSize=9, alignment=TA_CENTER, textColor=colors.HexColor("#526157")),
        ),
        Spacer(1, 5 * mm),
    ]

    def branch_location(location_type):
        return StockLocation.objects.filter(location_type=location_type).first()

    day = start_date
    while day <= end_date:
        story.append(Paragraph(day.strftime("%A, %d %B %Y"), section_style))
        day_rows = []

        for branch_name, location_type in branches:
            location = branch_location(location_type)
            sales = Sale.objects.filter(location=location, sold_at__date=day) if location else Sale.objects.none()
            sales_total = sum((row.total_amount for row in sales), start=0)
            sales_count = sales.count()

            expenses = BranchExpense.objects.filter(location=location_type, expense_date=day)
            expense_total = sum((row.amount for row in expenses), start=0)

            call_filter = {
                "location": location,
            }
            calls = CustomerCall.objects.filter(called_at__date=day)
            if location:
                calls = calls.filter(location=location)
            else:
                calls = CustomerCall.objects.none()

            reports = BranchDailyReport.objects.filter(location=location_type, report_date=day)
            report = reports.first()

            day_rows.append([
                branch_name,
                str(sales_count),
                _money(sales_total),
                str(expenses.count()),
                _money(expense_total),
                str(calls.count()),
                report.get_status_display() if report else "Not submitted",
            ])

            if report:
                detail_rows = [["Report item", "Recorded value"]]
                detail_rows.extend([
                    ["Units sold", str(report.units_sold)],
                    ["Closing balance", str(report.closing_balance)],
                    ["Loss quantity", str(report.loss_quantity)],
                    ["Total / new / returning customers", f"{report.total_customers} / {report.new_customers} / {report.returning_customers}"],
                    ["Visitors / deliveries / parcels", f"{report.visitors} / {report.deliveries} / {report.parcels}"],
                    ["Instruction / compliance / follow-up calls", f"{report.instruction_calls} / {report.compliance_calls} / {report.followup_calls}"],
                    ["Customer areas", report.customer_addresses or "-"],
                    ["Submitted by", report.submitted_by.get_full_name() or report.submitted_by.username],
                    ["Approval status", report.get_status_display()],
                ])
                story.append(Paragraph(branch_name, styles["Heading3"]))
                detail_table = Table(detail_rows, colWidths=[76 * mm, 99 * mm], repeatRows=1)
                detail_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0A3A22")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD8CD")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F8F4")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]))
                story.append(detail_table)

            if sales.exists():
                sale_rows = [["Time", "Reference", "Customer", "Amount"]]
                for sale in sales.select_related("customer").prefetch_related("items__product"):
                    sale_rows.append([
                        timezone.localtime(sale.sold_at).strftime("%H:%M"),
                        sale.reference,
                        sale.customer.name if sale.customer else "Walk-in",
                        _money(sale.total_amount),
                    ])
                sale_table = Table(sale_rows, colWidths=[22 * mm, 43 * mm, 62 * mm, 48 * mm], repeatRows=1)
                sale_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DFF4E6")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0A3A22")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD8CD")),
                    ("ALIGN", (3, 1), (3, -1), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]))
                if not report:
                    story.append(Paragraph(branch_name, styles["Heading3"]))
                story.append(Spacer(1, 2 * mm))
                story.append(Paragraph("Sales transactions", styles["Heading4"]))
                story.append(sale_table)

            if expenses.exists():
                expense_rows = [["Category", "Description", "Amount"]]
                for expense in expenses:
                    expense_rows.append([expense.category, expense.description or "-", _money(expense.amount)])
                expense_table = Table(expense_rows, colWidths=[50 * mm, 75 * mm, 50 * mm], repeatRows=1)
                expense_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FFF2CC")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#7A5200")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD8CD")),
                    ("ALIGN", (2, 1), (2, -1), "RIGHT"),
                ]))
                if not report and not sales.exists():
                    story.append(Paragraph(branch_name, styles["Heading3"]))
                story.append(Spacer(1, 2 * mm))
                story.append(Paragraph("Expenses", styles["Heading4"]))
                story.append(expense_table)

            if calls.exists():
                call_rows = [["Time", "Contact", "Direction", "Type", "Outcome"]]
                for call in calls.select_related("customer", "called_by"):
                    call_rows.append([
                        timezone.localtime(call.called_at).strftime("%H:%M"),
                        call.contact_name,
                        call.get_direction_display(),
                        call.get_call_type_display() or "-",
                        call.outcome,
                    ])
                call_table = Table(call_rows, colWidths=[18 * mm, 36 * mm, 28 * mm, 42 * mm, 45 * mm], repeatRows=1)
                call_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E7F0FF")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1D4ED8")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD8CD")),
                ]))
                if not report and not sales.exists() and not expenses.exists():
                    story.append(Paragraph(branch_name, styles["Heading3"]))
                story.append(Spacer(1, 2 * mm))
                story.append(Paragraph("Customer calls", styles["Heading4"]))
                story.append(call_table)

        summary = Table(
            [["Branch", "Sales", "Sales amount", "Expenses", "Expense amount", "Calls", "Report"]] + day_rows,
            colWidths=[30 * mm, 14 * mm, 38 * mm, 18 * mm, 38 * mm, 14 * mm, 30 * mm],
            repeatRows=1,
        )
        summary.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0A3A22")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD8CD")),
            ("ALIGN", (1, 1), (5, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F8F4")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(summary)
        story.append(Spacer(1, 3 * mm))
        day += timedelta(days=1)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#708174"))
        canvas.setFont("Helvetica", 8)
        canvas.drawString(14 * mm, 8 * mm, "Effective Diet Management System")
        canvas.drawRightString(A4[0] - 14 * mm, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    filename = f"effective-diet-branches-{start_date.isoformat()}-to-{end_date.isoformat()}.pdf"
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response
