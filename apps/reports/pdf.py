from decimal import Decimal
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Image as PdfImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from apps.customers.models import CustomerCall


GREEN = "#0F4A2E"
BRIGHT_GREEN = "#16A34A"
AMBER = "#F59E0B"
BLUE = "#3B82F6"
RED = "#DC2626"
LIGHT = "#F1F7F3"
BORDER = "#DCE7DF"
LIME = "#C6F135"
MUTED = "#607268"
BRANCH_COLORS = {"mwanza": BRIGHT_GREEN, "dar": AMBER}
ZERO = Decimal("0")
ASSETS = Path(__file__).resolve().parent / "assets"
PAGE_WIDTH, PAGE_HEIGHT = A4
CONTENT_WIDTH = PAGE_WIDTH - 30 * mm
_FONTS_REGISTERED = False


def _register_fonts():
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    pdfmetrics.registerFont(TTFont("Poppins", str(ASSETS / "Poppins-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Poppins-Medium", str(ASSETS / "Poppins-Medium.ttf")))
    pdfmetrics.registerFont(TTFont("Poppins-Bold", str(ASSETS / "Poppins-Bold.ttf")))
    pdfmetrics.registerFontFamily(
        "Poppins",
        normal="Poppins",
        bold="Poppins-Bold",
        italic="Poppins",
        boldItalic="Poppins-Bold",
    )
    _FONTS_REGISTERED = True


def _font(size, weight="regular"):
    file_name = {
        "regular": "Poppins-Regular.ttf",
        "medium": "Poppins-Medium.ttf",
        "bold": "Poppins-Bold.ttf",
    }[weight]
    return ImageFont.truetype(str(ASSETS / file_name), size)


def _chart(title, labels, series, kind="bar"):
    width, height = 1600, 660
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = _font(32, "bold")
    label_font = _font(21)
    legend_font = _font(20, "medium")
    draw.text((36, 22), title, fill=GREEN, font=title_font)
    series = [
        (name, [float(value or 0) for value in values], color)
        for name, values, color in series
    ]
    if not labels or not any(value for _name, values, _color in series for value in values):
        draw.text((width // 2, height // 2), "No data for this period", fill=MUTED, font=label_font, anchor="mm")
        return _chart_png(image)

    left, top, right, bottom = 105, 105, 1390, 545
    if kind == "donut":
        total = sum(values[0] for _name, values, _color in series)
        center = (490, 365)
        radius = 235
        start = -90
        for _name, values, color in series:
            extent = (values[0] / total * 360) if total else 0
            draw.pieslice(
                (center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius),
                start,
                start + extent,
                fill=color,
                outline="white",
                width=5,
            )
            start += extent
        inner = 128
        draw.ellipse(
            (center[0] - inner, center[1] - inner, center[0] + inner, center[1] + inner),
            fill="white",
        )
        draw.text(center, f"{total:,.0f}", fill=GREEN, font=_font(34, "bold"), anchor="mm")
        for index, (name, values, color) in enumerate(series):
            y = 235 + index * 64
            draw.rounded_rectangle((985, y, 1018, y + 30), radius=7, fill=color)
            draw.text((1040, y - 2), name, fill=GREEN, font=legend_font)
            draw.text((1370, y - 2), f"{values[0]:,.0f}", fill=MUTED, font=legend_font, anchor="ra")
        return _chart_png(image)

    if kind == "stacked":
        maximum = max(
            (
                sum(values[index] for _name, values, _color in series if index < len(values))
                for index in range(len(labels))
            ),
            default=0,
        )
    else:
        maximum = max((value for _name, values, _color in series for value in values), default=0)
    maximum = maximum or 1
    grid_font = _font(17)

    if kind == "horizontal":
        left, right = 540, 1430
        max_label_width = left - 44
        for step in range(5):
            x = left + (right - left) * step / 4
            draw.line((x, top, x, bottom), fill="#E7EFE9", width=2)
            draw.text(
                (x, bottom + 8),
                f"{maximum * step / 4:,.0f}",
                fill=MUTED,
                font=grid_font,
                anchor="mt",
            )
        row_count = max(len(labels), 1)
        row_height = (bottom - top) / row_count
        for index, label in enumerate(labels):
            y = top + row_height * (index + 0.5)
            safe_label = str(label)
            while draw.textlength(safe_label, font=label_font) > max_label_width:
                safe_label = safe_label[:-2].rstrip() + "…"
            draw.text((left - 18, y), safe_label, fill=MUTED, font=label_font, anchor="rm")
            for series_index, (name, values, color) in enumerate(series):
                if index >= len(values):
                    continue
                bar_height = max(13, min(34, row_height / max(len(series), 1) - 6))
                offset = (series_index - (len(series) - 1) / 2) * (bar_height + 3)
                y1 = y + offset - bar_height / 2
                bar_width = (right - left) * values[index] / maximum
                draw.rounded_rectangle((left, y1, left + bar_width, y1 + bar_height), radius=6, fill=color)
                draw.text((left + bar_width + 10, y1 + bar_height / 2), f"{values[index]:,.0f}", fill=MUTED, font=grid_font, anchor="lm")
        return _chart_png(image)

    for step in range(5):
        y = bottom - (bottom - top) * step / 4
        draw.line((left, y, right, y), fill="#E7EFE9", width=2)
        draw.text((left - 14, y), f"{maximum * step / 4:,.0f}", fill=MUTED, font=grid_font, anchor="rm")

    if kind != "horizontal":
        groups = max(len(labels), 1)
        group_width = (right - left) / groups
        bar_width = max(10, group_width * 0.72 / max(len(series), 1))
        for index, label in enumerate(labels):
            x_center = left + group_width * (index + 0.5)
            if kind == "line":
                for series_index, (name, values, color) in enumerate(series):
                    if index >= len(values):
                        continue
                    x = x_center
                    y = bottom - (bottom - top) * values[index] / maximum
                    if index:
                        previous_value = values[index - 1]
                        previous_x = left + group_width * (index - 0.5)
                        previous_y = bottom - (bottom - top) * previous_value / maximum
                        draw.line((previous_x, previous_y, x, y), fill=color, width=6)
                    draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=color)
            elif kind == "stacked":
                running_top = bottom
                for _name, values, color in series:
                    value = values[index] if index < len(values) else 0
                    bar_height = (bottom - top) * value / maximum
                    draw.rectangle(
                        (x_center - group_width * 0.28, running_top - bar_height, x_center + group_width * 0.28, running_top),
                        fill=color,
                    )
                    running_top -= bar_height
            else:
                for series_index, (_name, values, color) in enumerate(series):
                    if index >= len(values):
                        continue
                    x = x_center + (series_index - (len(series) - 1) / 2) * bar_width
                    bar_height = (bottom - top) * values[index] / maximum
                    draw.rounded_rectangle((x - bar_width / 2, bottom - bar_height, x + bar_width / 2, bottom), radius=5, fill=color)
            if groups <= 12 or index in (0, groups - 1) or index % max(groups // 8, 1) == 0:
                label_value = str(label)
                if len(label_value) > 12:
                    label_value = label_value[:10] + "…"
                draw.text((x_center, bottom + 16), label_value, fill=MUTED, font=grid_font, anchor="mt")

    legend_y = 600
    legend_x = left
    for name, _values, color in series:
        draw.rounded_rectangle((legend_x, legend_y, legend_x + 26, legend_y + 22), radius=5, fill=color)
        draw.text((legend_x + 38, legend_y - 4), name, fill=GREEN, font=legend_font)
        legend_x += 38 + draw.textlength(name, font=legend_font) + 32
    return _chart_png(image)


def _chart_png(image):
    buffer = BytesIO()
    image.save(buffer, format="PNG", dpi=(240, 240), optimize=True)
    buffer.seek(0)
    return buffer


def _paragraph_styles():
    common = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=common["Title"],
            fontName="Poppins-Bold",
            fontSize=17,
            leading=21,
            textColor=colors.white,
            alignment=TA_LEFT,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=common["Normal"],
            fontName="Poppins",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#E3F2E8"),
        ),
        "section": ParagraphStyle(
            "ReportSection",
            parent=common["Heading2"],
            fontName="Poppins-Bold",
            fontSize=12,
            leading=15,
            textColor=colors.HexColor(GREEN),
            spaceBefore=2 * mm,
            spaceAfter=2 * mm,
        ),
        "body": ParagraphStyle(
            "ReportBody",
            parent=common["BodyText"],
            fontName="Poppins",
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor("#304238"),
        ),
        "small": ParagraphStyle(
            "ReportSmall",
            parent=common["BodyText"],
            fontName="Poppins",
            fontSize=6.5,
            leading=8.5,
            textColor=colors.HexColor("#304238"),
        ),
        "table_header": ParagraphStyle(
            "ReportTableHeader",
            parent=common["BodyText"],
            fontName="Poppins-Bold",
            fontSize=6.4,
            leading=8,
            textColor=colors.white,
        ),
        "card_label": ParagraphStyle(
            "ReportCardLabel",
            parent=common["BodyText"],
            fontName="Poppins-Medium",
            fontSize=6.6,
            leading=8,
            textColor=colors.HexColor(MUTED),
        ),
        "card_value": ParagraphStyle(
            "ReportCardValue",
            parent=common["BodyText"],
            fontName="Poppins-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor(GREEN),
        ),
        "center": ParagraphStyle(
            "ReportCenter",
            parent=common["BodyText"],
            fontName="Poppins",
            fontSize=7,
            leading=9,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#304238"),
        ),
    }


def _money(value):
    return f"TZS {Decimal(value or 0):,.0f}"


def _number(value):
    if value is None:
        return "-"
    value = Decimal(value)
    return f"{value:,.0f}" if value == value.to_integral_value() else f"{value:,.2f}"


def _percent(value):
    return "n/a" if value is None else f"{Decimal(value):.1f}%"


def _date(value):
    return value.strftime("%d/%m/%Y")


def _safe(value):
    return escape(str(value if value not in (None, "") else "-"))


def _section(title, subtitle, styles):
    return Paragraph(f"{_safe(title)} <font name='Poppins' size='8' color='{MUTED}'>/ {_safe(subtitle)}</font>", styles["section"])


def _cards(cards, styles, columns=3):
    width = CONTENT_WIDTH / columns
    cells = []
    for label, value, note in cards:
        inner = Table(
            [[Paragraph(_safe(label), styles["card_label"])],
             [Paragraph(_safe(value), styles["card_value"])],
             [Paragraph(_safe(note), styles["small"])]],
            colWidths=[width - 7 * mm],
        )
        inner.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2 * mm),
        ]))
        cells.append(inner)
    rows = [cells[index:index + columns] for index in range(0, len(cells), columns)]
    for row in rows:
        row.extend([""] * (columns - len(row)))
    table = Table(rows, colWidths=[width] * columns, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(LIGHT)),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(BORDER)),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, colors.HexColor(BORDER)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3.5 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2.4 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5 * mm),
    ]))
    return table


def _table(rows, widths, styles, numeric_columns=(), totals_row=False):
    if len(rows) == 1:
        return Paragraph("No data for this period.", styles["body"])
    converted = []
    for row_index, row in enumerate(rows):
        converted_row = []
        for column_index, value in enumerate(row):
            if isinstance(value, Paragraph):
                converted_row.append(value)
                continue
            cell_style = styles["table_header"] if row_index == 0 else styles["small"]
            if row_index and column_index in numeric_columns:
                cell_style = ParagraphStyle(
                    f"RightCell{row_index}-{column_index}",
                    parent=cell_style,
                    alignment=TA_RIGHT,
                )
            converted_row.append(Paragraph(_safe(value), cell_style))
        converted.append(converted_row)
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(GREEN)),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor(BORDER)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F9F7")]),
    ]
    if totals_row and len(rows) > 1:
        commands.extend([
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E8F4EB")),
            ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.HexColor(GREEN)),
        ])
    result = Table(converted, colWidths=widths, repeatRows=1, hAlign="LEFT")
    result.setStyle(TableStyle(commands))
    return result


def _image(buffer, width, height):
    image = PdfImage(buffer, width=width, height=height)
    image.hAlign = "CENTER"
    return image


def _legend_series(data, field, series_offices=None):
    selected = series_offices or data["offices"]
    return [
        (
            office["label"],
            [
                row.get("offices", {}).get(office["key"], {}).get(field, 0)
                for row in data["daily_sales"]
            ],
            office["color"],
        )
        for office in selected
    ]


def _hero(data, report_type, styles):
    logo = PdfImage(str(ASSETS / "logo.png"), width=26 * mm, height=16 * mm)
    title = "Daily Management Report" if report_type == "DAILY" else "Management Report"
    subtitle = "Ripoti ya kila siku" if report_type == "DAILY" else "Ripoti ya usimamizi"
    heading = [
        Paragraph(title, styles["title"]),
        Paragraph(subtitle, styles["subtitle"]),
    ]
    header = Table([[logo, heading]], colWidths=[34 * mm, CONTENT_WIDTH - 34 * mm])
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(GREEN)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 * mm),
    ]))
    office_chips = "  |  ".join(office["label"] for office in data["offices"])
    period = _date(data["from_date"]) if data["from_date"] == data["to_date"] else f"{_date(data['from_date'])} - {_date(data['to_date'])}"
    chips = Table(
        [[Paragraph(f"<b>PERIOD</b>  {period}", styles["small"]),
          Paragraph(f"<b>OFFICE</b>  {_safe(office_chips)}", styles["small"])]],
        colWidths=[CONTENT_WIDTH * 0.52, CONTENT_WIDTH * 0.48],
    )
    chips.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EAF3EC")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(BORDER)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
    ]))
    return [header, Spacer(1, 2 * mm), chips, Spacer(1, 3 * mm)]


def _page_header(canvas_obj, doc):
    if doc.page > 1:
        canvas_obj.saveState()
        canvas_obj.setFillColor(colors.HexColor(GREEN))
        canvas_obj.rect(0, PAGE_HEIGHT - 3.5 * mm, PAGE_WIDTH, 3.5 * mm, fill=1, stroke=0)
        canvas_obj.drawImage(
            str(ASSETS / "logo.png"),
            15 * mm,
            PAGE_HEIGHT - 18 * mm,
            width=18 * mm,
            height=11 * mm,
            preserveAspectRatio=True,
            mask="auto",
        )
        canvas_obj.setFillColor(colors.HexColor(GREEN))
        canvas_obj.setFont("Poppins-Medium", 8)
        canvas_obj.drawRightString(PAGE_WIDTH - 15 * mm, PAGE_HEIGHT - 13 * mm, "EFFECTIVE DIET  |  MANAGEMENT REPORT")
        canvas_obj.restoreState()


class _NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._states = []

    def showPage(self):
        self._states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_total = len(self._states)
        for state in self._states:
            self.__dict__.update(state)
            self.saveState()
            self.setStrokeColor(colors.HexColor(BORDER))
            self.line(15 * mm, 12 * mm, PAGE_WIDTH - 15 * mm, 12 * mm)
            self.setFillColor(colors.HexColor(MUTED))
            self.setFont("Poppins", 6.5)
            self.drawString(
                15 * mm,
                7 * mm,
                "Effective Diet | Stay Healthy, Be Productive | Confidential - for management use",
            )
            self.drawRightString(PAGE_WIDTH - 15 * mm, 7 * mm, f"Page {self._pageNumber} of {page_total}")
            self.restoreState()
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)


def _daily_compare_chart(data):
    labels = [office["label"] for office in data["offices"]]
    series = [
        ("Report date", [branch["sales_last_day"] for branch in data["branches"]], BRIGHT_GREEN),
        ("Previous day", [branch["sales_yesterday"] for branch in data["branches"]], AMBER),
    ]
    return _chart("Selected day vs previous day", labels, series)


def _branch_value_series(branches, value_key):
    return [
        (
            branch["name"],
            [
                branch[value_key] if index == branch_index else 0
                for index in range(len(branches))
            ],
            branch["color"],
        )
        for branch_index, branch in enumerate(branches)
    ]


def _period_pages(data, styles):
    story = []
    story.extend(_hero(data, "PERIOD", styles))
    story.append(_section("Executive Summary", "Muhtasari wa Utendaji", styles))
    story.append(_cards([
        ("Total sales / Mauzo ya kipindi", _money(data["sales_total"]), "Selected period"),
        ("Sales today / Mauzo leo", _money(data["sales_today"]), f"Last report day: {_money(data['sales_last_day'])}"),
        ("Units produced / Uzalishaji", _number(data["produced_total"]), "All-time production"),
        ("Units in stock / Stock", _number(data["current_stock"]), "Current finished-goods stock"),
        ("Customers served / Wateja", _number(data["customers_served"]), "Unique customers in period"),
        ("Losses / Hasara", _number(data["loss_total"]), "Recorded in selected period"),
    ], styles))
    story.append(Spacer(1, 3 * mm))
    dates = [row["date"].strftime("%d/%m") for row in data["daily_sales"]]
    trend = _chart(
        "Daily sales trend by branch",
        dates,
        _legend_series(data, "sales"),
        "line",
    )
    stock_distribution = _chart(
        "Closing stock distribution",
        ["Stock"],
        [
            *(
                [("Store", [data["store_stock"]], GREEN)]
                if data["store_stock"] is not None
                else []
            ),
            *[
                (branch["name"], [branch["stock"]], branch["color"])
                for branch in data["branches"]
            ],
        ],
        "donut",
    )
    story.append(Table(
        [[_image(trend, 88 * mm, 45 * mm), _image(stock_distribution, 88 * mm, 45 * mm)]],
        colWidths=[CONTENT_WIDTH / 2] * 2,
        style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]),
    ))
    story.append(_section("Key Highlights", "Mambo Muhimu", styles))
    highlights = [
        f"Sales for the full selected period: {_money(data['sales_total'])}.",
        f"Finished goods produced: {_number(data['produced_total'])}; current tangible stock: {_number(data['current_stock'])}.",
        f"Customers served: {_number(data['customers_served'])}; recorded losses: {_number(data['loss_total'])}.",
    ]
    if data["reconciliation_warnings"]:
        highlights.append("Stock reconciliation needs review for: " + ", ".join(row["name"] for row in data["reconciliation_warnings"]) + ".")
    story.extend(Paragraph(f"• {_safe(line)}", styles["body"]) for line in highlights)

    story.append(PageBreak())
    story.append(_section("Sales Performance", "Utendaji wa Mauzo", styles))
    story.append(_cards([
        ("Period sales / Mauzo", _money(data["sales_total"]), "All selected dates"),
        ("Sales on last day / Siku ya mwisho", _money(data["sales_last_day"]), f"Vs previous day: {_percent(data['sales_change_percent'])}"),
        ("Units sold / Vilivyouzwa", _number(data["units_sold"]), "All sold products"),
        ("Customers / Wateja", _number(data["customers_served"]), "Unique in period"),
        ("Recorded losses / Hasara", _number(data["loss_total"]), "Selected period"),
        ("Average line price / Bei wastani", _money(_average_price(data)), "Weighted by sold units"),
    ], styles))
    branch_rows = [["Branch", "Sales (TZS)", "Share", "Units sold", "Customers", "Loss"]]
    for branch in data["branches"]:
        branch_rows.append([
            branch["name"],
            _money(branch["sales"]),
            _percent(branch["share_percent"]),
            _number(branch["units_sold"]),
            _number(branch["customers"]),
            _number(branch["loss"]),
        ])
    branch_rows.append([
        "TOTAL",
        _money(data["sales_total"]),
        "100.0%" if data["sales_total"] else "n/a",
        _number(sum((branch["units_sold"] for branch in data["branches"]), Decimal("0"))),
        "-",
        _number(data["loss_total"]),
    ])
    story.append(Spacer(1, 3 * mm))
    story.append(_table(branch_rows, [85, 100, 49, 65, 75, 58], styles, numeric_columns=(1, 2, 3, 4, 5), totals_row=True))
    product_rows = [["Product", "Units sold", "Revenue", "Average price", *[branch["name"] for branch in data["branches"]]]]
    for product in data["products"]:
        product_rows.append([
            product["name"],
            _number(product["quantity_sold"]),
            _money(product["revenue"]),
            _money(product["average_price"]) if product["average_price"] is not None else "-",
            *[_number(product["sold_by_office"][branch["key"]]) for branch in data["branches"]],
        ])
    product_revenue = sum((row["revenue"] for row in data["products"]), Decimal("0"))
    product_quantities = sum((row["quantity_sold"] for row in data["products"]), Decimal("0"))
    product_rows.append([
        "TOTAL",
        _number(product_quantities),
        _money(product_revenue),
        _money(product_revenue / product_quantities) if product_quantities else "-",
        *[
            _number(sum(
                (row["sold_by_office"][branch["key"]] for row in data["products"]),
                Decimal("0"),
            ))
            for branch in data["branches"]
        ],
    ])
    table_widths = [128, 62, 90, 92] + [69] * len(data["branches"])
    story.append(Spacer(1, 2 * mm))
    story.append(_table(product_rows, table_widths, styles, numeric_columns=tuple(range(1, len(product_rows[0]))), totals_row=True))
    sales_chart = _chart(
        "Sales by branch (TZS)",
        [branch["name"] for branch in data["branches"]],
        _branch_value_series(data["branches"], "sales"),
    )
    product_chart = _chart(
        "Units sold by product",
        [product["name"] for product in data["products"]],
        [("Units sold", [product["quantity_sold"] for product in data["products"]], BLUE)],
        "horizontal",
    )
    story.append(Spacer(1, 2 * mm))
    story.append(Table(
        [[_image(sales_chart, 88 * mm, 40 * mm), _image(product_chart, 88 * mm, 40 * mm)]],
        colWidths=[CONTENT_WIDTH / 2] * 2,
        style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]),
    ))
    story.append(Paragraph(
        "Reading the numbers: totals are from recorded sales; unit prices and revenue by product use each saved sale-line price. Gross margin is not shown because verified production costs are not available.",
        styles["small"],
    ))

    story.append(PageBreak())
    story.append(_section("Stock & Inventory", "Stock na Bidhaa", styles))
    story.append(_cards([
        ("Produced / Zilizozalishwa", _number(data["produced_total"]), "All-time tangible finished goods"),
        ("Current stock / Zilizopo", _number(data["current_stock"]), "Visible offices"),
        ("Store stock / Ghala", _number(data["store_stock"]) if data["store_stock"] is not None else "-", "Not included in branch-only view"),
        ("Stock alerts / Tahadhari", _number(len(data["stock_alerts"])), "At or below reorder level"),
    ], styles))
    stock_rows = [["Product", "Produced", *(
        ["Store"] if data["office"] == "all" else []
    ), *[office["label"] for office in data["offices"]], "Current", "In stock %"]]
    for row in data["tangible_products"]:
        stock_rows.append([
            row["name"],
            _number(row["produced"]),
            *([_number(row["store_stock"])] if data["office"] == "all" else []),
            *[_number(row["stock_by_location"].get(office["location_type"], 0)) for office in data["offices"]],
            _number(row["current_stock"]),
            _percent(row["stock_percent"]),
        ])
    stock_total_by_location = {
        office["location_type"]: sum(
            (row["stock_by_location"].get(office["location_type"], ZERO) for row in data["tangible_products"]),
            Decimal("0"),
        )
        for office in data["offices"]
    }
    stock_totals = [
        "TOTAL",
        _number(data["produced_total"]),
        *(
            [_number(data["store_stock"])]
            if data["office"] == "all"
            else []
        ),
        *[
            _number(stock_total_by_location[office["location_type"]])
            for office in data["offices"]
        ],
        _number(data["current_stock"]),
        _percent(
            data["current_stock"] / data["produced_total"] * Decimal("100")
            if data["produced_total"]
            else None
        ),
    ]
    if len(stock_rows) == 1:
        stock_rows.append(["No data for this period"] + ["-"] * (len(stock_rows[0]) - 1))
    else:
        stock_rows.append(stock_totals)
    remaining_width = CONTENT_WIDTH - 128
    stock_widths = [128] + [remaining_width / (len(stock_rows[0]) - 1)] * (len(stock_rows[0]) - 1)
    story.append(_table(stock_rows, stock_widths, styles, numeric_columns=tuple(range(1, len(stock_rows[0]))), totals_row=True))
    stock_series = [
        (name, [row["stock_by_location"].get(location_type, 0) for row in data["tangible_products"]], color)
        for name, location_type, color in (
            [("Store", "FACTORY", GREEN)] if data["office"] == "all" else []
        ) + [
            (office["label"], office["location_type"], office["color"])
            for office in data["offices"]
        ]
    ]
    labels = [row["name"] for row in data["tangible_products"]]
    inventory_chart = _chart("Stock by location", labels, stock_series, "stacked")
    produced_chart = _chart(
        "Produced vs current stock",
        labels,
        [
            ("Produced", [row["produced"] for row in data["tangible_products"]], BLUE),
            ("Current stock", [row["current_stock"] for row in data["tangible_products"]], BRIGHT_GREEN),
        ],
    )
    story.append(Spacer(1, 2 * mm))
    story.append(Table(
        [[_image(inventory_chart, 88 * mm, 39 * mm), _image(produced_chart, 88 * mm, 39 * mm)]],
        colWidths=[CONTENT_WIDTH / 2] * 2,
        style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]),
    ))
    branch_stock_chart = _chart(
        "Closing balance by branch",
        [branch["name"] for branch in data["branches"]],
        [("Closing stock", [branch["stock"] for branch in data["branches"]], AMBER)],
    )
    story.append(_image(branch_stock_chart, 105 * mm, 32 * mm))
    alerts = data["stock_alerts"]
    story.append(Paragraph(
        "Stock alerts: " + (
            ", ".join(f"{row['name']} ({_number(row['current_stock'])} left)" for row in alerts)
            if alerts else "No products are at or below reorder level."
        ),
        styles["body"],
    ))

    story.append(PageBreak())
    story.append(_section("Branch Detail", "Taarifa za Matawi", styles))
    for branch in data["branches"]:
        story.append(Paragraph(_safe(branch["name"]), styles["section"]))
        story.append(_cards([
            ("Closing stock / Stock", _number(branch["stock"]), "Current branch balance"),
            ("Sales / Mauzo", _money(branch["sales"]), "Selected period"),
            ("Pending transfers / Mizigo", _number(branch["pending_transfers"]), "Awaiting receipt"),
            ("Loss / Hasara", _number(branch["loss"]), "Selected period"),
        ], styles, columns=4))
        stock_detail = [["Product", "Sold", "Balance", "Loss"]]
        for row in data["tangible_products"]:
            stock_detail.append([
                row["name"],
                _number(row["sold_by_office"].get(branch["key"], 0)),
                _number(row["stock_by_location"].get(branch["location"].location_type, 0) if branch["location"] else 0),
                _number(row["loss_by_office"].get(branch["key"], 0)),
            ])
        stock_detail.append([
            "TOTAL",
            _number(branch["units_sold"]),
            _number(branch["stock"]),
            _number(branch["loss"]),
        ])
        story.append(_table(stock_detail, [235, 85, 95, 95], styles, numeric_columns=(1, 2, 3), totals_row=True))
        activity_rows = [
            ["Customer activity", "Count"],
            ["New customers", _number(branch["new_customers"])],
            ["Returning customers", _number(branch["returning_customers"])],
            ["Visitors", _number(branch["visitors"])],
            ["Deliveries / parcels", f"{branch['deliveries']} / {branch['parcels']}"],
        ]
        story.append(Spacer(1, 1.5 * mm))
        story.append(_table(activity_rows, [245, 265], styles, numeric_columns=(1,)))
        story.append(Paragraph(
            "Customer areas: " + (_safe(", ".join(branch["customer_areas"])) if branch["customer_areas"] else "No data for this period."),
            styles["small"],
        ))
        story.append(Spacer(1, 3 * mm))
    if not data["branches"]:
        story.append(Paragraph("No branch data for this period.", styles["body"]))

    story.append(PageBreak())
    story.append(_section("Customers, Operations & Calls", "Wateja, Shughuli na Simu", styles))
    story.append(_cards([
        ("Customers served / Wateja", _number(data["customers_served"]), "Unique in period"),
        ("New / Wapya", _number(data["customer_visit_totals"].get("NEW_CUSTOMER", 0)), "Visit records"),
        ("Returning / Waliorudi", _number(data["customer_visit_totals"].get("RETURNING_CUSTOMER", 0)), "Visit records"),
        ("Deliveries / Parcels", f"{data['delivery_count']} / {data['parcel_count']}", "Recorded in period"),
        ("Calls / Simu", _number(len(data["calls"])), "Recorded in period"),
        ("Follow-ups / Ufuatiliaji", _number(len(data["followups"])), "Due in selected range"),
    ], styles))
    story.append(Paragraph("Daily customer log", styles["section"]))
    customer_rows = [["Date", "Office", "Customer / visitor", "Phone", "Area", "Visit type"]]
    customer_rows.extend([
        [_date(row["date"]), row["office"], row["name"], row["phone"] or "-", row["area"], row["visit_type"]]
        for row in data["customer_log"]
    ])
    story.append(_table(customer_rows, [48, 62, 105, 72, 100, 133], styles))
    calls_chart = _chart(
        "Call activity by type",
        [label for _key, label in CustomerCall.CallType.choices],
        [("Calls", list(data["calls_by_type"].values()), BLUE)],
        "horizontal",
    )
    story.append(Spacer(1, 2 * mm))
    story.append(_image(calls_chart, 112 * mm, 36 * mm))
    story.append(Paragraph("Follow-up queue", styles["section"]))
    followup_rows = [["Due date", "Customer", "Phone", "Call type", "Next step"]]
    followup_rows.extend([
        [
            _date(call.follow_up_date) if call.follow_up_date else "-",
            call.contact_name or "-",
            call.caller_phone or (call.customer.phone if call.customer else "-"),
            call.get_call_type_display() or "-",
            call.outcome,
        ]
        for call in data["followups"]
    ])
    story.append(_table(followup_rows, [55, 105, 80, 105, 175], styles))

    story.append(PageBreak())
    story.append(_section("Call History & Data Quality", "Historia ya Simu na Ubora wa Data", styles))
    call_rows = [["Date", "Office", "Customer", "Phone", "Call type", "Outcome / notes"]]
    call_rows.extend([
        [
            timezone.localtime(call.called_at).strftime("%d/%m/%Y %H:%M"),
            call.branch_location.name if call.branch_location else "-",
            call.contact_name or "-",
            call.caller_phone or (call.customer.phone if call.customer else "-"),
            call.get_call_type_display() or "-",
            call.outcome + (f" — {call.notes}" if call.notes else ""),
        ]
        for call in data["calls"]
    ])
    story.append(_table(call_rows, [70, 75, 90, 77, 95, 113], styles))
    story.append(_section("Data Quality Notes & Next Steps", "Ubora wa Data na Hatua Zinazofuata", styles))
    for note in data["data_quality_notes"]:
        story.append(Paragraph(f"• {_safe(note)}", styles["body"]))
    for warning in data["reconciliation_warnings"]:
        story.append(Paragraph(
            f"• Reconcile { _safe(warning['name']) }: current stock ({_number(warning['current_stock'])}) exceeds recorded production ({_number(warning['produced'])}).",
            styles["body"],
        ))
    if not data["sales_total"] and not data["customer_log"] and not data["calls"]:
        story.append(Paragraph("No data for this period. Review branch submissions and transaction records.", styles["body"]))
    story.append(Spacer(1, 7 * mm))
    story.append(_signature_table(
        ["Prepared by", "Reviewed by CEO / Manager", "Date"],
        styles,
    ))
    return story


def _average_price(data):
    total_quantity = sum((row["quantity_sold"] for row in data["products"]), Decimal("0"))
    total_revenue = sum((row["revenue"] for row in data["products"]), Decimal("0"))
    return total_revenue / total_quantity if total_quantity else Decimal("0")


def _signature_table(labels, styles):
    cells = []
    for label in labels:
        cells.append(Paragraph(f"{_safe(label)}<br/><br/>____________________________", styles["small"]))
    table = Table([cells], colWidths=[CONTENT_WIDTH / len(labels)] * len(labels))
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
    ]))
    return table


def _daily_pages(data, styles):
    story = []
    story.extend(_hero(data, "DAILY", styles))
    day_label = _date(data["to_date"])
    story.append(_section(f"Day at a Glance — {day_label}", "Muhtasari wa Siku", styles))
    story.append(_cards([
        ("Sales today / Mauzo", _money(data["sales_last_day"]), "Selected report date"),
        ("Vs yesterday / Ikilinganishwa", _percent(data["sales_change_percent"]), "n/a when previous day has no sales"),
        ("Units sold / Vilivyouzwa", _number(data["units_sold"]), "All product lines"),
        ("Closing stock / Stock", _number(data["current_stock"]), "At report generation"),
        ("Customers served / Wateja", _number(data["customers_served"]), "Unique in selected day"),
        ("Loss / Hasara", _number(data["loss_total"]), "Recorded that day"),
    ], styles))
    trend_chart = _chart(
        "Daily sales trend by branch",
        [row["date"].strftime("%d/%m") for row in data["daily_sales_trend"]],
        [
            (
                office["label"],
                [row["offices"][office["key"]] for row in data["daily_sales_trend"]],
                office["color"],
            )
            for office in data["offices"]
        ],
        "line",
    )
    stock_series = (
        [("Store", [data["store_stock"]], GREEN)]
        if data["store_stock"] is not None
        else []
    )
    stock_series.extend(
        (branch["name"], [branch["stock"]], branch["color"])
        for branch in data["branches"]
    )
    stock_distribution = _chart(
        "Closing stock distribution",
        ["Stock"],
        stock_series,
        "donut",
    )
    story.append(Spacer(1, 2 * mm))
    story.append(Table(
        [[_image(trend_chart, 88 * mm, 45 * mm), _image(stock_distribution, 88 * mm, 45 * mm)]],
        colWidths=[CONTENT_WIDTH / 2] * 2,
        style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]),
    ))
    product_rows = [["Product", "Units sold", "Revenue", "Closing balance"]]
    for product in data["products"]:
        product_rows.append([
            product["name"],
            _number(product["quantity_sold"]),
            _money(product["revenue"]),
            _number(product["current_stock"]),
        ])
    product_revenue = sum((row["revenue"] for row in data["products"]), Decimal("0"))
    product_rows.append([
        "TOTAL",
        _number(data["units_sold"]),
        _money(product_revenue),
        _number(data["current_stock"]),
    ])
    story.append(_section("Sales by Product", "Mauzo kwa Bidhaa", styles))
    story.append(_table(product_rows, [185, 90, 120, 115], styles, numeric_columns=(1, 2, 3), totals_row=True))
    units_chart = _chart(
        "Units sold by product",
        [product["name"] for product in data["products"]],
        [("Units sold", [product["quantity_sold"] for product in data["products"]], BLUE)],
        "horizontal",
    )
    comparison_chart = _daily_compare_chart(data)
    story.append(Spacer(1, 2 * mm))
    story.append(Table(
        [[_image(comparison_chart, 88 * mm, 40 * mm), _image(units_chart, 88 * mm, 40 * mm)]],
        colWidths=[CONTENT_WIDTH / 2] * 2,
        style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]),
    ))
    story.append(_section("Key Highlights", "Mambo Muhimu", styles))
    story.append(Paragraph(
        "• " + _safe(f"Sales for the selected day: {_money(data['sales_last_day'])}."),
        styles["body"],
    ))
    story.append(Paragraph(
        "• " + _safe(f"Finished goods produced: {_number(data['produced_total'])}; current tangible stock: {_number(data['current_stock'])}."),
        styles["body"],
    ))
    story.append(Paragraph(
        "• " + _safe(f"Customers served: {data['customers_served']}; recorded losses: {_number(data['loss_total'])}; deliveries: {data['delivery_count']}; parcels: {data['parcel_count']}."),
        styles["body"],
    ))

    story.append(PageBreak())
    story.append(_section("Branch Movement & Customers", "Mabadiliko ya Stock na Wateja", styles))
    for branch in data["branches"]:
        story.append(Paragraph(_safe(branch["name"]), styles["section"]))
        stock_rows = [["Product", "Produced all-time", "Sold today", "Closing balance", "Loss"]]
        for product in data["tangible_products"]:
            stock_rows.append([
                product["name"],
                _number(product["produced"]),
                _number(product["sold_by_office"].get(branch["key"], 0)),
                _number(product["stock_by_location"].get(branch["location"].location_type, 0) if branch["location"] else 0),
                _number(product["loss_by_office"].get(branch["key"], 0)),
            ])
        stock_rows.append([
            "TOTAL",
            _number(data["produced_total"]),
            _number(branch["units_sold"]),
            _number(branch["stock"]),
            _number(branch["loss"]),
        ])
        story.append(_table(stock_rows, [130, 100, 85, 115, 80], styles, numeric_columns=(1, 2, 3, 4), totals_row=True))
        story.append(Paragraph(
            f"Sales: {_money(branch['sales_last_day'])}  |  New customers: {branch['new_customers']}  |  Returning: {branch['returning_customers']}  |  Visitors: {branch['visitors']}",
            styles["small"],
        ))
    closing_chart = _chart(
        "Closing balance by branch",
        [branch["name"] for branch in data["branches"]],
        [("Stock", [branch["stock"] for branch in data["branches"]], BRIGHT_GREEN)],
    )
    story.append(Spacer(1, 2 * mm))
    story.append(_image(closing_chart, 110 * mm, 33 * mm))
    activity_chart = _chart(
        "Customer activity comparison",
        [branch["name"] for branch in data["branches"]],
        [
            ("New", [branch["new_customers"] for branch in data["branches"]], BRIGHT_GREEN),
            ("Returning", [branch["returning_customers"] for branch in data["branches"]], AMBER),
            ("Visitors", [branch["visitors"] for branch in data["branches"]], BLUE),
        ],
    )
    story.append(_image(activity_chart, 110 * mm, 33 * mm))
    story.append(Paragraph(
        f"Follow-ups due on {_date(data['to_date'])}: {data['followups_due_today']}.",
        styles["body"],
    ))
    story.append(Paragraph("Attention for tomorrow", styles["section"]))
    attention = []
    if data["stock_alerts"]:
        attention.append("Low or out of stock: " + ", ".join(row["name"] for row in data["stock_alerts"]))
    else:
        attention.append("No low-stock products are currently flagged.")
    attention.append(f"Open follow-ups due in this report: {len(data['followups'])}.")
    if data["missing_branch_reports"]:
        attention.append("Branch reports not submitted: " + ", ".join(data["missing_branch_reports"]))
    else:
        attention.append("All selected branch daily reports are present.")
    for item in attention:
        story.append(Paragraph(f"• {_safe(item)}", styles["small"]))
    due_rows = [["Due date", "Customer", "Phone", "Call type", "Outcome"]]
    due_rows.extend([
        [
            _date(call.follow_up_date) if call.follow_up_date else "-",
            call.contact_name or "-",
            call.caller_phone or (call.customer.phone if call.customer else "-"),
            call.get_call_type_display() or "-",
            call.outcome,
        ]
        for call in data["followups"]
    ])
    story.append(_table(due_rows, [60, 110, 82, 105, 153], styles))
    story.append(Spacer(1, 4 * mm))
    story.append(_signature_table(
        ["Mwanza", "Dar es Salaam", "CEO / Manager"],
        styles,
    ))
    story.append(Paragraph(
        "*Production is an all-time cumulative figure; branch closing balances are current balances at report generation.",
        styles["small"],
    ))
    return story


def generate_report_pdf(data, report_type):
    _register_fonts()
    styles = _paragraph_styles()
    story = _daily_pages(data, styles) if report_type == "DAILY" else _period_pages(data, styles)
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=22 * mm,
        bottomMargin=18 * mm,
        title="Effective Diet Management Report",
        author="Effective Diet",
        pageCompression=1,
    )
    document.build(
        story,
        onFirstPage=_page_header,
        onLaterPages=_page_header,
        canvasmaker=_NumberedCanvas,
    )
    return buffer.getvalue()
