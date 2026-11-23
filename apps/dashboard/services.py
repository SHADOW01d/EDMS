from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.inventory.models import StockLocation, InventoryLedger, Product
from apps.procurement.models import Purchase
from apps.production.models import ProductionBatch
from apps.distribution.models import Transfer
from apps.sales.models import Sale, SaleItem
from apps.customers.models import BranchDailyReport, BranchExpense, Customer, CustomerCall


def factory_dashboard_data():
    today = timezone.localdate()
    factory = StockLocation.objects.filter(location_type=StockLocation.LocationType.FACTORY).first()
    stock_count = (
        InventoryLedger.objects.filter(location=factory).aggregate(total=Sum("quantity"))["total"]
        if factory
        else None
    )
    factory_product_rows = []
    if factory:
        for product in Product.objects.filter(active=True).order_by("category", "name"):
            balance = (
                InventoryLedger.objects.filter(location=factory, product=product)
                .aggregate(total=Sum("quantity"))["total"]
                or Decimal("0")
            )
            factory_product_rows.append({"product": product, "balance": balance})
    return {
        "batches": ProductionBatch.objects.select_related("recipe__product").filter(
            status=ProductionBatch.Status.COMPLETED
        ).order_by("-production_date", "-created_at"),
        "purchases": Purchase.objects.select_related("supplier").prefetch_related("items__product").order_by("-created_at")[:10],
        "batches": ProductionBatch.objects.select_related("recipe", "recipe__product").order_by("-created_at")[:10],
        "dispatches": Transfer.objects.select_related("destination").order_by("-dispatched_at")[:10],
        "stock_count": stock_count,
        "purchase_count": Purchase.objects.count(),
        "batch_count": ProductionBatch.objects.count(),
        "dispatch_count": Transfer.objects.count(),
        "finished_products": Product.objects.filter(
            active=True,
            category=Product.Category.FINISHED_GOOD,
        ),
        "raw_materials": Product.objects.filter(
            active=True,
            category=Product.Category.RAW_MATERIAL,
        ),
        "packaging_products": Product.objects.filter(
            active=True,
            category=Product.Category.PACKAGING,
        ),
        "factory_product_rows": factory_product_rows,
    }


def branch_dashboard_data(location_type):
    today = timezone.localdate()
    location = StockLocation.objects.filter(location_type=location_type).first()
    location_name = location_type
    stock = (
        InventoryLedger.objects.filter(location=location).aggregate(total=Sum("quantity"))["total"]
        if location
        else None
    )
    sales = Sale.objects.filter(location=location) if location else Sale.objects.none()
    sales_today = sales.filter(sold_at__date=today).aggregate(total=Sum("total_amount"))["total"]
    incoming = Transfer.objects.filter(destination=location).exclude(status=Transfer.Status.RECEIVED) if location else Transfer.objects.none()
    branch_role = (
        "BRANCH_MWANZA"
        if location_type == StockLocation.LocationType.BRANCH_MWANZA
        else "BRANCH_DAR"
    )
    branch_calls = CustomerCall.objects.filter(
        called_by__role=branch_role,
        customer__location=location,
    ).select_related("customer", "called_by").order_by("-called_at")[:20]
    customers = Customer.objects.filter(location=location) if location else Customer.objects.none()
    all_branch_calls = CustomerCall.objects.filter(
        called_by__role=branch_role,
        customer__location=location,
    ) if location else CustomerCall.objects.none()
    branch_followups = all_branch_calls.filter(follow_up_date__gte=today)
    customer_areas = sorted({
        address.strip()
        for address in customers.filter(active=True).exclude(address="").values_list("address", flat=True)
        if address.strip()
    })
    recent_reports = BranchDailyReport.objects.filter(location=location_type).select_related(
        "submitted_by", "approved_by"
    )[:10]
    return {
        "batches": [
            {
                "batch": row,
                "balance": (
                    InventoryLedger.objects.filter(
                        location=location,
                        production_batch=row,
                        product__category=Product.Category.FINISHED_GOOD,
                    ).aggregate(total=Sum("quantity"))["total"]
                    or Decimal("0")
                ),
            }
            for row in ProductionBatch.objects.filter(
                status=ProductionBatch.Status.COMPLETED,
                inventory_movements__location=location,
                inventory_movements__quantity__gt=0,
            ).select_related("recipe__product").distinct()
        ],
        "location": location,
        "stock": stock,
        "sales_today": sales_today,
        "incoming_transfers": incoming,
        "recent_sales": sales.select_related("customer").prefetch_related("items")[:10],
        "expenses": BranchExpense.objects.filter(location=location_name).order_by("-expense_date")[:10],
        "open_followups": CustomerCall.objects.filter(
            called_by__role=branch_role,
            customer__location=location,
            follow_up_date__gte=today,
        ).select_related("customer")[:10],
        "recent_calls": branch_calls,
        "branch_customers": customers,
        "customer_count": customers.filter(active=True).count(),
        "customer_call_count": all_branch_calls.count(),
        "open_followup_count": branch_followups.count(),
        "customer_areas": customer_areas,
        "recent_reports": recent_reports,
        "finished_products": Product.objects.filter(
            active=True,
            category=Product.Category.FINISHED_GOOD,
        ),
        "raw_materials": Product.objects.filter(
            active=True,
            category=Product.Category.RAW_MATERIAL,
        ),
        "packaging_products": Product.objects.filter(
            active=True,
            category=Product.Category.PACKAGING,
        ),
    }


def manager_dashboard_data():
    today = timezone.localdate()
    month_start = today.replace(day=1)

    factory = StockLocation.objects.filter(
        location_type=StockLocation.LocationType.FACTORY
    ).first()
    mwanza = StockLocation.objects.filter(
        location_type=StockLocation.LocationType.BRANCH_MWANZA
    ).first()
    dar = StockLocation.objects.filter(
        location_type=StockLocation.LocationType.BRANCH_DAR
    ).first()
    purchase_products = Product.objects.filter(
        active=True,
        category__in=(
            Product.Category.RAW_MATERIAL,
            Product.Category.PACKAGING,
        ),
    ).order_by("category", "name")
    factory_product_balances = {}
    if factory:
        factory_product_balances = dict(
            InventoryLedger.objects.filter(
                location=factory,
                product__in=purchase_products,
            )
            .values("product_id")
            .annotate(balance=Sum("quantity"))
            .values_list("product_id", "balance")
        )
    purchase_product_rows = [
        {
            "product": product,
            "balance": factory_product_balances.get(product.pk) or Decimal("0"),
        }
        for product in purchase_products
    ]

    def location_stock(location):
        if not location:
            return Decimal("0")
        total = InventoryLedger.objects.filter(location=location).aggregate(
            total=Sum("quantity")
        )["total"]
        return total or Decimal("0")

    def location_losses(location, start=None):
        entries = InventoryLedger.objects.filter(
            location=location,
            movement=InventoryLedger.Movement.LOSS,
        ) if location else InventoryLedger.objects.none()
        if start:
            entries = entries.filter(created_at__date__gte=start)
        total = entries.aggregate(total=Sum("quantity"))["total"]
        if not total:
            return Decimal("0")
        return abs(total)

    def branch_data(location):
        sales = Sale.objects.filter(location=location) if location else Sale.objects.none()
        customers = (
            Customer.objects.filter(location=location, active=True)
            if location
            else Customer.objects.none()
        )
        customer_calls = (
            CustomerCall.objects.filter(
                customer__location=location,
                called_by__role=location.location_type,
            )
            if location
            else CustomerCall.objects.none()
        )
        customer_followups = customer_calls.filter(follow_up_date__gte=today)
        customer_areas = sorted({
            address.strip()
            for address in customers.exclude(address="").values_list("address", flat=True)
            if address.strip()
        })
        sales_today = sales.filter(sold_at__date=today).aggregate(
            total=Sum("total_amount")
        )["total"] or Decimal("0")
        sales_month = sales.filter(sold_at__date__gte=month_start).aggregate(
            total=Sum("total_amount")
        )["total"] or Decimal("0")
        incoming = (
            Transfer.objects.filter(destination=location).exclude(
                status=Transfer.Status.RECEIVED
            )
            if location
            else Transfer.objects.none()
        )
        product_rows = []
        for product in Product.objects.filter(
            active=True,
            category=Product.Category.FINISHED_GOOD,
        ):
            ledger = InventoryLedger.objects.filter(location=location, product=product) if location else InventoryLedger.objects.none()
            balance = ledger.aggregate(total=Sum("quantity"))["total"] or Decimal("0")
            sold = (
                SaleItem.objects.filter(
                    sale__location=location,
                    sale__sold_at__date=today,
                    product=product,
                ).aggregate(total=Sum("quantity"))["total"]
                if location
                else None
            ) or Decimal("0")
            loss = ledger.filter(movement=InventoryLedger.Movement.LOSS).aggregate(
                total=Sum("quantity")
            )["total"] or Decimal("0")
            product_rows.append({
                "product": product,
                "sold_today": sold,
                "balance": balance,
                "loss": abs(loss),
            })
        return {
            "location": location,
            "sales_today": sales_today,
            "sales_month": sales_month,
            "stock": location_stock(location),
            "loss_today": location_losses(location, today),
            "incoming_count": incoming.count(),
            "incoming_transfers": incoming.select_related("dispatched_by").prefetch_related("items__product")[:10],
            "product_rows": product_rows,
            "customer_count": customers.count(),
            "customer_call_count": customer_calls.count(),
            "open_followup_count": customer_followups.count(),
            "customer_areas": customer_areas,
        }

    sales_today = Sale.objects.filter(sold_at__date=today).aggregate(
        total=Sum("total_amount")
    )["total"] or Decimal("0")
    sales_month = Sale.objects.filter(sold_at__date__gte=month_start).aggregate(
        total=Sum("total_amount")
    )["total"] or Decimal("0")
    production_today = ProductionBatch.objects.filter(
        production_date=today,
        status=ProductionBatch.Status.COMPLETED,
    ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
    production_month = ProductionBatch.objects.filter(
        production_date__gte=month_start,
        status=ProductionBatch.Status.COMPLETED,
    ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
    purchase_month = Purchase.objects.filter(
        purchase_date__gte=month_start
    ).aggregate(total=Sum("total_amount"))["total"] or Decimal("0")
    purchase_total = Purchase.objects.aggregate(
        total=Sum("total_amount")
    )["total"] or Decimal("0")
    loss_month = location_losses(factory, month_start)
    if not factory:
        loss_month = InventoryLedger.objects.filter(
            movement=InventoryLedger.Movement.LOSS,
            created_at__date__gte=month_start,
        ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
        loss_month = abs(loss_month)

    sales_trend_labels = []
    sales_trend_mwanza = []
    sales_trend_dar = []
    for week_offset in range(7, -1, -1):
        week_start = today - timedelta(days=today.weekday() + (week_offset * 7))
        week_end = week_start + timedelta(days=6)
        sales_trend_labels.append(week_start.strftime("W%d"))
        for location, values in ((mwanza, sales_trend_mwanza), (dar, sales_trend_dar)):
            week_total = (
                Sale.objects.filter(
                    location=location,
                    sold_at__date__gte=week_start,
                    sold_at__date__lte=week_end,
                ).aggregate(total=Sum("total_amount"))["total"]
                if location
                else None
            ) or Decimal("0")
            values.append(float(week_total))

    recent_call_counts = {
        "instruction": CustomerCall.objects.filter(outcome__iexact="Instruction").count(),
        "compliance": CustomerCall.objects.filter(outcome__iexact="Compliance").count(),
        "followup": CustomerCall.objects.exclude(
            outcome__iexact="Instruction"
        ).exclude(outcome__iexact="Compliance").count(),
        "due_today": CustomerCall.objects.filter(follow_up_date=today).count(),
    }
    production_by_product = []
    production_product_labels = []
    production_product_totals = []
    for product in Product.objects.filter(
        active=True,
        category=Product.Category.FINISHED_GOOD,
    ):
        total = ProductionBatch.objects.filter(
            recipe__product=product,
            production_date__gte=month_start,
            status=ProductionBatch.Status.COMPLETED,
        ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
        factory_balance = (
            InventoryLedger.objects.filter(product=product, location=factory)
            .aggregate(total=Sum("quantity"))["total"]
            if factory
            else None
        ) or Decimal("0")
        mwanza_balance = (
            InventoryLedger.objects.filter(product=product, location=mwanza)
            .aggregate(total=Sum("quantity"))["total"]
            if mwanza
            else None
        ) or Decimal("0")
        dar_balance = (
            InventoryLedger.objects.filter(product=product, location=dar)
            .aggregate(total=Sum("quantity"))["total"]
            if dar
            else None
        ) or Decimal("0")
        production_by_product.append({
            "product": product,
            "total": total,
            "factory_balance": factory_balance,
            "mwanza_balance": mwanza_balance,
            "dar_balance": dar_balance,
        })
        production_product_labels.append(product.name)
        production_product_totals.append(float(total))

    sales_product_labels = []
    sales_product_totals = []
    for product in Product.objects.filter(
        active=True,
        category=Product.Category.FINISHED_GOOD,
    ):
        total = SaleItem.objects.filter(
            product=product,
            sale__sold_at__date__gte=month_start,
        ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
        sales_product_labels.append(product.name)
        sales_product_totals.append(float(total))

    sales_report_product_totals = []
    for product in Product.objects.filter(
        active=True,
        category=Product.Category.FINISHED_GOOD,
    ):
        sold_total = SaleItem.objects.filter(product=product).aggregate(
            total=Sum("quantity")
        )["total"] or Decimal("0")
        mwanza_balance = (
            InventoryLedger.objects.filter(
                product=product,
                location=mwanza,
            ).aggregate(total=Sum("quantity"))["total"]
            if mwanza
            else None
        ) or Decimal("0")
        dar_balance = (
            InventoryLedger.objects.filter(
                product=product,
                location=dar,
            ).aggregate(total=Sum("quantity"))["total"]
            if dar
            else None
        ) or Decimal("0")
        factory_balance = (
            InventoryLedger.objects.filter(
                product=product,
                location=factory,
            ).aggregate(total=Sum("quantity"))["total"]
            if factory
            else None
        ) or Decimal("0")
        sales_report_product_totals.append({
            "product": product,
            "sold": sold_total,
            "factory_balance": factory_balance,
            "mwanza_balance": mwanza_balance,
            "dar_balance": dar_balance,
        })

    branch_reports = BranchDailyReport.objects.select_related(
        "submitted_by",
        "approved_by",
    ).order_by("-report_date", "-created_at")[:20]

    footer_product_values = []
    for row in sales_report_product_totals[:3]:
        footer_product_values.append({
            "sold": row["sold"],
            "balance": (row["mwanza_balance"] + row["dar_balance"]),
        })
    while len(footer_product_values) < 3:
        footer_product_values.append({"sold": Decimal("0"), "balance": Decimal("0")})

    return {
        "today": today,
        "month_start": month_start,
        "sales_total": Sale.objects.aggregate(total=Sum("total_amount"))["total"] or Decimal("0"),
        "sales_today": sales_today,
        "sales_month": sales_month,
        "production_today": production_today,
        "production_month": production_month,
        "factory_stock": location_stock(factory),
        "mwanza_stock": location_stock(mwanza),
        "dar_stock": location_stock(dar),
        "loss_month": loss_month,
        "purchase_month": purchase_month,
        "purchase_total": purchase_total,
        "purchase_count": Purchase.objects.count(),
        "batch_count": ProductionBatch.objects.count(),
        "transfer_count": Transfer.objects.exclude(status=Transfer.Status.RECEIVED).count(),
        "recent_sales": Sale.objects.select_related("location", "customer").order_by("-sold_at")[:10],
        "recent_purchases": Purchase.objects.select_related("supplier", "created_by").prefetch_related("items__product").order_by("-purchase_date", "-created_at")[:10],
        "recent_batches": ProductionBatch.objects.select_related("recipe", "recipe__product", "created_by").order_by("-production_date", "-created_at")[:10],
        "batches": ProductionBatch.objects.select_related("recipe", "recipe__product").filter(
            status=ProductionBatch.Status.COMPLETED
        ).order_by("-production_date", "-created_at"),
        "recent_transfers": Transfer.objects.select_related("destination", "dispatched_by").prefetch_related("items__product").order_by("-dispatched_at")[:10],
        "open_followups": CustomerCall.objects.filter(follow_up_date__gte=today).select_related("customer").order_by("follow_up_date")[:10],
        "recent_calls": CustomerCall.objects.select_related("customer", "called_by").order_by("-called_at")[:20],
        "customer_count": Customer.objects.filter(active=True).count(),
        "products": Product.objects.filter(
            active=True,
            category=Product.Category.FINISHED_GOOD,
        ),
        "raw_materials": Product.objects.filter(
            active=True,
            category=Product.Category.RAW_MATERIAL,
        ),
        "packaging_products": Product.objects.filter(
            active=True,
            category=Product.Category.PACKAGING,
        ),
        "factory_product_rows": [
            {"product": row["product"], "balance": row["factory_balance"]}
            for row in sales_report_product_totals
        ],
        "purchase_product_rows": purchase_product_rows,
        "mwanza_data": branch_data(mwanza),
        "dar_data": branch_data(dar),
        "sales_trend_labels": sales_trend_labels,
        "sales_trend_mwanza": sales_trend_mwanza,
        "sales_trend_dar": sales_trend_dar,
        "stock_split": [
            float(location_stock(factory)),
            float(location_stock(mwanza)),
            float(location_stock(dar)),
        ],
        "production_product_labels": production_product_labels,
        "production_product_totals": production_product_totals,
        "sales_product_labels": sales_product_labels,
        "sales_product_totals": sales_product_totals,
        "recent_call_counts": recent_call_counts,
        "production_by_product": production_by_product,
        "sales_report_product_totals": sales_report_product_totals,
        "sales_report_footer": footer_product_values,
        "distribution_product_labels": [
            row["product"].name for row in sales_report_product_totals
        ],
        "distribution_factory_stock": [
            float(row["factory_balance"]) for row in sales_report_product_totals
        ],
        "distribution_mwanza_stock": [
            float(row["mwanza_balance"]) for row in sales_report_product_totals
        ],
        "distribution_dar_stock": [
            float(row["dar_balance"]) for row in sales_report_product_totals
        ],
        "branch_reports": branch_reports,
    }
