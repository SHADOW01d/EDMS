from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.customers.models import (
    BranchDailyReport,
    BranchDelivery,
    BranchExpense,
    CustomerCall,
    CustomerVisit,
)
from apps.distribution.models import Transfer
from apps.inventory.models import InventoryLedger, Product, StockLocation
from apps.production.models import ProductionBatch, ProductionOutput
from apps.production.services import is_full_package_product, is_manufactured_product, production_product_family
from apps.sales.models import Sale, SaleItem


ZERO = Decimal("0")
OFFICES = {
    "mwanza": {
        "label": "Mwanza",
        "location_type": StockLocation.LocationType.BRANCH_MWANZA,
        "color": "#16A34A",
    },
    "dar": {
        "label": "Dar es Salaam",
        "location_type": StockLocation.LocationType.BRANCH_DAR,
        "color": "#F59E0B",
    },
}
STORE = {
    "label": "Store",
    "location_type": StockLocation.LocationType.FACTORY,
    "color": "#0F4A2E",
}
PACKAGE_COMPONENT_FAMILIES = ("effective_diet", "pressure_masala", "honey")


def _decimal(value):
    return value if value is not None else ZERO


def _selected_offices(office):
    if office == "all":
        return ("mwanza", "dar")
    if office in OFFICES:
        return (office,)
    raise ValueError("Select All offices, Mwanza, or Dar es Salaam.")


def _stock_location_types(office):
    if office == "all":
        return (
            StockLocation.LocationType.FACTORY,
            StockLocation.LocationType.BRANCH_MWANZA,
            StockLocation.LocationType.BRANCH_DAR,
        )
    return (OFFICES[office]["location_type"],)


def _empty_totals():
    return {"quantity": ZERO, "revenue": ZERO}


def _customer_ids_for_range(start_date, end_date, offices):
    location_types = [OFFICES[key]["location_type"] for key in offices]
    sale_customers = Sale.objects.filter(
        sold_at__date__range=(start_date, end_date),
        location__location_type__in=location_types,
        customer__isnull=False,
    ).values_list("customer_id", flat=True)
    visit_customers = CustomerVisit.objects.filter(
        visited_at__date__range=(start_date, end_date),
        location__location_type__in=location_types,
        customer__isnull=False,
    ).values_list("customer_id", flat=True)
    return set(sale_customers).union(visit_customers)


def build_report_data(from_date, to_date, office="all"):
    """Build the single source of truth for report screens, PDFs and CSV exports."""
    if from_date is None or to_date is None or from_date > to_date:
        raise ValueError("The report date range is invalid.")
    offices = _selected_offices(office)
    office_types = [OFFICES[key]["location_type"] for key in offices]
    visible_location_types = _stock_location_types(office)
    visible_locations = {
        row.location_type: row
        for row in StockLocation.objects.filter(location_type__in=visible_location_types)
    }

    sales = Sale.objects.filter(
        sold_at__date__range=(from_date, to_date),
        location__location_type__in=office_types,
    )
    sales_total = sales.aggregate(total=Coalesce(Sum("total_amount"), ZERO))["total"]
    units_sold = SaleItem.objects.filter(sale__in=sales).aggregate(
        total=Coalesce(Sum("quantity"), ZERO),
    )["total"]
    sales_by_day_office = {
        (row["sold_at__date"], row["location__location_type"]): row
        for row in sales.values("sold_at__date", "location__location_type").annotate(
            revenue=Coalesce(Sum("total_amount"), ZERO),
            count=Count("pk"),
        )
    }

    item_totals = defaultdict(_empty_totals)
    item_totals_by_office = defaultdict(_empty_totals)
    daily_sale_units = defaultdict(lambda: defaultdict(lambda: ZERO))
    daily_sale_amounts = defaultdict(lambda: defaultdict(lambda: ZERO))
    for row in SaleItem.objects.filter(sale__in=sales).values(
        "product_id",
        "sale__location__location_type",
        "sale__sold_at__date",
        "quantity",
        "unit_price",
    ):
        product_id = row["product_id"]
        location_type = row["sale__location__location_type"]
        day_location = (row["sale__sold_at__date"], location_type)
        quantity = row["quantity"]
        revenue = quantity * row["unit_price"]
        item_totals[product_id]["quantity"] += quantity
        item_totals[product_id]["revenue"] += revenue
        item_totals_by_office[(product_id, location_type)]["quantity"] += quantity
        item_totals_by_office[(product_id, location_type)]["revenue"] += revenue
        daily_sale_units[day_location][product_id] += quantity
        daily_sale_amounts[day_location][product_id] += revenue

    products = list(
        Product.objects.filter(category=Product.Category.FINISHED_GOOD)
        .order_by("name")
    )
    product_ids = [product.pk for product in products]
    produced_by_product = defaultdict(lambda: ZERO)
    for row in ProductionOutput.objects.filter(product_id__in=product_ids).values(
        "product_id",
    ).annotate(total=Coalesce(Sum("quantity"), ZERO)):
        produced_by_product[row["product_id"]] += row["total"]
    for row in ProductionBatch.objects.filter(
        recipe__product_id__in=product_ids,
        status=ProductionBatch.Status.COMPLETED,
        outputs__isnull=True,
    ).values("recipe__product_id").annotate(total=Coalesce(Sum("quantity"), ZERO)):
        produced_by_product[row["recipe__product_id"]] += row["total"]

    stock_by_product_location = defaultdict(lambda: ZERO)
    loss_by_product_office = defaultdict(lambda: ZERO)
    loss_by_location = defaultdict(lambda: ZERO)
    stock_rows = InventoryLedger.objects.filter(
        product_id__in=product_ids,
        location__location_type__in=visible_location_types,
    ).values(
        "product_id",
        "location__location_type",
    ).annotate(total=Coalesce(Sum("quantity"), ZERO))
    for row in stock_rows:
        stock_by_product_location[
            (row["product_id"], row["location__location_type"])
        ] = row["total"]
    loss_rows = InventoryLedger.objects.filter(
        product_id__in=product_ids,
        location__location_type__in=office_types,
        movement=InventoryLedger.Movement.LOSS,
        created_at__date__range=(from_date, to_date),
    ).values("product_id", "location__location_type").annotate(
        total=Coalesce(Sum("quantity"), ZERO),
    )
    for row in loss_rows:
        product_id = row["product_id"]
        location_type = row["location__location_type"]
        loss_by_location[location_type] += abs(row["total"])
        office_key = next(
            (
                key for key in offices
                if OFFICES[key]["location_type"] == location_type
            ),
            None,
        )
        if office_key:
            loss_by_product_office[(product_id, office_key)] += abs(row["total"])

    visits = list(
        CustomerVisit.objects.filter(
            visited_at__date__range=(from_date, to_date),
            location__location_type__in=office_types,
        ).select_related("customer", "location", "recorded_by").order_by("visited_at", "pk")
    )
    deliveries = list(
        BranchDelivery.objects.filter(
            delivery_date__range=(from_date, to_date),
            location__location_type__in=office_types,
        ).select_related("customer", "location", "recorded_by").order_by("delivery_date", "created_at")
    )
    calls = list(
        CustomerCall.objects.filter(
            called_at__date__range=(from_date, to_date),
        ).filter(
            Q(location__location_type__in=office_types)
            | Q(
                location__isnull=True,
                called_by__role__in=office_types,
                customer__location__location_type__in=office_types,
            )
        ).select_related("customer", "called_by", "location").order_by("-called_at")
    )
    followups = list(
        CustomerCall.objects.filter(
            follow_up_date__range=(from_date, to_date),
        ).filter(
            Q(location__location_type__in=office_types)
            | Q(
                location__isnull=True,
                called_by__role__in=office_types,
                customer__location__location_type__in=office_types,
            )
        ).select_related("customer", "called_by", "location").order_by("follow_up_date", "-called_at")
    )
    expenses = list(
        BranchExpense.objects.filter(
            expense_date__range=(from_date, to_date),
            location__in=office_types,
        ).select_related("recorded_by").order_by("expense_date", "recorded_at")
    )
    customer_ids = _customer_ids_for_range(from_date, to_date, offices)
    customer_ids_by_day_office = defaultdict(set)
    for row in Sale.objects.filter(
        sold_at__date__range=(from_date, to_date),
        location__location_type__in=office_types,
        customer__isnull=False,
    ).values("sold_at__date", "location__location_type", "customer_id").distinct():
        customer_ids_by_day_office[
            (row["sold_at__date"], row["location__location_type"])
        ].add(row["customer_id"])
    for row in CustomerVisit.objects.filter(
        visited_at__date__range=(from_date, to_date),
        location__location_type__in=office_types,
        customer__isnull=False,
    ).values("visited_at__date", "location__location_type", "customer_id").distinct():
        customer_ids_by_day_office[
            (row["visited_at__date"], row["location__location_type"])
        ].add(row["customer_id"])

    product_families = {
        product.pk: production_product_family(product)
        for product in products
    }
    component_by_family = {
        family: next(
            (
                product for product in products
                if product.sku.casefold() == {
                    "effective_diet": "ed-single",
                    "pressure_masala": "presha-single",
                    "honey": "honey-single",
                }[family]
            ),
            None,
        )
        for family in PACKAGE_COMPONENT_FAMILIES
    }
    product_rows = []
    for product in products:
        family = product_families[product.pk]
        if not (is_manufactured_product(product) or is_full_package_product(product)):
            has_activity = (
                product.pk in item_totals
                or produced_by_product[product.pk] != ZERO
                or any(key[0] == product.pk and value != ZERO for key, value in stock_by_product_location.items())
            )
            if not has_activity:
                continue
        virtual = is_full_package_product(product)
        if virtual:
            component_products = [
                component_by_family[family_key]
                for family_key in PACKAGE_COMPONENT_FAMILIES
            ]
            if any(component is None for component in component_products):
                current_stock_by_location = {}
                produced = ZERO
            else:
                current_stock_by_location = {
                    location_type: min(
                        stock_by_product_location[
                            (component.pk, location_type)
                        ]
                        for component in component_products
                    )
                    for location_type in visible_location_types
                }
                produced = min(
                    produced_by_product[component.pk]
                    for component in component_products
                )
        else:
            current_stock_by_location = {
                location_type: stock_by_product_location[(product.pk, location_type)]
                for location_type in visible_location_types
            }
            produced = produced_by_product[product.pk]
        displayed_stock = sum(current_stock_by_location.values(), ZERO)
        values = item_totals[product.pk]
        sold_by_office = {
            office_key: item_totals_by_office[(product.pk, office_key)]["quantity"]
            for office_key in offices
        }
        revenue_by_office = {
            office_key: item_totals_by_office[(product.pk, office_key)]["revenue"]
            for office_key in offices
        }
        current_stock = displayed_stock if office == "all" else current_stock_by_location.get(
            OFFICES[office]["location_type"],
            ZERO,
        )
        product_rows.append({
            "product": product,
            "name": product.name,
            "sku": product.sku,
            "unit": product.unit,
            "unit_price": product.unit_price,
            "quantity_sold": values["quantity"],
            "revenue": values["revenue"],
            "average_price": (
                values["revenue"] / values["quantity"]
                if values["quantity"] else None
            ),
            "sold_by_office": sold_by_office,
            "sold_by_office_rows": [
                {
                    "office": OFFICES[office_key]["label"],
                    "quantity": sold_by_office[office_key],
                }
                for office_key in offices
            ],
            "revenue_by_office": revenue_by_office,
            "produced": produced,
            "store_stock": (
                current_stock_by_location.get(STORE["location_type"], ZERO)
                if office == "all" else None
            ),
            "mwanza_stock": (
                current_stock_by_location.get(OFFICES["mwanza"]["location_type"], ZERO)
                if office in ("all", "mwanza") else None
            ),
            "dar_stock": (
                current_stock_by_location.get(OFFICES["dar"]["location_type"], ZERO)
                if office in ("all", "dar") else None
            ),
            "stock_by_location": current_stock_by_location,
            "current_stock": current_stock,
            "stock_percent": (
                current_stock / produced * Decimal("100")
                if produced > ZERO else None
            ),
            "loss_by_office": {
                office_key: loss_by_product_office[(product.pk, office_key)]
                for office_key in offices
            },
            "loss": (
                sum(
                    (loss_by_product_office[(product.pk, office_key)] for office_key in offices),
                    ZERO,
                )
            ),
            "is_virtual": virtual,
            "family": family,
        })

    tangible_product_rows = [row for row in product_rows if not row["is_virtual"]]
    total_produced = sum((row["produced"] for row in tangible_product_rows), ZERO)
    total_stock = sum((row["current_stock"] for row in tangible_product_rows), ZERO)
    store_stock = (
        sum((row["store_stock"] or ZERO for row in tangible_product_rows), ZERO)
        if office == "all" else None
    )
    today = timezone.localdate()
    yesterday = to_date - timedelta(days=1)
    today_sales = Sale.objects.filter(
        sold_at__date=today,
        location__location_type__in=office_types,
    ).aggregate(total=Coalesce(Sum("total_amount"), ZERO))["total"]
    yesterday_sales = Sale.objects.filter(
        sold_at__date=yesterday,
        location__location_type__in=office_types,
    ).aggregate(total=Coalesce(Sum("total_amount"), ZERO))["total"]
    report_day_sales = sales.filter(sold_at__date=to_date).aggregate(
        total=Coalesce(Sum("total_amount"), ZERO),
    )["total"]
    yesterday_sales_by_office = {
        row["location__location_type"]: row["total"]
        for row in Sale.objects.filter(
            sold_at__date=yesterday,
            location__location_type__in=office_types,
        ).values("location__location_type").annotate(
            total=Coalesce(Sum("total_amount"), ZERO),
        )
    }
    report_day_sales_by_office = {
        row["location__location_type"]: row["total"]
        for row in sales.filter(sold_at__date=to_date)
        .values("location__location_type")
        .annotate(total=Coalesce(Sum("total_amount"), ZERO))
    }
    branches = []
    for office_key in offices:
        office_data = OFFICES[office_key]
        location = visible_locations.get(office_data["location_type"])
        branch_total = sum(
            (
                row["revenue"]
                for (day, location_type), row in sales_by_day_office.items()
                if location_type == office_data["location_type"]
            ),
            ZERO,
        )
        branch_units = sum(
            (
                item_totals_by_office[(product.pk, office_key)]["quantity"]
                for product in products
            ),
            ZERO,
        )
        branch_customer_ids = set(
            Sale.objects.filter(
                sold_at__date__range=(from_date, to_date),
                location__location_type=office_data["location_type"],
                customer__isnull=False,
            ).values_list("customer_id", flat=True)
        ).union(
            CustomerVisit.objects.filter(
                visited_at__date__range=(from_date, to_date),
                location__location_type=office_data["location_type"],
                customer__isnull=False,
            ).values_list("customer_id", flat=True)
        )
        branch_visits = [visit for visit in visits if visit.location.location_type == office_data["location_type"]]
        branch_deliveries = [
            delivery for delivery in deliveries
            if delivery.location.location_type == office_data["location_type"]
        ]
        branch_calls = [call for call in calls if call.branch_location and call.branch_location.location_type == office_data["location_type"]]
        branch_followups = [
            call for call in followups
            if call.branch_location and call.branch_location.location_type == office_data["location_type"]
        ]
        pending_transfers = Transfer.objects.filter(
            destination=location,
            status__in=(Transfer.Status.DISPATCHED, Transfer.Status.PARTIAL),
        ).count() if location else 0
        branches.append({
            "key": office_key,
            "name": office_data["label"],
            "location": location,
            "color": office_data["color"],
            "sales": branch_total,
            "sales_yesterday": yesterday_sales_by_office.get(
                office_data["location_type"],
                ZERO,
            ),
            "sales_last_day": report_day_sales_by_office.get(
                office_data["location_type"],
                ZERO,
            ),
            "share_percent": (
                branch_total / sales_total * Decimal("100")
                if sales_total else ZERO
            ),
            "units_sold": branch_units,
            "customers": len(branch_customer_ids),
            "loss": loss_by_location[office_data["location_type"]],
            "stock": sum(
                (
                    row["stock_by_location"].get(office_data["location_type"], ZERO)
                    for row in tangible_product_rows
                ),
                ZERO,
            ),
            "pending_transfers": pending_transfers,
            "visits": len(branch_visits),
            "new_customers": sum(visit.visit_type == CustomerVisit.VisitType.NEW_CUSTOMER for visit in branch_visits),
            "returning_customers": sum(visit.visit_type == CustomerVisit.VisitType.RETURNING_CUSTOMER for visit in branch_visits),
            "visitors": sum(
                visit.visit_type not in (
                    CustomerVisit.VisitType.NEW_CUSTOMER,
                    CustomerVisit.VisitType.RETURNING_CUSTOMER,
                )
                for visit in branch_visits
            ),
            "deliveries": len(branch_deliveries),
            "parcels": sum(delivery.parcel_count for delivery in branch_deliveries),
            "calls": len(branch_calls),
            "followups": len(branch_followups),
            "customer_areas": sorted({
                visit.customer.address.strip()
                for visit in branch_visits
                if visit.customer and visit.customer.address.strip()
            }),
            "sales_today": Sale.objects.filter(
                location__location_type=office_data["location_type"],
                sold_at__date=timezone.localdate(),
            ).aggregate(total=Coalesce(Sum("total_amount"), ZERO))["total"],
        })

    sales_change_percent = (
        (report_day_sales - yesterday_sales) / yesterday_sales * Decimal("100")
        if yesterday_sales else None
    )

    daily_sales = []
    day = from_date
    while day <= to_date:
        row = {"date": day}
        row["offices"] = {}
        for office_key in offices:
            office_type = OFFICES[office_key]["location_type"]
            daily_row = sales_by_day_office.get((day, office_type), {})
            row["offices"][office_key] = {
                "sales": daily_row.get("revenue", ZERO),
                "count": daily_row.get("count", 0),
            }
        row["sales"] = sum(
            (values["sales"] for values in row["offices"].values()),
            ZERO,
        )
        daily_sales.append(row)
        day += timedelta(days=1)

    trend_start = to_date - timedelta(days=6)
    trend_sales = {
        (row["sold_at__date"], row["location__location_type"]): row["total"]
        for row in Sale.objects.filter(
            sold_at__date__range=(trend_start, to_date),
            location__location_type__in=office_types,
        ).values("sold_at__date", "location__location_type").annotate(
            total=Coalesce(Sum("total_amount"), ZERO),
        )
    }
    daily_sales_trend = []
    trend_day = trend_start
    while trend_day <= to_date:
        daily_sales_trend.append({
            "date": trend_day,
            "offices": {
                office_key: trend_sales.get(
                    (trend_day, OFFICES[office_key]["location_type"]),
                    ZERO,
                )
                for office_key in offices
            },
        })
        trend_day += timedelta(days=1)

    product_by_id = {product.pk: product for product in products}
    customer_log = []
    for visit in visits:
        customer_log.append({
            "date": timezone.localtime(visit.visited_at).date(),
            "office": visit.location.get_location_type_display(),
            "office_key": next(
                (key for key in offices if OFFICES[key]["location_type"] == visit.location.location_type),
                "",
            ),
            "name": visit.contact_name,
            "phone": visit.visitor_phone or (visit.customer.phone if visit.customer else ""),
            "area": visit.customer.address if visit.customer and visit.customer.address else "-",
            "visit_type": visit.get_visit_type_display(),
        })

    calls_by_type = {
        call_type: sum(call.call_type == call_type for call in calls)
        for call_type, _label in CustomerCall.CallType.choices
    }
    branch_report_status = {
        report.location: report
        for report in BranchDailyReport.objects.filter(
            report_date=to_date,
            location__in=office_types,
        ).select_related("submitted_by", "approved_by")
    }
    missing_branch_reports = [
        OFFICES[key]["label"]
        for key in offices
        if OFFICES[key]["location_type"] not in branch_report_status
    ]
    sales_table_rows = []
    for daily_row in daily_sales:
        for office_key in offices:
            office_type = OFFICES[office_key]["location_type"]
            key = (daily_row["date"], office_type)
            daily_product_data = []
            for product in product_rows:
                daily_product_data.append({
                    "product": product["product"],
                    "quantity": daily_sale_units[key][product["product"].pk],
                    "revenue": daily_sale_amounts[key][product["product"].pk],
                })
            sales_table_rows.append({
                "date": daily_row["date"],
                "office": OFFICES[office_key]["label"],
                "office_key": office_key,
                "sales": daily_row["offices"][office_key]["sales"],
                "units": sum((item["quantity"] for item in daily_product_data), ZERO),
                "customers": len(customer_ids_by_day_office[key]),
                "products": daily_product_data,
            })
    office_order = {office_key: index for index, office_key in enumerate(offices)}
    sales_table_rows.sort(
        key=lambda row: (-row["date"].toordinal(), office_order[row["office_key"]]),
    )

    loss_total = sum((branch["loss"] for branch in branches), ZERO)
    expense_total = sum((expense.amount for expense in expenses), ZERO)
    customers_served = len(customer_ids)
    visit_type_totals = {
        visit_type: sum(visit.visit_type == visit_type for visit in visits)
        for visit_type, _label in CustomerVisit.VisitType.choices
    }
    report_product_rows = [
        row for row in product_rows
        if row["quantity_sold"] or row["produced"] or row["current_stock"] or row["is_virtual"]
    ]
    data_quality_notes = [
        "Full Package ni bidhaa-virtual: ni kifurushi cha bidhaa 1 ya kila aina (Effective Diet, Presha Masala, Asali). Stock yake ni kiwango cha chini cha vipengele hivyo na haijumuishwi tena kwenye jumla ya stock ili kuepuka kuhesabu bidhaa mara mbili.",
        "Gross margin haijaonyeshwa pale gharama halisi ya uzalishaji haijathibitishwa. Bei ya mauzo inatokana na bei iliyohifadhiwa kwenye kila sale line.",
    ]
    reconciliation_warnings = [
        row for row in tangible_product_rows
        if row["current_stock"] > row["produced"]
    ]
    stock_alerts = [
        row for row in tangible_product_rows
        if row["current_stock"] <= row["product"].reorder_level
    ]

    return {
        "from_date": from_date,
        "to_date": to_date,
        "office": office,
        "office_label": "All offices" if office == "all" else OFFICES[office]["label"],
        "offices": [{"key": key, **OFFICES[key]} for key in offices],
        "sales": sales,
        "sales_total": sales_total,
        "sales_today": today_sales,
        "sales_last_day": report_day_sales,
        "yesterday_sales": yesterday_sales,
        "yesterday_sales_by_office": {
            office_key: yesterday_sales_by_office.get(
                OFFICES[office_key]["location_type"],
                ZERO,
            )
            for office_key in offices
        },
        "sales_last_day_by_office": {
            office_key: report_day_sales_by_office.get(
                OFFICES[office_key]["location_type"],
                ZERO,
            )
            for office_key in offices
        },
        "sales_change_percent": sales_change_percent,
        "units_sold": units_sold,
        "produced_total": total_produced,
        "current_stock": total_stock,
        "store_stock": store_stock,
        "branch_stock": sum((branch["stock"] for branch in branches), ZERO),
        "active_customers": customers_served,
        "customers_served": customers_served,
        "loss_total": loss_total,
        "branches": branches,
        "products": report_product_rows,
        "tangible_products": tangible_product_rows,
        "daily_sales": daily_sales,
        "daily_sales_trend": daily_sales_trend,
        "sales_table_rows": sales_table_rows,
        "customer_log": customer_log,
        "customer_visits": visits,
        "customer_visit_totals": visit_type_totals,
        "customer_areas": sorted({row["area"] for row in customer_log if row["area"] != "-"}),
        "deliveries": deliveries,
        "delivery_count": len(deliveries),
        "parcel_count": sum(delivery.parcel_count for delivery in deliveries),
        "calls": calls,
        "calls_by_type": calls_by_type,
        "followups": followups,
        "followups_due_today": sum(call.follow_up_date == today for call in followups),
        "expenses": expenses,
        "expense_total": expense_total,
        "branch_report_status": branch_report_status,
        "missing_branch_reports": missing_branch_reports,
        "reconciliation_warnings": reconciliation_warnings,
        "stock_alerts": stock_alerts,
        "data_quality_notes": data_quality_notes,
        "today": today,
        "yesterday": yesterday,
        "today_vs_yesterday_percent": sales_change_percent,
        "sale_count": sales.count(),
        "product_by_id": product_by_id,
        "visible_locations": visible_locations,
        "stock_by_product_location": stock_by_product_location,
        "loss_by_location": loss_by_location,
        "calls_today_count": sum(
            timezone.localtime(call.called_at).date() == today for call in calls
        ),
    }
