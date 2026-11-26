from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.inventory.models import StockLocation, InventoryLedger, Product
from apps.procurement.models import Purchase
from apps.production.models import ProductionBatch, ProductionConsumption, ProductionOutput
from apps.production.services import (
    is_full_package_product,
    is_manufactured_product,
    production_product_family,
)
from apps.distribution.models import Transfer, TransferItem
from apps.sales.models import Sale, SaleItem
from apps.customers.models import (
    BranchDailyReport,
    BranchDelivery,
    BranchExpense,
    Customer,
    CustomerCall,
    CustomerVisit,
)


def _manufacturing_groups():
    products = list(
        product for product in Product.objects.filter(
            active=True,
            category=Product.Category.FINISHED_GOOD,
        ).order_by("name")
        if is_manufactured_product(product)
    )
    family_labels = (
        ("Effective Diet", "effective_diet"),
        ("Presha Masala", "pressure_masala"),
        ("Asali", "honey"),
    )
    return [
        {
            "name": label,
            "products": [
                product for product in products
                if production_product_family(product) == family
            ],
        }
        for label, family in family_labels
        if any(production_product_family(product) == family for product in products)
    ]


def _batch_material_balances(factory, products, selected_batch):
    if not factory or not selected_batch:
        return {}, {}, {}

    product_ids = [product.pk for product in products]
    opening_balances = dict(
        InventoryLedger.objects.filter(
            location=factory,
            product_id__in=product_ids,
            created_at__lt=selected_batch.created_at,
        )
        .exclude(production_batch=selected_batch)
        .values("product_id")
        .annotate(balance=Sum("quantity"))
        .values_list("product_id", "balance")
    )
    batch_movements = InventoryLedger.objects.filter(
        location=factory,
        product_id__in=product_ids,
        production_batch=selected_batch,
    )
    batch_balances = dict(
        batch_movements.values("product_id")
        .annotate(balance=Sum("quantity"))
        .values_list("product_id", "balance")
    )
    batch_purchases = dict(
        batch_movements.filter(movement=InventoryLedger.Movement.PURCHASE)
        .values("product_id")
        .annotate(quantity=Sum("quantity"))
        .values_list("product_id", "quantity")
    )
    return opening_balances, batch_purchases, batch_balances


def _factory_material_data(factory, selected_batch=None):
    products = list(
        Product.objects.filter(
            active=True,
            category__in=(Product.Category.RAW_MATERIAL, Product.Category.PACKAGING),
        ).order_by("category", "name")
    )
    balances = {
        product_id: balance or Decimal("0")
        for product_id, balance in (
            InventoryLedger.objects.filter(
                location=factory,
                product__in=products,
            )
            .values("product_id")
            .annotate(balance=Sum("quantity"))
        ).values_list("product_id", "balance")
    } if factory else {}
    opening_balances, batch_purchases, batch_movements = _batch_material_balances(
        factory,
        products,
        selected_batch,
    )
    consumption_totals = ProductionConsumption.objects.filter(
        product__in=products,
        **({"batch": selected_batch} if selected_batch else {}),
    ).values("product_id").annotate(total=Sum("quantity"))
    consumed = {
        row["product_id"]: row["total"] or Decimal("0")
        for row in consumption_totals
    }
    consumptions = ProductionConsumption.objects.filter(
        **({"batch": selected_batch} if selected_batch else {}),
    ).select_related(
        "product",
        "batch",
        "batch__recipe__product",
        "output__product",
        "output__created_by",
    ).order_by("-created_at")[:50]
    consumed_product_ids = {row.product_id for row in consumptions}
    balance_entries = InventoryLedger.objects.filter(
        location=factory,
        product_id__in=consumed_product_ids,
    )
    if selected_batch:
        balance_entries = balance_entries.exclude(
            product__category=Product.Category.FINISHED_GOOD,
        ) | InventoryLedger.objects.filter(
            location=factory,
            product_id__in=consumed_product_ids,
            product__category=Product.Category.FINISHED_GOOD,
            production_batch=selected_batch,
        )
    consumption_balances = dict(
        balance_entries.values("product_id")
        .annotate(balance=Sum("quantity"))
        .values_list("product_id", "balance")
    )
    return {
        "material_inventory_rows": [
            {
                "product": product,
                "balance": balances.get(product.pk, Decimal("0")),
                "used_quantity": consumed.get(product.pk, Decimal("0")),
                "batch_opening_balance": opening_balances.get(product.pk, Decimal("0")),
                "batch_purchase_quantity": batch_purchases.get(product.pk, Decimal("0")),
                "batch_balance": (
                    opening_balances.get(product.pk, Decimal("0"))
                    + batch_movements.get(product.pk, Decimal("0"))
                ),
            }
            for product in products
        ],
        "production_consumption_rows": [
            {
                "consumption": consumption,
                "balance": consumption_balances.get(consumption.product_id, Decimal("0")),
            }
            for consumption in consumptions
        ],
    }


def factory_dashboard_data(selected_batch=None):
    today = timezone.localdate()
    factory = StockLocation.objects.filter(location_type=StockLocation.LocationType.FACTORY).first()
    stock_entries = InventoryLedger.objects.filter(location=factory) if factory else InventoryLedger.objects.none()
    if selected_batch:
        stock_entries = stock_entries.filter(
            production_batch=selected_batch,
            product__category=Product.Category.FINISHED_GOOD,
        )
    stock_count = stock_entries.aggregate(total=Sum("quantity"))["total"] if factory else None
    material_products = list(
        Product.objects.filter(
            active=True,
            category__in=(Product.Category.RAW_MATERIAL, Product.Category.PACKAGING),
        )
    )
    opening_balances, batch_purchases, batch_movements = _batch_material_balances(
        factory,
        material_products,
        selected_batch,
    )
    factory_product_rows = []
    if factory:
        for product in Product.objects.filter(active=True).order_by("category", "name"):
            balance = (
                InventoryLedger.objects.filter(location=factory, product=product)
                .aggregate(total=Sum("quantity"))["total"]
                or Decimal("0")
            )
            if selected_batch and product.category == Product.Category.FINISHED_GOOD:
                balance = (
                    InventoryLedger.objects.filter(
                        location=factory,
                        product=product,
                        production_batch=selected_batch,
                    ).aggregate(total=Sum("quantity"))["total"]
                    or Decimal("0")
                )
            factory_product_rows.append({
                "product": product,
                "balance": balance,
                "batch_balance": (
                    balance
                    if product.category == Product.Category.FINISHED_GOOD and selected_batch
                    else opening_balances.get(product.pk, Decimal("0"))
                    + batch_movements.get(product.pk, Decimal("0"))
                ),
                "batch_opening_balance": opening_balances.get(product.pk, Decimal("0")),
                "batch_purchase_quantity": batch_purchases.get(product.pk, Decimal("0")),
            })
    batch_production_cards = []
    for group in _manufacturing_groups():
        group_quantity = Decimal("0")
        for product in group["products"]:
            output_rows = ProductionOutput.objects.filter(product=product)
            if selected_batch:
                output_rows = output_rows.filter(batch=selected_batch)
            group_quantity += output_rows.aggregate(total=Sum("quantity"))["total"] or Decimal("0")
        batch_production_cards.append({
            "name": group["name"],
            "quantity": group_quantity,
        })
    purchases = Purchase.objects.select_related("supplier").prefetch_related("items__product")
    if selected_batch:
        purchases = purchases.filter(batch=selected_batch)
    raw_honey_product = Product.objects.filter(
        sku="RAW-RAW-HONEY",
        category=Product.Category.RAW_MATERIAL,
    ).first()
    honey_jar_product = Product.objects.filter(
        sku="PKG-HONEY-CANS",
        category=Product.Category.PACKAGING,
    ).first()
    factory_material_balances = {
        row["product"].pk: row["balance"]
        for row in factory_product_rows
    }
    return {
        **_factory_material_data(factory, selected_batch),
        "purchases": purchases.order_by("-created_at")[:10],
        "batches": ProductionBatch.objects.select_related("recipe", "recipe__product").exclude(
            status__in=(ProductionBatch.Status.REJECTED, ProductionBatch.Status.CANCELLED)
        ).order_by("-created_at"),
        "selected_batch": selected_batch,
        "batch_outputs": (
            ProductionOutput.objects.filter(batch=selected_batch).select_related("product")
            if selected_batch
            else ProductionOutput.objects.none()
        ),
        "batch_production_cards": batch_production_cards,
        "pending_batch_requests": ProductionBatch.objects.filter(
            status=ProductionBatch.Status.PENDING_APPROVAL
        ).order_by("-created_at"),
        "manufacturing_products": [
            product for product in Product.objects.filter(
                active=True,
                category=Product.Category.FINISHED_GOOD,
            ).order_by("name")
            if is_manufactured_product(product)
        ],
        "manufacturing_stock_rows": [
            row for row in factory_product_rows
            if row["product"].category == Product.Category.FINISHED_GOOD
            and production_product_family(row["product"]) in (
                "effective_diet",
                "pressure_masala",
                "honey",
            )
        ],
        "manufacturing_groups": _manufacturing_groups(),
        "raw_honey_product": raw_honey_product,
        "honey_jar_product": honey_jar_product,
        "raw_honey_stock": factory_material_balances.get(raw_honey_product.pk, Decimal("0")) if raw_honey_product else Decimal("0"),
        "honey_jar_stock": factory_material_balances.get(honey_jar_product.pk, Decimal("0")) if honey_jar_product else Decimal("0"),
        "dispatches": (
            Transfer.objects.filter(items__batch=selected_batch).distinct()
            if selected_batch
            else Transfer.objects.all()
        ).select_related("destination").order_by("-dispatched_at")[:10],
        "stock_count": stock_count,
        "purchase_count": purchases.count(),
        "batch_count": ProductionBatch.objects.count(),
        "dispatch_count": (
            Transfer.objects.filter(items__batch=selected_batch).distinct().count()
            if selected_batch
            else Transfer.objects.count()
        ),
        "finished_products": [
            product
            for product in Product.objects.filter(
                active=True,
                category=Product.Category.FINISHED_GOOD,
            ).order_by("name")
            if is_manufactured_product(product)
        ],
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


def branch_batches_for_location(location):
    return ProductionBatch.objects.filter(
        status__in=(
            ProductionBatch.Status.ACTIVE,
            ProductionBatch.Status.COMPLETED,
            ProductionBatch.Status.CLOSED,
        ),
    ).filter(
        Q(
            inventory_movements__location=location,
            inventory_movements__quantity__gt=0,
        )
        | Q(
            transfer_items__transfer__destination=location,
            transfer_items__transfer__status__in=(
                Transfer.Status.DISPATCHED,
                Transfer.Status.PARTIAL,
            ),
        )
    ).distinct()


def branch_daily_report_snapshot(location, batch, report_date):
    branch_role = (
        "BRANCH_MWANZA"
        if location.location_type == StockLocation.LocationType.BRANCH_MWANZA
        else "BRANCH_DAR"
    )
    visits = CustomerVisit.objects.filter(
        location=location,
        visited_at__date=report_date,
    )
    visit_summary = visits.aggregate(
        new_customers=Count(
            "pk",
            filter=Q(visit_type=CustomerVisit.VisitType.NEW_CUSTOMER),
        ),
        returning_customers=Count(
            "pk",
            filter=Q(visit_type=CustomerVisit.VisitType.RETURNING_CUSTOMER),
        ),
        visitors=Count(
            "pk",
            filter=Q(visit_type__in=(
                CustomerVisit.VisitType.CUSTOMER_INQUIRY,
                CustomerVisit.VisitType.MANAGEMENT_GUEST,
                CustomerVisit.VisitType.GOVERNMENT_OFFICIAL,
                CustomerVisit.VisitType.OTHER,
            )),
        ),
    )
    deliveries = BranchDelivery.objects.filter(
        location=location,
        delivery_date=report_date,
    ).aggregate(deliveries=Count("pk"), parcels=Sum("parcel_count"))
    calls = CustomerCall.objects.filter(
        Q(location=location)
        | Q(
            location__isnull=True,
            called_by__role=branch_role,
            customer__location=location,
        ),
        called_at__date=report_date,
    )
    sales_items = SaleItem.objects.filter(
        sale__location=location,
        sale__sold_at__date=report_date,
        batch=batch,
    )
    stock = InventoryLedger.objects.filter(
        location=location,
        production_batch=batch,
        product__category=Product.Category.FINISHED_GOOD,
    ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
    loss = InventoryLedger.objects.filter(
        location=location,
        production_batch=batch,
        movement=InventoryLedger.Movement.LOSS,
        created_at__date=report_date,
    ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
    addresses = sorted({
        address.strip()
        for address in visits.exclude(customer__address="")
        .values_list("customer__address", flat=True)
        if address and address.strip()
    })
    return {
        "units_sold": sales_items.aggregate(total=Sum("quantity"))["total"] or Decimal("0"),
        "closing_balance": stock,
        "loss_quantity": abs(loss),
        "total_customers": (
            visit_summary["new_customers"] + visit_summary["returning_customers"]
        ),
        "new_customers": visit_summary["new_customers"],
        "returning_customers": visit_summary["returning_customers"],
        "visitors": visit_summary["visitors"],
        "deliveries": deliveries["deliveries"],
        "parcels": deliveries["parcels"] or 0,
        "instruction_calls": calls.filter(
            call_type=CustomerCall.CallType.INSTRUCTION,
        ).count(),
        "compliance_calls": calls.filter(
            call_type=CustomerCall.CallType.COMPLIANCE,
        ).count(),
        "followup_calls": calls.filter(
            call_type=CustomerCall.CallType.FOLLOW_UP,
        ).count(),
        "customer_addresses": "\n".join(addresses),
    }


def branch_dashboard_data(location_type, selected_batch=None):
    today = timezone.localdate()
    location = StockLocation.objects.filter(location_type=location_type).first()
    location_name = location_type
    stock = (
        InventoryLedger.objects.filter(
            location=location,
            **(
                {
                    "production_batch": selected_batch,
                    "product__category": Product.Category.FINISHED_GOOD,
                }
                if selected_batch
                else {}
            ),
        ).aggregate(total=Sum("quantity"))["total"]
        if location
        else None
    )
    sales = Sale.objects.filter(location=location) if location else Sale.objects.none()
    incoming = (
        Transfer.objects.filter(
            destination=location,
            status__in=(Transfer.Status.DISPATCHED, Transfer.Status.PARTIAL),
        ).prefetch_related("items__product", "items__batch")
        if location
        else Transfer.objects.none()
    )
    incoming_notification_count = incoming.count()
    if selected_batch:
        sales = sales.filter(items__batch=selected_batch).distinct()
        incoming = incoming.filter(items__batch=selected_batch).distinct()
    sales_today = sales.filter(sold_at__date=today).aggregate(total=Sum("total_amount"))["total"]
    finished_stock_rows = []
    package_product = Product.objects.filter(sku="ED-PK-FULL", active=True).first()
    package_balance = Decimal("0")
    if package_product:
        package_entries = InventoryLedger.objects.filter(location=location, product=package_product)
        if selected_batch:
            package_entries = package_entries.filter(production_batch=selected_batch)
        package_balance = package_entries.aggregate(total=Sum("quantity"))["total"] or Decimal("0")

    finished_products = list(
        Product.objects.filter(
            active=True,
            category=Product.Category.FINISHED_GOOD,
        ).order_by("name")
    )
    product_ids = [product.pk for product in finished_products if product != package_product]
    ledger_entries = InventoryLedger.objects.filter(
        location=location,
        product_id__in=product_ids,
    ) if location else InventoryLedger.objects.none()
    if selected_batch:
        ledger_entries = ledger_entries.filter(production_batch=selected_batch)
    stock_by_product = dict(
        ledger_entries.values("product_id")
        .annotate(balance=Sum("quantity"))
        .values_list("product_id", "balance")
    )

    component_labels = {
        "ED-SINGLE": "Effective Diet",
        "PRESHA-SINGLE": "Pressure Masala",
        "HONEY-SINGLE": "Wild Honey / Asali",
    }
    for product in finished_products:
        if product.sku == "ED-PK-FULL":
            continue
        balance = stock_by_product.get(product.pk) or Decimal("0")
        if product.sku in component_labels:
            balance += package_balance
        finished_stock_rows.append({
            "product": product,
            "display_name": component_labels.get(product.sku, product.name),
            "balance": balance,
        })
    branch_role = (
        "BRANCH_MWANZA"
        if location_type == StockLocation.LocationType.BRANCH_MWANZA
        else "BRANCH_DAR"
    )
    branch_call_filter = (
        Q(location=location)
        | Q(location__isnull=True, called_by__role=branch_role, customer__location=location)
    )
    branch_calls = CustomerCall.objects.filter(
        branch_call_filter,
    ).select_related("customer", "called_by", "location").order_by("-called_at")[:20]
    customers = (
        Customer.objects.filter(location=location).annotate(
            branch_visit_count=Count(
                "visits",
                filter=Q(visits__visit_type__in=(
                    CustomerVisit.VisitType.NEW_CUSTOMER,
                    CustomerVisit.VisitType.RETURNING_CUSTOMER,
                )),
            )
        )
        if location
        else Customer.objects.none()
    )
    all_branch_calls = (
        CustomerCall.objects.filter(branch_call_filter)
        if location
        else CustomerCall.objects.none()
    )
    branch_followups = all_branch_calls.filter(follow_up_date__gte=today)
    customer_areas = sorted({
        address.strip()
        for address in customers.filter(active=True).exclude(address="").values_list("address", flat=True)
        if address.strip()
    })
    recent_reports = BranchDailyReport.objects.filter(location=location_type).select_related(
        "submitted_by", "approved_by"
    )
    today_visits = CustomerVisit.objects.filter(
        location=location,
        visited_at__date=today,
    ) if location else CustomerVisit.objects.none()
    today_deliveries = BranchDelivery.objects.filter(
        location=location,
        delivery_date=today,
    ) if location else BranchDelivery.objects.none()
    expenses = BranchExpense.objects.filter(location=location_name)
    if selected_batch:
        expenses = expenses.filter(batch=selected_batch)
        recent_reports = recent_reports.filter(batch=selected_batch)
    current_daily_report = recent_reports.filter(report_date=today).order_by("-created_at").first()
    recent_expenses = expenses.select_related("recorded_by").order_by("-recorded_at")[:5]
    recent_deliveries = BranchDelivery.objects.filter(
        location=location,
    ).select_related("customer", "recorded_by")[:30] if location else BranchDelivery.objects.none()
    recent_visits = CustomerVisit.objects.filter(
        location=location,
    ).select_related("customer", "recorded_by")[:30] if location else CustomerVisit.objects.none()
    activity_items = []
    for sale in sales.select_related("customer").order_by("-sold_at")[:5]:
        activity_items.append({
            "at": sale.sold_at,
            "icon": "bi-cart-check",
            "kind": "Sale",
            "title": sale.customer.name if sale.customer else "Walk-in sale",
            "detail": f"{sale.reference} · TZS {sale.total_amount:,.0f}",
            "view": "sales",
        })
    for visit in recent_visits[:5]:
        activity_items.append({
            "at": visit.visited_at,
            "icon": "bi-person-check",
            "kind": "Customer / visitor",
            "title": visit.contact_name,
            "detail": visit.get_visit_type_display(),
            "view": "visitors",
        })
    for delivery in recent_deliveries[:5]:
        activity_items.append({
            "at": delivery.created_at,
            "icon": "bi-box-seam",
            "kind": "Delivery",
            "title": delivery.recipient_name,
            "detail": f"{delivery.parcel_count} parcels · {delivery.get_status_display()}",
            "view": "deliveries",
        })
    for call in branch_calls[:5]:
        activity_items.append({
            "at": call.called_at,
            "icon": "bi-telephone",
            "kind": "Customer call",
            "title": call.contact_name or "Customer contact",
            "detail": f"{call.get_direction_display()} · {call.get_call_type_display() or call.outcome}",
            "view": "calls",
        })
    for expense in recent_expenses:
        activity_items.append({
            "at": expense.recorded_at,
            "icon": "bi-receipt",
            "kind": "Expense",
            "title": expense.category,
            "detail": f"TZS {expense.amount:,.0f}",
            "view": "expenses",
        })
    recent_branch_transfers = Transfer.objects.filter(
        destination=location,
    ).select_related("dispatched_by").order_by("-dispatched_at")[:5] if location else Transfer.objects.none()
    for transfer in recent_branch_transfers:
        activity_items.append({
            "at": transfer.received_at or transfer.dispatched_at,
            "icon": "bi-truck",
            "kind": "Transfer",
            "title": transfer.reference,
            "detail": transfer.get_status_display(),
            "view": "transfers",
        })
    activity_items.sort(key=lambda activity: activity["at"], reverse=True)
    branch_batches = branch_batches_for_location(location)
    available_batches = list(branch_batches.select_related("recipe__product"))
    batch_balances = dict(
        InventoryLedger.objects.filter(
            location=location,
            production_batch_id__in=[row.pk for row in available_batches],
            product__category=Product.Category.FINISHED_GOOD,
        )
        .values("production_batch_id")
        .annotate(balance=Sum("quantity"))
        .values_list("production_batch_id", "balance")
    )
    return {
        "batches": [
            {
                "batch": row,
                "balance": batch_balances.get(row.pk, Decimal("0")),
            }
            for row in available_batches
            if not selected_batch or row.pk == selected_batch.pk
        ],
        "selected_batch": selected_batch,
        "available_batches": branch_batches,
        "daily_report_snapshot": (
            branch_daily_report_snapshot(location, selected_batch, today)
            if location and selected_batch
            else None
        ),
        "can_submit_daily_report": bool(
            location
            and selected_batch
            and InventoryLedger.objects.filter(
                location=location,
                production_batch=selected_batch,
                quantity__gt=0,
            ).exists()
        ),
        "location": location,
        "stock": stock or Decimal("0"),
        "finished_stock_rows": finished_stock_rows,
        "sales_today": sales_today,
        "incoming_transfers": incoming,
        "incoming_transfer_notification_count": incoming_notification_count,
        "recent_sales": sales.select_related("customer").prefetch_related("items")[:10],
        "expenses": expenses.order_by("-expense_date")[:10],
        "open_followups": CustomerCall.objects.filter(
            branch_call_filter,
            follow_up_date__gte=today,
        ).select_related("customer", "location")[:10],
        "recent_calls": branch_calls,
        "call_direction_choices": (
            (CustomerCall.Direction.INBOUND, CustomerCall.Direction.INBOUND.label),
            (CustomerCall.Direction.OUTBOUND, CustomerCall.Direction.OUTBOUND.label),
        ),
        "call_type_choices": CustomerCall.CallType.choices,
        "branch_customers": customers,
        "recent_visits": recent_visits,
        "recent_deliveries": recent_deliveries,
        "recent_activity": activity_items[:12],
        "recent_branch_transfers": recent_branch_transfers,
        "recent_expenses": recent_expenses,
        "visitor_visit_types": (
            (CustomerVisit.VisitType.CUSTOMER_INQUIRY, CustomerVisit.VisitType.CUSTOMER_INQUIRY.label),
            (CustomerVisit.VisitType.MANAGEMENT_GUEST, CustomerVisit.VisitType.MANAGEMENT_GUEST.label),
            (CustomerVisit.VisitType.GOVERNMENT_OFFICIAL, CustomerVisit.VisitType.GOVERNMENT_OFFICIAL.label),
            (CustomerVisit.VisitType.OTHER, CustomerVisit.VisitType.OTHER.label),
        ),
        "delivery_status_choices": BranchDelivery.Status.choices,
        "today_new_customers": today_visits.filter(visit_type=CustomerVisit.VisitType.NEW_CUSTOMER).count(),
        "today_returning_customers": today_visits.filter(visit_type=CustomerVisit.VisitType.RETURNING_CUSTOMER).count(),
        "today_visitors": today_visits.filter(visit_type__in=(
            CustomerVisit.VisitType.CUSTOMER_INQUIRY,
            CustomerVisit.VisitType.MANAGEMENT_GUEST,
            CustomerVisit.VisitType.GOVERNMENT_OFFICIAL,
            CustomerVisit.VisitType.OTHER,
        )).count(),
        "today_delivery_count": today_deliveries.count(),
        "today_parcel_count": today_deliveries.aggregate(total=Sum("parcel_count"))["total"] or 0,
        "customer_count": customers.filter(active=True).count(),
        "customer_call_count": all_branch_calls.count(),
        "open_followup_count": branch_followups.count(),
        "customer_areas": customer_areas,
        "recent_reports": recent_reports[:10],
        "current_daily_report": current_daily_report,
        "finished_products": [
            product for product in finished_products
            if is_manufactured_product(product) or is_full_package_product(product)
        ],
        "raw_materials": Product.objects.filter(
            active=True,
            category=Product.Category.RAW_MATERIAL,
        ),
        "packaging_products": Product.objects.filter(
            active=True,
            category=Product.Category.PACKAGING,
        ),
    }


def manager_dashboard_data(selected_batch=None):
    today = timezone.localdate()
    month_start = today.replace(day=1)
    finished_products = list(
        Product.objects.filter(
            active=True,
            category=Product.Category.FINISHED_GOOD,
        ).order_by("name")
    )

    factory = StockLocation.objects.filter(
        location_type=StockLocation.LocationType.FACTORY
    ).first()
    mwanza = StockLocation.objects.filter(
        location_type=StockLocation.LocationType.BRANCH_MWANZA
    ).first()
    dar = StockLocation.objects.filter(
        location_type=StockLocation.LocationType.BRANCH_DAR
    ).first()
    batch_sale_items = (
        SaleItem.objects.filter(batch=selected_batch)
        if selected_batch
        else None
    )
    batch_sales = (
        Sale.objects.filter(items__batch=selected_batch).distinct()
        if selected_batch
        else Sale.objects.all()
    )
    batch_production = (
        ProductionBatch.objects.filter(pk=selected_batch.pk)
        if selected_batch
        else ProductionBatch.objects.all()
    )
    batch_transfer_items = (
        TransferItem.objects.filter(batch=selected_batch)
        if selected_batch
        else None
    )
    batch_ledger = (
        InventoryLedger.objects.filter(production_batch=selected_batch)
        if selected_batch
        else InventoryLedger.objects.all()
    )
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
    batch_opening_balances, batch_purchase_balances, batch_balances = _batch_material_balances(
        factory,
        list(purchase_products),
        selected_batch,
    )
    purchase_product_rows = [
        {
            "product": product,
            "balance": factory_product_balances.get(product.pk) or Decimal("0"),
            "batch_balance": (
                batch_opening_balances.get(product.pk, Decimal("0"))
                + batch_balances.get(product.pk, Decimal("0"))
            ),
            "batch_opening_balance": batch_opening_balances.get(product.pk, Decimal("0")),
            "batch_purchase_quantity": batch_purchase_balances.get(product.pk, Decimal("0")),
        }
        for product in purchase_products
    ]
    raw_honey_product = Product.objects.filter(
        sku="RAW-RAW-HONEY",
        category=Product.Category.RAW_MATERIAL,
    ).first()
    purchase_product_balances = {
        row["product"].pk: row["balance"]
        for row in purchase_product_rows
    }
    honey_jar_product = Product.objects.filter(
        sku="PKG-HONEY-CANS",
        category=Product.Category.PACKAGING,
    ).first()

    def location_stock(location):
        if not location:
            return Decimal("0")
        entries = InventoryLedger.objects.filter(location=location)
        if selected_batch:
            entries = entries.filter(
                production_batch=selected_batch,
                product__category=Product.Category.FINISHED_GOOD,
            )
        total = entries.aggregate(total=Sum("quantity"))["total"]
        return total or Decimal("0")

    def location_losses(location, start=None):
        entries = InventoryLedger.objects.filter(
            location=location,
            movement=InventoryLedger.Movement.LOSS,
        ) if location else InventoryLedger.objects.none()
        if selected_batch:
            entries = entries.filter(
                production_batch=selected_batch,
                product__category=Product.Category.FINISHED_GOOD,
            )
        if start:
            entries = entries.filter(created_at__date__gte=start)
        total = entries.aggregate(total=Sum("quantity"))["total"]
        if not total:
            return Decimal("0")
        return abs(total)

    def branch_data(location):
        sales = batch_sales.filter(location=location) if location else Sale.objects.none()
        customers = (
            Customer.objects.filter(location=location, active=True)
            if location
            else Customer.objects.none()
        )
        customer_calls = (
            CustomerCall.objects.filter(
                Q(location=location)
                | Q(
                    location__isnull=True,
                    called_by__role=location.location_type,
                    customer__location=location,
                )
            )
            if location
            else CustomerCall.objects.none()
        )
        customer_followups = customer_calls.filter(follow_up_date__gte=today)
        branch_visits = CustomerVisit.objects.filter(
            location=location,
            visited_at__date=today,
        ) if location else CustomerVisit.objects.none()
        branch_deliveries = BranchDelivery.objects.filter(
            location=location,
            delivery_date=today,
        ) if location else BranchDelivery.objects.none()
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
            Transfer.objects.filter(
                destination=location,
                status__in=(Transfer.Status.DISPATCHED, Transfer.Status.PARTIAL),
            )
            if location
            else Transfer.objects.none()
        )
        if selected_batch:
            incoming = incoming.filter(items__batch=selected_batch).distinct()
        product_ids = [product.pk for product in finished_products]
        branch_ledger = InventoryLedger.objects.filter(
            location=location,
            product_id__in=product_ids,
        ) if location else InventoryLedger.objects.none()
        if selected_batch:
            branch_ledger = branch_ledger.filter(production_batch=selected_batch)
        stock_by_product = {
            row["product_id"]: row
            for row in branch_ledger.values("product_id").annotate(
                balance=Sum("quantity"),
                loss=Sum(
                    "quantity",
                    filter=Q(movement=InventoryLedger.Movement.LOSS),
                ),
            )
        }
        sold_today_by_product = {}
        if location:
            branch_sale_items = SaleItem.objects.filter(
                sale__location=location,
                sale__sold_at__date=today,
                product_id__in=product_ids,
            )
            if selected_batch:
                branch_sale_items = branch_sale_items.filter(batch=selected_batch)
            sold_today_by_product = dict(
                branch_sale_items.values("product_id")
                .annotate(total=Sum("quantity"))
                .values_list("product_id", "total")
            )
        product_rows = []
        for product in finished_products:
            stock_row = stock_by_product.get(product.pk, {})
            product_rows.append({
                "product": product,
                "sold_today": sold_today_by_product.get(product.pk) or Decimal("0"),
                "balance": stock_row.get("balance") or Decimal("0"),
                "loss": abs(stock_row.get("loss") or Decimal("0")),
            })
        expenses = (
            BranchExpense.objects.filter(location=location.location_type)
            if location
            else BranchExpense.objects.none()
        )
        reports = (
            BranchDailyReport.objects.filter(location=location.location_type)
            if location
            else BranchDailyReport.objects.none()
        )
        if selected_batch:
            expenses = expenses.filter(batch=selected_batch)
            reports = reports.filter(batch=selected_batch)
        return {
            "location": location,
            "sales_today": sales_today,
            "sales_month": sales_month,
            "stock": location_stock(location),
            "loss_today": location_losses(location, today),
            "incoming_count": incoming.count(),
            "incoming_notification_count": (
                Transfer.objects.filter(
                    destination=location,
                    status__in=(Transfer.Status.DISPATCHED, Transfer.Status.PARTIAL),
                ).count()
                if location
                else 0
            ),
            "incoming_transfers": incoming.select_related("dispatched_by").prefetch_related("items__product")[:10],
            "product_rows": product_rows,
            "customer_count": customers.count(),
            "customer_visits_today": branch_visits.filter(visit_type__in=(
                CustomerVisit.VisitType.NEW_CUSTOMER,
                CustomerVisit.VisitType.RETURNING_CUSTOMER,
            )).count(),
            "new_customers_today": branch_visits.filter(visit_type=CustomerVisit.VisitType.NEW_CUSTOMER).count(),
            "returning_customers_today": branch_visits.filter(visit_type=CustomerVisit.VisitType.RETURNING_CUSTOMER).count(),
            "visitors_today": branch_visits.filter(visit_type__in=(
                CustomerVisit.VisitType.CUSTOMER_INQUIRY,
                CustomerVisit.VisitType.MANAGEMENT_GUEST,
                CustomerVisit.VisitType.GOVERNMENT_OFFICIAL,
                CustomerVisit.VisitType.OTHER,
            )).count(),
            "delivery_count_today": branch_deliveries.count(),
            "parcel_count_today": branch_deliveries.aggregate(total=Sum("parcel_count"))["total"] or 0,
            "customer_call_count": customer_calls.count(),
            "open_followup_count": customer_followups.count(),
            "customer_areas": customer_areas,
            "expenses": expenses.order_by("-expense_date")[:10],
            "reports": reports.select_related("submitted_by", "approved_by").order_by("-report_date")[:10],
        }

    sales_today = batch_sales.filter(sold_at__date=today).aggregate(
        total=Sum("total_amount")
    )["total"] or Decimal("0")
    sales_month = batch_sales.filter(sold_at__date__gte=month_start).aggregate(
        total=Sum("total_amount")
    )["total"] or Decimal("0")
    legacy_production_today = batch_production.filter(
        recipe__isnull=False,
        production_date=today,
        status=ProductionBatch.Status.COMPLETED,
    ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
    output_production_today = ProductionOutput.objects.filter(production_date=today)
    legacy_production_month = batch_production.filter(
        recipe__isnull=False,
        production_date__gte=month_start,
        status=ProductionBatch.Status.COMPLETED,
    ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
    output_production_month = ProductionOutput.objects.filter(
        production_date__gte=month_start,
    )
    if selected_batch:
        output_production_today = output_production_today.filter(batch=selected_batch)
        output_production_month = output_production_month.filter(batch=selected_batch)
    production_today = legacy_production_today + (
        output_production_today.aggregate(total=Sum("quantity"))["total"] or Decimal("0")
    )
    production_month = legacy_production_month + (
        output_production_month.aggregate(total=Sum("quantity"))["total"] or Decimal("0")
    )
    purchases = Purchase.objects.all()
    if selected_batch:
        purchases = purchases.filter(batch=selected_batch)
    purchase_month = purchases.filter(
        purchase_date__gte=month_start
    ).aggregate(total=Sum("total_amount"))["total"] or Decimal("0")
    purchase_total = purchases.aggregate(
        total=Sum("total_amount")
    )["total"] or Decimal("0")
    loss_month = location_losses(factory, month_start)
    if not factory:
        loss_month = InventoryLedger.objects.filter(
            movement=InventoryLedger.Movement.LOSS,
            created_at__date__gte=month_start,
        ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
        loss_month = abs(loss_month)

    sales_trend_week_start = today - timedelta(days=today.weekday())
    sales_trend_week_end = sales_trend_week_start + timedelta(days=6)
    weekdays = ("Jumatatu", "Jumanne", "Jumatano", "Alhamisi", "Ijumaa", "Jumamosi", "Jumapili")
    trend_location_ids = [location.pk for location in (mwanza, dar) if location]
    trend_sales = Sale.objects.filter(
        location_id__in=trend_location_ids,
        sold_at__date__range=(sales_trend_week_start, sales_trend_week_end),
    )
    if selected_batch:
        trend_sales = trend_sales.filter(
            pk__in=SaleItem.objects.filter(batch=selected_batch).values("sale_id")
        )
    weekly_sales = {
        (row["sold_at__date"], row["location_id"]): row["total"]
        for row in trend_sales
        .values("sold_at__date", "location_id")
        .annotate(total=Sum("total_amount"))
    }
    sales_trend_labels = []
    sales_trend_mwanza = []
    sales_trend_dar = []
    for day_offset in range(7):
        sales_date = sales_trend_week_start + timedelta(days=day_offset)
        sales_trend_labels.append(
            f"{weekdays[day_offset]} {sales_date.strftime('%d/%m')}"
        )
        for location, values in ((mwanza, sales_trend_mwanza), (dar, sales_trend_dar)):
            daily_total = weekly_sales.get((sales_date, location.pk), Decimal("0")) if location else Decimal("0")
            values.append(float(daily_total))

    recent_call_counts = {
        "instruction": CustomerCall.objects.filter(
            call_type=CustomerCall.CallType.INSTRUCTION
        ).count(),
        "compliance": CustomerCall.objects.filter(
            call_type=CustomerCall.CallType.COMPLIANCE
        ).count(),
        "followup": CustomerCall.objects.filter(
            call_type=CustomerCall.CallType.FOLLOW_UP
        ).count(),
        "due_today": CustomerCall.objects.filter(follow_up_date=today).count(),
    }
    production_by_product = []
    production_product_labels = []
    production_product_totals = []
    manufactured_products = [
        product for product in finished_products
        if is_manufactured_product(product)
    ]
    if selected_batch:
        batch_product_ids = set(
            ProductionOutput.objects.filter(batch=selected_batch)
            .values_list("product_id", flat=True)
        )
        if selected_batch.recipe_id:
            batch_product_ids.add(selected_batch.recipe.product_id)
        production_products = [
            product for product in manufactured_products
            if product.pk in batch_product_ids
        ]
    else:
        production_products = manufactured_products
    production_product_ids = [product.pk for product in production_products]
    output_month_query = ProductionOutput.objects.filter(
        product_id__in=production_product_ids,
        production_date__gte=month_start,
    )
    output_all_query = ProductionOutput.objects.filter(
        product_id__in=production_product_ids,
    )
    legacy_month_query = ProductionBatch.objects.filter(
        recipe__product_id__in=production_product_ids,
        production_date__gte=month_start,
        status=ProductionBatch.Status.COMPLETED,
    )
    legacy_all_query = ProductionBatch.objects.filter(
        recipe__product_id__in=production_product_ids,
        status=ProductionBatch.Status.COMPLETED,
    )
    if selected_batch:
        output_month_query = output_month_query.filter(batch=selected_batch)
        output_all_query = output_all_query.filter(batch=selected_batch)
        legacy_month_query = legacy_month_query.filter(pk=selected_batch.pk)
        legacy_all_query = legacy_all_query.filter(pk=selected_batch.pk)
    monthly_output_totals = dict(
        output_month_query.values("product_id")
        .annotate(total=Sum("quantity"))
        .values_list("product_id", "total")
    )
    all_output_totals = dict(
        output_all_query.values("product_id")
        .annotate(total=Sum("quantity"))
        .values_list("product_id", "total")
    )
    monthly_legacy_totals = dict(
        legacy_month_query.values("recipe__product_id")
        .annotate(total=Sum("quantity"))
        .values_list("recipe__product_id", "total")
    )
    all_legacy_totals = dict(
        legacy_all_query.values("recipe__product_id")
        .annotate(total=Sum("quantity"))
        .values_list("recipe__product_id", "total")
    )
    production_stock_query = InventoryLedger.objects.filter(
        product_id__in=production_product_ids,
        location_id__in=[location.pk for location in (factory, mwanza, dar) if location],
    )
    if selected_batch:
        production_stock_query = production_stock_query.filter(production_batch=selected_batch)
    production_stock = {
        (row["product_id"], row["location_id"]): row["total"]
        for row in production_stock_query.values(
            "product_id",
            "location_id",
        ).annotate(total=Sum("quantity"))
    }
    for product in production_products:
        total = (
            monthly_output_totals.get(product.pk) or Decimal("0")
        ) + (
            monthly_legacy_totals.get(product.pk) or Decimal("0")
        )
        produced_total = (
            all_output_totals.get(product.pk) or Decimal("0")
        ) + (
            all_legacy_totals.get(product.pk) or Decimal("0")
        )
        factory_balance = production_stock.get((product.pk, factory.pk), Decimal("0")) if factory else Decimal("0")
        mwanza_balance = production_stock.get((product.pk, mwanza.pk), Decimal("0")) if mwanza else Decimal("0")
        dar_balance = production_stock.get((product.pk, dar.pk), Decimal("0")) if dar else Decimal("0")
        production_by_product.append({
            "product": product,
            "total": total,
            "produced_total": produced_total,
            "factory_balance": factory_balance,
            "mwanza_balance": mwanza_balance,
            "dar_balance": dar_balance,
            "current_stock": factory_balance + mwanza_balance + dar_balance,
        })
        production_product_labels.append(product.name)
        production_product_totals.append(float(total))

    manufacturing_groups = _manufacturing_groups()
    production_cards = []
    product_totals = {row["product"].pk: row for row in production_by_product}
    for group in manufacturing_groups:
        members = [product_totals[product.pk] for product in group["products"] if product.pk in product_totals]
        production_cards.append({
            "name": group["name"],
            "products": group["products"],
            "total": sum((row["total"] for row in members), Decimal("0")),
            "factory_balance": sum((row["factory_balance"] for row in members), Decimal("0")),
            "mwanza_balance": sum((row["mwanza_balance"] for row in members), Decimal("0")),
            "dar_balance": sum((row["dar_balance"] for row in members), Decimal("0")),
        })

    sales_report_product_totals = []
    report_products = production_products if selected_batch else finished_products
    report_product_ids = [product.pk for product in report_products]
    sold_items = SaleItem.objects.filter(product_id__in=report_product_ids)
    if selected_batch:
        sold_items = sold_items.filter(batch=selected_batch)
    sold_by_product = dict(
        sold_items.values("product_id")
        .annotate(total=Sum("quantity"))
        .values_list("product_id", "total")
    )
    report_stock_entries = InventoryLedger.objects.filter(
        product_id__in=report_product_ids,
        location_id__in=[location.pk for location in (factory, mwanza, dar) if location],
    )
    if selected_batch:
        report_stock_entries = report_stock_entries.filter(production_batch=selected_batch)
    report_stock_by_product_location = {
        (row["product_id"], row["location_id"]): row["total"]
        for row in report_stock_entries.values(
            "product_id",
            "location_id",
        ).annotate(total=Sum("quantity"))
    }
    for product in report_products:
        sold_total = sold_by_product.get(product.pk) or Decimal("0")
        factory_balance = report_stock_by_product_location.get(
            (product.pk, factory.pk), Decimal("0")
        ) if factory else Decimal("0")
        mwanza_balance = report_stock_by_product_location.get(
            (product.pk, mwanza.pk), Decimal("0")
        ) if mwanza else Decimal("0")
        dar_balance = report_stock_by_product_location.get(
            (product.pk, dar.pk), Decimal("0")
        ) if dar else Decimal("0")
        sales_report_product_totals.append({
            "product": product,
            "sold": sold_total,
            "factory_balance": factory_balance,
            "mwanza_balance": mwanza_balance,
            "dar_balance": dar_balance,
        })

    pending_branch_reports = BranchDailyReport.objects.filter(
        status=BranchDailyReport.Status.SUBMITTED,
    ).select_related(
        "submitted_by",
        "approved_by",
    ).order_by("-report_date", "-created_at")
    pending_branch_report_count = pending_branch_reports.count()
    branch_reports = pending_branch_reports[:20]
    office_report_status = {}
    for office_key, location_type in (
        ("mwanza", StockLocation.LocationType.BRANCH_MWANZA),
        ("dar", StockLocation.LocationType.BRANCH_DAR),
    ):
        office_reports = BranchDailyReport.objects.filter(location=location_type)
        office_report_status[office_key] = {
            "pending_count": office_reports.filter(
                status=BranchDailyReport.Status.SUBMITTED,
            ).count(),
            "latest_pending": office_reports.filter(
                status=BranchDailyReport.Status.SUBMITTED,
            ).select_related("submitted_by").order_by(
                "-report_date",
                "-created_at",
            ).first(),
            "latest": office_reports.select_related(
                "submitted_by",
                "approved_by",
            ).order_by("-report_date", "-created_at").first(),
        }

    pending_transfer_count = Transfer.objects.filter(
        destination__location_type__in=(
            StockLocation.LocationType.BRANCH_MWANZA,
            StockLocation.LocationType.BRANCH_DAR,
        ),
        status__in=(Transfer.Status.DISPATCHED, Transfer.Status.PARTIAL),
    ).count()

    footer_product_values = []
    for row in sales_report_product_totals[:3]:
        footer_product_values.append({
            "sold": row["sold"],
            "balance": (row["mwanza_balance"] + row["dar_balance"]),
        })
    while len(footer_product_values) < 3:
        footer_product_values.append({"sold": Decimal("0"), "balance": Decimal("0")})

    mwanza_data = branch_data(mwanza)
    dar_data = branch_data(dar)

    factory_material_data = _factory_material_data(factory, selected_batch)
    return {
        **factory_material_data,
        "today": today,
        "month_start": month_start,
        "sales_total": batch_sales.aggregate(total=Sum("total_amount"))["total"] or Decimal("0"),
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
        "purchase_count": purchases.count(),
        "batch_count": ProductionBatch.objects.exclude(
            status__in=(ProductionBatch.Status.REJECTED, ProductionBatch.Status.CANCELLED)
        ).count(),
        "transfer_count": (
            Transfer.objects.filter(items__batch=selected_batch).exclude(
                status=Transfer.Status.RECEIVED
            ).distinct().count()
            if selected_batch
            else Transfer.objects.exclude(status=Transfer.Status.RECEIVED).count()
        ),
        "recent_sales": batch_sales.select_related("location", "customer").order_by("-sold_at")[:10],
        "recent_purchases": purchases.select_related("supplier", "created_by").prefetch_related("items__product").order_by("-purchase_date", "-created_at")[:10],
        "recent_batches": (
            ProductionBatch.objects.filter(pk=selected_batch.pk)
            if selected_batch
            else ProductionBatch.objects.exclude(
                status__in=(ProductionBatch.Status.REJECTED, ProductionBatch.Status.CANCELLED)
            )
        ).select_related("recipe", "recipe__product", "created_by").order_by("-production_date", "-created_at")[:10],
        "batches": ProductionBatch.objects.select_related("recipe", "recipe__product").filter(
            status__in=(ProductionBatch.Status.ACTIVE, ProductionBatch.Status.COMPLETED, ProductionBatch.Status.CLOSED)
        ).order_by("-production_date", "-created_at"),
        "pending_batch_requests": ProductionBatch.objects.filter(
            status=ProductionBatch.Status.PENDING_APPROVAL
        ).select_related("created_by").order_by("-created_at"),
        "recent_transfers": (
            Transfer.objects.filter(items__batch=selected_batch).distinct()
            if selected_batch
            else Transfer.objects.all()
        ).select_related("destination", "dispatched_by").prefetch_related("items__product").order_by("-dispatched_at")[:10],
        "open_followups": CustomerCall.objects.filter(follow_up_date__gte=today).select_related("customer", "location").order_by("follow_up_date")[:10],
        "recent_calls": CustomerCall.objects.select_related("customer", "called_by", "location").order_by("-called_at")[:20],
        "call_type_choices": CustomerCall.CallType.choices,
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
        "raw_honey_product": raw_honey_product,
        "raw_honey_stock": purchase_product_balances.get(raw_honey_product.pk, Decimal("0")) if raw_honey_product else Decimal("0"),
        "honey_jar_stock": purchase_product_balances.get(honey_jar_product.pk, Decimal("0")) if honey_jar_product else Decimal("0"),
        "mwanza_data": mwanza_data,
        "dar_data": dar_data,
        "pending_branch_report_count": pending_branch_report_count,
        "pending_transfer_notification_count": pending_transfer_count,
        "office_notification_count": (
            pending_branch_report_count + pending_transfer_count
        ),
        "office_report_status": office_report_status,
        "incoming_transfer_notification_count": (
            mwanza_data["incoming_notification_count"]
            + dar_data["incoming_notification_count"]
        ),
        "sales_trend_labels": sales_trend_labels,
        "sales_trend_mwanza": sales_trend_mwanza,
        "sales_trend_dar": sales_trend_dar,
        "sales_trend_week_start": sales_trend_week_start,
        "sales_trend_week_end": sales_trend_week_end,
        "stock_split": [
            float(location_stock(factory)),
            float(location_stock(mwanza)),
            float(location_stock(dar)),
        ],
        "production_product_labels": production_product_labels,
        "production_product_totals": production_product_totals,
        "recent_call_counts": recent_call_counts,
        "production_by_product": production_by_product,
        "production_cards": production_cards,
        "manufacturing_products": [
            product for group in manufacturing_groups for product in group["products"]
        ],
        "manufacturing_groups": manufacturing_groups,
        "manufacturing_stock_rows": [
            row for row in production_by_product
            if production_product_family(row["product"]) in (
                "effective_diet",
                "pressure_masala",
                "honey",
            )
        ],
        "production_consumption_rows": factory_material_data["production_consumption_rows"],
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
