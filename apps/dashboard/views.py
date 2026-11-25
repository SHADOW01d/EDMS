from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import models, transaction
from django.http import FileResponse
from django.shortcuts import render
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST
from django.utils.crypto import get_random_string
from decimal import Decimal, InvalidOperation
from datetime import date, timedelta
import re
import uuid

from apps.accounts.models import User
from apps.inventory.models import InventoryLedger, Product, StockLocation
from apps.inventory.services import post_movement
from apps.procurement.models import Supplier, Purchase, PurchaseItem
from apps.procurement.services import receive_purchase
from apps.production.models import (
    ProductionBatch,
    ProductionOutput,
)
from apps.production.services import (
    complete_production_output,
    full_package_components,
    is_full_package_product,
    is_manufactured_product,
    production_product_family,
)
from apps.distribution.models import Transfer, TransferItem
from apps.distribution.services import receive_transfer as receive_transfer_service
from apps.sales.models import Sale, SaleItem
from apps.sales.services import confirm_sale
from apps.customers.models import (
    BranchDailyReport,
    BranchDelivery,
    BranchExpense,
    Customer,
    CustomerCall,
    CustomerVisit,
)
from apps.core.models import AuditEvent
from apps.core.services import record_audit_event
from .services import factory_dashboard_data, branch_dashboard_data, manager_dashboard_data
from apps.reports.exports import csv_response, branch_daily_report_pdf


def _location(location_type):
    names = {
        StockLocation.LocationType.FACTORY: "Factory",
        StockLocation.LocationType.BRANCH_MWANZA: "Mwanza",
        StockLocation.LocationType.BRANCH_DAR: "Dar es Salaam",
    }
    location, _ = StockLocation.objects.get_or_create(
        location_type=location_type,
        defaults={"name": names[location_type]},
    )
    return location


def _reference(prefix):
    stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{stamp}-{get_random_string(4).upper()}"


def _decimal(value):
    try:
        result = Decimal(str(value or "0"))
    except InvalidOperation as exc:
        raise ValueError("Invalid number") from exc
    if result < 0:
        raise ValueError("Number cannot be negative")
    return result


_VISITOR_VISIT_TYPES = (
    CustomerVisit.VisitType.CUSTOMER_INQUIRY,
    CustomerVisit.VisitType.MANAGEMENT_GUEST,
    CustomerVisit.VisitType.GOVERNMENT_OFFICIAL,
    CustomerVisit.VisitType.OTHER,
)


def _normalized_phone(value):
    digits = re.sub(r"\D", "", value or "")
    return f"0{digits[3:]}" if digits.startswith("255") else digits


def _branch_customers_matching_phone(location, phone):
    normalized_phone = _normalized_phone(phone)
    if not normalized_phone:
        return []
    return [
        customer
        for customer in Customer.objects.filter(location=location).exclude(phone="")
        if _normalized_phone(customer.phone) == normalized_phone
    ]


def _link_prior_visitor_records(location, customer, phone):
    normalized_phone = _normalized_phone(phone)
    if not normalized_phone:
        return 0
    prior_visits = CustomerVisit.objects.filter(
        location=location,
        customer__isnull=True,
        visit_type__in=_VISITOR_VISIT_TYPES,
    ).exclude(visitor_phone="")
    matching_ids = [
        visit_id
        for visit_id, saved_phone in prior_visits.values_list("pk", "visitor_phone")
        if _normalized_phone(saved_phone) == normalized_phone
    ]
    if matching_ids:
        CustomerVisit.objects.filter(pk__in=matching_ids).update(customer=customer)
    return len(matching_ids)


def _branch_dashboard_redirect(request, view=None):
    dashboard = (
        "mwanza_dashboard"
        if request.user.role == User.Role.BRANCH_MWANZA
        else "dar_dashboard"
    )
    url = reverse(dashboard)
    return redirect(f"{url}?view={view}" if view else url)


def _find_or_create_inventory_item(name, sku, unit, category):
    name = name.strip()
    sku = sku.strip().upper()
    unit = unit.strip()
    if not name:
        raise ValueError("Inventory item name is required.")
    if not sku:
        sku = "ITEM-" + get_random_string(8).upper()
    if not unit:
        raise ValueError("Inventory unit is required.")
    existing = Product.objects.filter(
        models.Q(name__iexact=name) | models.Q(sku__iexact=sku),
    ).first()
    if existing:
        if existing.category != category:
            raise ValueError(f"{existing.name} already exists in another inventory category.")
        if not existing.active:
            existing.active = True
            existing.save(update_fields=["active"])
        return existing
    return Product.objects.create(
        name=name,
        sku=sku,
        unit=unit,
        category=category,
    )


def _pricing_unit_for_product(product):
    unit = (product.unit or "").strip().lower()
    normalized = unit.replace("_", " ").replace("-", " ")
    if normalized in ("kg", "kilogram", "kilograms", "kilo", "kilos"):
        return PurchaseItem.PricingUnit.KG
    return PurchaseItem.PricingUnit.PIECE


@login_required(login_url="login")
def manager_dashboard(request):
    if not (request.user.is_superuser or request.user.role == User.Role.MANAGER):
        raise PermissionDenied("The manager dashboard is restricted to managers.")

    _location(StockLocation.LocationType.FACTORY)
    selected_batch_id = request.GET.get("batch")
    selected_batch = None
    if selected_batch_id:
        try:
            selected_batch = ProductionBatch.objects.select_related(
                "recipe__product",
                "created_by",
            ).get(
                pk=selected_batch_id,
                status__in=(
                    ProductionBatch.Status.ACTIVE,
                    ProductionBatch.Status.COMPLETED,
                    ProductionBatch.Status.CLOSED,
                    ProductionBatch.Status.PLANNED,
                ),
            )
        except ProductionBatch.DoesNotExist:
            selected_batch = None
    manager_name = request.user.get_full_name() or request.user.username
    return render(
        request,
        "dashboard/manager.html",
        {
            "manager_name": manager_name,
            "manager_initial": manager_name[:1].upper(),
            "dashboard_data_is_sample": False,
            "selected_batch": selected_batch,
            "production_request_key": uuid.uuid4(),
            "honey_bottling_request_key": uuid.uuid4(),
            "report_start_date": timezone.localdate() - timedelta(days=30),
            **manager_dashboard_data(selected_batch),
        },
    )


@login_required(login_url="login")
def export_manager_report(request):
    if not (request.user.is_superuser or request.user.role == User.Role.MANAGER):
        raise PermissionDenied("Only managers can export reports.")
    report_type = request.GET.get("type", "sales")
    if report_type == "branch_pdf":
        end_date = parse_date(request.GET.get("end_date", "")) or timezone.localdate()
        start_date = parse_date(request.GET.get("start_date", "")) or end_date - timedelta(days=30)
        branch = request.GET.get("branch", "all")
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        if (end_date - start_date).days > 30:
            start_date = end_date - timedelta(days=30)
        return branch_daily_report_pdf(start_date, end_date, branch)
    if report_type == "purchases":
        rows = [
            [
                purchase.reference,
                purchase.supplier.name,
                purchase.purchase_date,
                purchase.status,
                purchase.total_amount,
            ]
            for purchase in Purchase.objects.select_related("supplier").order_by("-purchase_date")
        ]
        return csv_response(
            "purchases.csv",
            ["Reference", "Supplier", "Date", "Status", "Total"],
            rows,
        )
    if report_type == "calls":
        rows = [
            [
                call.called_at,
                call.contact_name,
                call.caller_phone or (call.customer.phone if call.customer else ""),
                call.branch_location.name if call.branch_location else "",
                call.get_direction_display(),
                call.get_call_type_display() or "",
                call.outcome,
                call.notes,
                call.follow_up_date or "",
                call.called_by.username,
            ]
            for call in CustomerCall.objects.select_related("customer", "called_by").order_by("-called_at")
        ]
        return csv_response(
            "customer-calls.csv",
            ["Date", "Contact", "Phone", "Branch", "Direction", "Call type", "Outcome", "Notes", "Follow-up", "Recorded by"],
            rows,
        )
    rows = [
        [
            sale.reference,
            sale.location.name,
            sale.sold_at,
            sale.customer.name if sale.customer else "Walk-in",
            sale.total_amount,
        ]
        for sale in Sale.objects.select_related("location", "customer").order_by("-sold_at")
    ]
    return csv_response(
        "sales.csv",
        ["Reference", "Location", "Date", "Customer", "Total"],
        rows,
    )


@login_required(login_url="login")
@require_POST
@transaction.atomic
def update_catalog_product(request, product_id):
    if not (request.user.is_superuser or request.user.role == User.Role.MANAGER):
        raise PermissionDenied("Only managers can edit the product catalog.")
    try:
        product = Product.objects.select_for_update().get(pk=product_id)
        name = request.POST.get("name", "").strip()
        sku = request.POST.get("sku", "").strip()
        unit = request.POST.get("unit", "").strip()
        unit_price = _decimal(request.POST.get("unit_price"))
        if not name or not sku or not unit:
            raise ValueError("Name, SKU, and unit are required.")
        if Product.objects.exclude(pk=product.pk).filter(sku=sku).exists():
            raise ValueError("That SKU is already used by another product.")
        product.name = name
        product.sku = sku
        product.unit = unit
        product.unit_price = unit_price
        product.save(update_fields=["name", "sku", "unit", "unit_price"])
        messages.success(request, f"{name} imehifadhiwa.")
    except Product.DoesNotExist:
        messages.error(request, "Product not found.")
    except (ValueError, InvalidOperation) as exc:
        messages.error(request, str(exc))
    return redirect("manager_dashboard")


@login_required(login_url="login")
@require_POST
@transaction.atomic
def create_catalog_product(request):
    if not (request.user.is_superuser or request.user.role == User.Role.MANAGER):
        raise PermissionDenied("Only managers can add products to the catalog.")
    try:
        name = request.POST.get("name", "").strip()
        sku = request.POST.get("sku", "").strip().upper()
        unit = request.POST.get("unit", "").strip()
        unit_price = _decimal(request.POST.get("unit_price"))
        if not name or not sku or not unit:
            raise ValueError("Name, SKU, and unit are required.")
        if Product.objects.filter(models.Q(sku__iexact=sku) | models.Q(name__iexact=name)).exists():
            raise ValueError("A product with that name or SKU already exists.")
        product = Product.objects.create(
            name=name,
            sku=sku,
            unit=unit,
            unit_price=unit_price,
            category=Product.Category.FINISHED_GOOD,
        )
        messages.success(request, f"{product.name} imeongezwa kwenye bidhaa na bei.")
    except (ValueError, InvalidOperation) as exc:
        messages.error(request, str(exc))
    return redirect(f"{reverse('manager_dashboard')}?view=catalog")


@login_required(login_url="login")
def factory_dashboard(request):
    if not (request.user.is_superuser or request.user.role == User.Role.FACTORY):
        raise PermissionDenied("The factory workspace is restricted to factory users.")

    _location(StockLocation.LocationType.FACTORY)
    selected_batch = None
    requested_batch_id = request.GET.get("batch", "").strip()
    if requested_batch_id:
        selected_batch = ProductionBatch.objects.filter(
            pk=requested_batch_id,
            status=ProductionBatch.Status.ACTIVE,
        ).first()
    recently_approved = ProductionBatch.objects.filter(
        created_by=request.user,
        status=ProductionBatch.Status.ACTIVE,
        approved_at__gte=timezone.now() - timedelta(minutes=30),
    ).order_by("-approved_at").first()
    show_batch_welcome = bool(
        recently_approved
        and request.session.get("batch_welcome_seen") != recently_approved.pk
    )
    if show_batch_welcome:
        request.session["batch_welcome_seen"] = recently_approved.pk
        selected_batch = recently_approved
    return _render_workspace(
        request,
        "factory",
        "factory_dashboard",
        show_batch_welcome=show_batch_welcome,
        recently_approved_batch=recently_approved if show_batch_welcome else None,
        production_request_key=uuid.uuid4(),
        honey_bottling_request_key=uuid.uuid4(),
        **factory_dashboard_data(selected_batch),
    )


@login_required(login_url="login")
def factory_standalone_dashboard(request):
    if not (request.user.is_superuser or request.user.role == User.Role.FACTORY):
        raise PermissionDenied("The factory workspace is restricted to factory users.")

    return FileResponse(
        (settings.BASE_DIR / "kiwandani.html").open("rb"),
        content_type="text/html; charset=utf-8",
    )


@login_required(login_url="login")
def mwanza_dashboard(request):
    if not (request.user.is_superuser or request.user.role == User.Role.BRANCH_MWANZA):
        raise PermissionDenied("The Mwanza workspace is restricted to Mwanza branch users.")

    selected_batch = None
    requested_batch_id = request.GET.get("batch", "").strip()
    if requested_batch_id:
        selected_batch = ProductionBatch.objects.filter(
            pk=requested_batch_id,
            inventory_movements__location__location_type=StockLocation.LocationType.BRANCH_MWANZA,
        ).distinct().first()
    return _render_workspace(
        request,
        "branch",
        "mwanza_dashboard",
        branch_name="Mwanza",
        branch_location="Mwanza",
        branch_location_type=StockLocation.LocationType.BRANCH_MWANZA,
        **branch_dashboard_data(StockLocation.LocationType.BRANCH_MWANZA, selected_batch),
    )


@login_required(login_url="login")
def dar_dashboard(request):
    if not (request.user.is_superuser or request.user.role == User.Role.BRANCH_DAR):
        raise PermissionDenied("The Dar workspace is restricted to Dar branch users.")

    selected_batch = None
    requested_batch_id = request.GET.get("batch", "").strip()
    if requested_batch_id:
        selected_batch = ProductionBatch.objects.filter(
            pk=requested_batch_id,
            inventory_movements__location__location_type=StockLocation.LocationType.BRANCH_DAR,
        ).distinct().first()
    return _render_workspace(
        request,
        "branch",
        "dar_dashboard",
        branch_name="Dar es Salaam",
        branch_location="Dar es Salaam",
        branch_location_type=StockLocation.LocationType.BRANCH_DAR,
        **branch_dashboard_data(StockLocation.LocationType.BRANCH_DAR, selected_batch),
    )


def _render_workspace(request, workspace, dashboard_url_name, **extra_context):
    display_name = request.user.get_full_name() or request.user.username
    account_role = {
        "factory": "Factory Manager",
        "branch": "Branch Manager",
    }.get(workspace, "User")
    context = {
        "workspace": workspace,
        "sale_request_key": uuid.uuid4(),
        "dashboard_url": reverse(dashboard_url_name),
        "user_name": display_name,
        "user_initial": display_name[:1].upper(),
        "account_menu_role": account_role,
    }
    context.update(extra_context)
    return render(request, f"dashboard/{workspace}.html", context)


def _require_role(request, role):
    if not (request.user.is_superuser or request.user.role == role):
        raise PermissionDenied("This operation is outside your role.")


def _require_one_of_roles(request, *roles):
    if not (request.user.is_superuser or request.user.role in roles):
        raise PermissionDenied("This operation is outside your role.")


@login_required(login_url="login")
@require_POST
@transaction.atomic
def record_purchase(request):
    _require_one_of_roles(request, User.Role.FACTORY, User.Role.MANAGER)
    try:
        supplier_name = request.POST.get("supplier", "").strip()
        sku = request.POST.get("sku", "").strip()
        item_name = request.POST.get("item_name", "").strip()
        item_unit = request.POST.get("item_unit", "").strip()
        category_value = request.POST.get("category", "").strip()
        batch_id = request.POST.get("batch_id", "").strip()
        quantity = _decimal(request.POST.get("quantity"))
        unit_cost = _decimal(request.POST.get("unit_cost"))
        actual_payment_value = request.POST.get("actual_payment", "").strip()
        if not supplier_name or quantity <= 0:
            raise ValueError("Supplier and quantity are required.")
        batch = None
        if batch_id:
            batch = ProductionBatch.objects.select_for_update().filter(
                pk=batch_id,
                status=ProductionBatch.Status.ACTIVE,
            ).first()
            if batch is None:
                raise ValueError("Purchases can only be associated with an active batch.")
        supplier, _ = Supplier.objects.get_or_create(name=supplier_name)
        if sku:
            product = Product.objects.get(sku=sku, active=True)
            if product.category not in (
                Product.Category.RAW_MATERIAL,
                Product.Category.PACKAGING,
            ):
                raise ValueError("Purchases can only include raw materials or packaging.")
        else:
            category = (
                Product.Category.PACKAGING
                if category_value == "PACKAGING"
                else Product.Category.RAW_MATERIAL
            )
            product = _find_or_create_inventory_item(
                item_name,
                sku,
                item_unit,
                category,
            )
        pricing_unit = _pricing_unit_for_product(product)
        _location(StockLocation.LocationType.FACTORY)
        calculated_total = quantity * unit_cost
        actual_payment = (
            _decimal(actual_payment_value)
            if actual_payment_value
            else calculated_total
        )
        purchase = Purchase.objects.create(
            reference=_reference("PO"),
            supplier=supplier,
            purchase_date=timezone.localdate(),
            total_amount=actual_payment,
            actual_payment=actual_payment,
            calculated_amount=calculated_total,
            batch=batch,
            created_by=request.user,
        )
        PurchaseItem.objects.create(
            purchase=purchase,
            product=product,
            quantity=quantity,
            unit_cost=unit_cost,
            pricing_unit=pricing_unit,
        )
        receive_purchase(purchase)
        messages.success(request, f"Purchase {purchase.reference} received.")
    except (
        ValueError,
        StockLocation.DoesNotExist,
        Product.DoesNotExist,
        ProductionBatch.DoesNotExist,
    ) as exc:
        messages.error(request, str(exc))
    dashboard = (
        "manager_dashboard"
        if request.user.role == User.Role.MANAGER or request.user.is_superuser
        else "factory_dashboard"
    )
    batch_id = request.POST.get("batch_id", "").strip()
    return redirect(f"{reverse(dashboard)}?batch={batch_id}" if batch_id else dashboard)


@login_required(login_url="login")
@require_POST
@transaction.atomic
def receive_saved_purchase(request, purchase_id):
    _require_one_of_roles(request, User.Role.FACTORY, User.Role.MANAGER)
    dashboard = (
        "manager_dashboard"
        if request.user.role == User.Role.MANAGER or request.user.is_superuser
        else "factory_dashboard"
    )
    try:
        purchase = Purchase.objects.select_for_update().get(pk=purchase_id)
        receive_purchase(purchase)
        messages.success(
            request,
            f"Manunuzi {purchase.reference} yamepokelewa na stock imeongezwa stoo.",
        )
    except Purchase.DoesNotExist:
        messages.error(request, "Rekodi ya manunuzi haikupatikana.")
    except (ValueError, StockLocation.DoesNotExist) as exc:
        messages.error(request, str(exc))
    batch_id = request.POST.get("batch_id", "").strip()
    return redirect(f"{reverse(dashboard)}?batch={batch_id}" if batch_id else dashboard)


@login_required(login_url="login")
@require_POST
@transaction.atomic
def start_new_batch(request):
    if request.user.role not in (User.Role.FACTORY, User.Role.MANAGER) and not request.user.is_superuser:
        raise PermissionDenied("Only factory managers and CEOs can start a production batch.")
    factory = _location(StockLocation.LocationType.FACTORY)
    StockLocation.objects.select_for_update().get(pk=factory.pk)
    batch_number = (
        ProductionBatch.objects.aggregate(value=models.Max("batch_number"))["value"] or 0
    ) + 1
    reference = request.POST.get("reference", "").strip() or f"BATCH-{batch_number:03d}"
    if ProductionBatch.objects.filter(reference=reference).exists():
        messages.error(request, "That batch identifier is already in use.")
        return redirect("factory_dashboard" if request.user.role == User.Role.FACTORY else "manager_dashboard")
    is_manager = request.user.is_superuser or request.user.role == User.Role.MANAGER
    batch = ProductionBatch.objects.create(
        reference=reference,
        recipe=None,
        quantity=0,
        batch_number=batch_number,
        production_date=timezone.localdate(),
        created_by=request.user,
        status=(
            ProductionBatch.Status.ACTIVE
            if is_manager
            else ProductionBatch.Status.PENDING_APPROVAL
        ),
        approved_by=request.user if is_manager else None,
        approved_at=timezone.now() if is_manager else None,
        request_note=request.POST.get("request_note", "").strip(),
    )
    if is_manager:
        messages.success(request, f"Karibu kwenye batch mpya {batch.reference}! Imefunguliwa bila historia ya miamala.")
        return redirect(f"{reverse('manager_dashboard')}?batch={batch.pk}&welcome=1")
    messages.info(request, f"Ombi la batch {batch.reference} limetumwa kwa CEO kwa idhini. Subiri kabla ya kurekodi uzalishaji.")
    return redirect("factory_dashboard")


@login_required(login_url="login")
@require_POST
@transaction.atomic
def approve_batch_request(request, batch_id):
    if not (request.user.is_superuser or request.user.role == User.Role.MANAGER):
        raise PermissionDenied("Only the CEO/Manager can approve a new batch.")
    try:
        batch = ProductionBatch.objects.select_for_update().get(
            pk=batch_id,
            status=ProductionBatch.Status.PENDING_APPROVAL,
        )
        batch.status = ProductionBatch.Status.ACTIVE
        batch.approved_by = request.user
        batch.approved_at = timezone.now()
        batch.save(update_fields=["status", "approved_by", "approved_at"])
        messages.success(request, f"Batch {batch.reference} imeidhinishwa na iko tayari kwa uzalishaji.")
        return redirect(f"{reverse('manager_dashboard')}?batch={batch.pk}&welcome=1")
    except ProductionBatch.DoesNotExist:
        messages.error(request, "Ombi la batch halipo au tayari limeshughulikiwa.")
        return redirect("manager_dashboard")


@login_required(login_url="login")
@require_POST
@transaction.atomic
def reject_batch_request(request, batch_id):
    if not (request.user.is_superuser or request.user.role == User.Role.MANAGER):
        raise PermissionDenied("Only the CEO/Manager can reject a new batch.")
    try:
        batch = ProductionBatch.objects.select_for_update().get(
            pk=batch_id,
            status=ProductionBatch.Status.PENDING_APPROVAL,
        )
        batch.status = ProductionBatch.Status.REJECTED
        batch.approved_by = request.user
        batch.approved_at = timezone.now()
        batch.request_note = request.POST.get("reason", "").strip() or batch.request_note
        batch.save(update_fields=["status", "approved_by", "approved_at", "request_note"])
        messages.info(request, f"Ombi la batch {batch.reference} limekataliwa.")
    except ProductionBatch.DoesNotExist:
        messages.error(request, "Ombi la batch halipo au tayari limeshughulikiwa.")
    return redirect("manager_dashboard")


@login_required(login_url="login")
@require_POST
@transaction.atomic
def record_production(request):
    _require_one_of_roles(request, User.Role.FACTORY, User.Role.MANAGER)
    try:
        batch_id = request.POST.get("batch_id", "").strip()
        sku = request.POST.get("sku", "").strip()
        quantity = _decimal(request.POST.get("quantity"))
        if not batch_id or not sku or quantity <= 0:
            raise ValueError("Select an active batch, product, and positive output quantity.")
        batch = ProductionBatch.objects.select_for_update().get(
            pk=batch_id,
            status=ProductionBatch.Status.ACTIVE,
        )
        product = Product.objects.select_for_update().get(sku=sku, active=True)
        if not is_manufactured_product(product):
            raise ValueError("Select Effective Diet or Presha Masala. Record Wild Honey in the separate bottling section.")
        if production_product_family(product) == "honey":
            raise ValueError("Record Wild Honey using the separate honey bottling section.")

        production_date_value = request.POST.get("production_date", "").strip()
        production_date = parse_date(production_date_value) if production_date_value else timezone.localdate()
        if production_date is None:
            raise ValueError("Enter a valid production date.")

        consumptions = []
        for prefix, category, noun in (
            ("material", Product.Category.RAW_MATERIAL, "raw material"),
            ("packaging", Product.Category.PACKAGING, "packaging"),
        ):
            skus = request.POST.getlist(f"{prefix}_sku")
            quantities = request.POST.getlist(f"{prefix}_quantity")
            for index in range(max(map(len, (skus, quantities)), default=0)):
                item_sku = skus[index].strip() if index < len(skus) else ""
                quantity_value = quantities[index].strip() if index < len(quantities) else ""
                if not any((item_sku, quantity_value)):
                    continue
                if not item_sku:
                    raise ValueError(f"Select a registered {noun}.")
                if not quantity_value:
                    raise ValueError(f"Enter a quantity for each {noun}.")
                consumed_quantity = _decimal(quantity_value)
                if consumed_quantity <= 0:
                    raise ValueError(f"{noun.capitalize()} quantity must be positive.")
                item = Product.objects.select_for_update().get(sku=item_sku, active=True)
                if item.category != category:
                    raise ValueError("Select an existing " + noun + " from the correct category.")
                consumptions.append((item, consumed_quantity))

        request_key_value = request.POST.get("production_request_key", "").strip()
        request_key = uuid.UUID(request_key_value) if request_key_value else uuid.uuid4()
        output = complete_production_output(
            batch=batch,
            product=product,
            quantity=quantity,
            consumptions=consumptions,
            created_by=request.user,
            production_date=production_date,
            request_key=request_key,
        )
        messages.success(request, f"{product.name} production saved under {batch.reference}.")
    except (ValueError, StockLocation.DoesNotExist, Product.DoesNotExist, ProductionBatch.DoesNotExist) as exc:
        messages.error(request, str(exc))
    if request.user.role == User.Role.MANAGER or request.user.is_superuser:
        return redirect(f"{reverse('manager_dashboard')}?batch={request.POST.get('batch_id', '')}")
    return redirect(f"{reverse('factory_dashboard')}?batch={request.POST.get('batch_id', '')}")


@login_required(login_url="login")
@require_POST
@transaction.atomic
def record_honey_bottling(request):
    _require_one_of_roles(request, User.Role.FACTORY, User.Role.MANAGER)
    batch_id = request.POST.get("batch_id", "").strip()
    try:
        batch = ProductionBatch.objects.select_for_update().get(
            pk=batch_id,
            status=ProductionBatch.Status.ACTIVE,
        )
        raw_honey = Product.objects.select_for_update().get(
            sku="RAW-RAW-HONEY",
            category=Product.Category.RAW_MATERIAL,
            active=True,
        )
        jar_packaging = Product.objects.select_for_update().get(
            sku="PKG-HONEY-CANS",
            category=Product.Category.PACKAGING,
            active=True,
        )
        bottled_honey = Product.objects.select_for_update().get(
            sku="HONEY-SINGLE",
            category=Product.Category.FINISHED_GOOD,
            active=True,
        )
        honey_quantity = _decimal(request.POST.get("honey_quantity"))
        jars_filled = _decimal(request.POST.get("jars_filled"))
        if honey_quantity <= 0 or jars_filled <= 0:
            raise ValueError("Weka idadi ya madumu yaliyotumika na vikopo vilivyojazwa.")
        if jars_filled != jars_filled.to_integral_value():
            raise ValueError("Idadi ya vikopo lazima iwe namba kamili.")

        production_date_value = request.POST.get("production_date", "").strip()
        production_date = parse_date(production_date_value) if production_date_value else timezone.localdate()
        if production_date is None:
            raise ValueError("Weka tarehe sahihi ya kufungasha asali.")

        request_key_value = request.POST.get("production_request_key", "").strip()
        try:
            request_key = uuid.UUID(request_key_value) if request_key_value else uuid.uuid4()
        except ValueError as exc:
            raise ValueError("Invalid production submission key.") from exc

        output = complete_production_output(
            batch=batch,
            product=bottled_honey,
            quantity=jars_filled,
            consumptions=(
                (raw_honey, honey_quantity),
                (jar_packaging, jars_filled),
            ),
            created_by=request.user,
            production_date=production_date,
            request_key=request_key,
        )
        messages.success(
            request,
            f"Asali {output.quantity} {bottled_honey.unit} imefungashwa kutoka {honey_quantity} {raw_honey.unit} "
            f"kwenye batch {batch.reference}.",
        )
    except (
        ValueError,
        StockLocation.DoesNotExist,
        Product.DoesNotExist,
        ProductionBatch.DoesNotExist,
    ) as exc:
        messages.error(request, str(exc))

    dashboard = "manager_dashboard" if request.user.role == User.Role.MANAGER or request.user.is_superuser else "factory_dashboard"
    return redirect(f"{reverse(dashboard)}?batch={batch_id}" if batch_id else dashboard)


@login_required(login_url="login")
@require_POST
@transaction.atomic
def record_dispatch(request):
    _require_one_of_roles(request, User.Role.FACTORY, User.Role.MANAGER)
    try:
        with transaction.atomic():
            sku = request.POST.get("sku", "").strip()
            quantity = _decimal(request.POST.get("quantity"))
            destination = request.POST.get("destination")
            batch_id = request.POST.get("batch_id", "").strip()
            if not sku or quantity <= 0 or not batch_id:
                raise ValueError("SKU, batch, and positive quantity are required.")
            if destination not in ("DAR", "MWANZA"):
                raise ValueError("Select a valid branch destination.")
            product = Product.objects.get(
                sku=sku,
                active=True,
                category=Product.Category.FINISHED_GOOD,
            )
            batch = ProductionBatch.objects.select_for_update().get(
                pk=batch_id,
                status__in=(ProductionBatch.Status.ACTIVE, ProductionBatch.Status.COMPLETED),
            )
            if not (
                ProductionOutput.objects.filter(batch=batch, product=product).exists()
                or batch.recipe_id and batch.recipe.product_id == product.pk
            ):
                raise ValueError("The selected product does not belong to this batch.")
            _location(StockLocation.LocationType.FACTORY)
            location_type = (
                StockLocation.LocationType.BRANCH_DAR
                if destination == "DAR"
                else StockLocation.LocationType.BRANCH_MWANZA
            )
            destination_location = _location(location_type)
            transfer = Transfer.objects.create(
                reference=_reference("TR"),
                destination=destination_location,
                dispatched_by=request.user,
            )
            TransferItem.objects.create(
                transfer=transfer,
                product=product,
                batch=batch,
                quantity_sent=quantity,
            )
            from apps.distribution.services import dispatch_transfer
            dispatch_transfer(transfer)
        messages.success(request, f"Transfer {transfer.reference} dispatched.")
    except (
        ValueError,
        StockLocation.DoesNotExist,
        Product.DoesNotExist,
        ProductionBatch.DoesNotExist,
    ) as exc:
        messages.error(request, str(exc))
    dashboard = (
        "manager_dashboard"
        if request.user.role == User.Role.MANAGER or request.user.is_superuser
        else "factory_dashboard"
    )
    batch_id = request.POST.get("batch_id", "").strip()
    return redirect(f"{reverse(dashboard)}?batch={batch_id}" if batch_id else dashboard)


def _branch_role(request):
    if request.user.role not in (User.Role.BRANCH_MWANZA, User.Role.BRANCH_DAR):
        raise PermissionDenied("This operation is restricted to branch users.")


def _branch_location(request):
    if request.user.is_superuser:
        location_type = request.POST.get("location_type") or StockLocation.LocationType.BRANCH_DAR
        if location_type not in (
            StockLocation.LocationType.BRANCH_MWANZA,
            StockLocation.LocationType.BRANCH_DAR,
        ):
            raise ValueError("Select a valid branch.")
        return _location(location_type)
    if request.user.role == User.Role.BRANCH_MWANZA:
        return _location(StockLocation.LocationType.BRANCH_MWANZA)
    return _location(StockLocation.LocationType.BRANCH_DAR)


@login_required(login_url="login")
@require_POST
def record_sale(request):
    _branch_role(request)
    try:
        with transaction.atomic():
            sku = request.POST.get("sku", "").strip()
            customer_id = request.POST.get("customer_id", "").strip()
            batch_id = request.POST.get("batch_id", "").strip()
            quantity = _decimal(request.POST.get("quantity"))
            request_key_text = request.POST.get("request_key", "").strip()
            if not sku or not customer_id or not batch_id or quantity <= 0:
                raise ValueError("Customer, SKU, batch, and quantity are required.")
            location = _branch_location(request)
            product = Product.objects.get(
                sku=sku,
                active=True,
                category=Product.Category.FINISHED_GOOD,
            )
            customer = Customer.objects.get(
                pk=customer_id,
                location=location,
                active=True,
            )
            batch = None
            batch = ProductionBatch.objects.select_for_update().get(
                pk=batch_id,
                status__in=(ProductionBatch.Status.ACTIVE, ProductionBatch.Status.COMPLETED),
            )
            stock_products = (
                full_package_components()
                if is_full_package_product(product)
                else (product,)
            )
            for stock_product in stock_products:
                if not (
                    ProductionOutput.objects.filter(batch=batch, product=stock_product).exists()
                    or batch.recipe_id and batch.recipe.product_id == stock_product.pk
                ):
                    raise ValueError(
                        f"{stock_product.name} haipo kwenye batch iliyochaguliwa."
                    )
                stock_entries = InventoryLedger.objects.filter(
                    location=location,
                    product=stock_product,
                    production_batch=batch,
                )
                available = stock_entries.aggregate(
                    total=models.Sum("quantity")
                )["total"] or Decimal("0")
                if quantity > available:
                    raise ValueError(
                        f"Stock haitoshi ya {stock_product.name} kwenye batch hii: "
                        f"{available} {stock_product.unit}."
                    )
            unit_price = product.unit_price
            try:
                request_key = uuid.UUID(request_key_text) if request_key_text else uuid.uuid4()
            except (ValueError, AttributeError):
                raise ValueError("Invalid sale request key.")
            existing_sale = Sale.objects.select_for_update().filter(request_key=request_key).first()
            if existing_sale:
                return redirect(f"{reverse('mwanza_dashboard' if request.user.role == User.Role.BRANCH_MWANZA else 'dar_dashboard')}?batch={batch_id}")
            sale = Sale.objects.create(
                reference=_reference("SALE"),
                location=location,
                customer=customer,
                sold_by=request.user,
                total_amount=quantity * unit_price,
                request_key=request_key,
            )
            SaleItem.objects.create(
                sale=sale,
                product=product,
                batch=batch,
                quantity=quantity,
                unit_price=unit_price,
            )
            confirm_sale(sale)
            record_audit_event(
                actor=request.user,
                category=AuditEvent.Category.SALES,
                action="sale.recorded",
                object_type="Sale",
                object_id=sale.pk,
                new_values={
                    "reference": sale.reference,
                    "location": sale.location.location_type,
                    "customer": customer.pk,
                    "product": product.pk,
                    "quantity": str(quantity),
                    "total_amount": str(sale.total_amount),
                },
                request=request,
            )
        messages.success(request, f"Sale {sale.reference} recorded.")
    except (
        ValueError,
        StockLocation.DoesNotExist,
        Product.DoesNotExist,
        Customer.DoesNotExist,
        ProductionBatch.DoesNotExist,
    ) as exc:
        messages.error(request, str(exc))
    dashboard = "mwanza_dashboard" if request.user.role == User.Role.BRANCH_MWANZA else "dar_dashboard"
    batch_id = request.POST.get("batch_id", "").strip()
    return redirect(f"{reverse(dashboard)}?batch={batch_id}" if batch_id else dashboard)


@login_required(login_url="login")
@require_POST
@transaction.atomic
def record_expense(request):
    _branch_role(request)
    try:
        amount = _decimal(request.POST.get("amount"))
        category = request.POST.get("category", "").strip()
        batch_id = request.POST.get("batch_id", "").strip()
        if amount <= 0 or not category:
            raise ValueError("Category and amount are required.")
        location = _branch_location(request)
        batch = None
        if batch_id:
            batch = ProductionBatch.objects.select_for_update().get(
                pk=batch_id,
                status__in=(
                    ProductionBatch.Status.ACTIVE,
                    ProductionBatch.Status.COMPLETED,
                    ProductionBatch.Status.CLOSED,
                ),
            )
        BranchExpense.objects.create(
            location=location.location_type,
            category=category,
            amount=amount,
            description=request.POST.get("description", "").strip(),
            expense_date=timezone.localdate(),
            recorded_by=request.user,
            batch=batch,
        )
        messages.success(request, "Expense recorded.")
    except (ValueError, ProductionBatch.DoesNotExist) as exc:
        messages.error(request, str(exc))
    dashboard = "mwanza_dashboard" if request.user.role == User.Role.BRANCH_MWANZA else "dar_dashboard"
    batch_id = request.POST.get("batch_id", "").strip()
    return redirect(f"{reverse(dashboard)}?batch={batch_id}" if batch_id else dashboard)


@login_required(login_url="login")
@require_POST
@transaction.atomic
def record_customer(request):
    _branch_role(request)
    name = request.POST.get("name", "").strip()
    phone = request.POST.get("phone", "").strip()
    if not name:
        messages.error(request, "Customer name is required.")
    else:
        try:
            location = _branch_location(request)
            location = StockLocation.objects.select_for_update().get(pk=location.pk)
            matches = _branch_customers_matching_phone(location, phone) if phone else []
            if len(matches) > 1:
                named_matches = [customer for customer in matches if customer.name.casefold() == name.casefold()]
                matches = named_matches or matches
            if len(matches) > 1:
                raise ValueError("Namba hii inatumika kwa wateja zaidi ya mmoja. Chagua mteja aliyepo kwenye check-in.")
            customer = matches[0] if matches else None
            if customer is None and not phone:
                named_matches = list(Customer.objects.filter(location=location, name__iexact=name)[:2])
                if len(named_matches) > 1:
                    raise ValueError("Kuna wateja wenye jina hili. Tumia namba ya simu kutambua mteja sahihi.")
                customer = named_matches[0] if named_matches else None
            is_returning = customer is not None
            if customer is None:
                customer = Customer.objects.create(
                    name=name,
                    location=location,
                    phone=phone,
                    diagnosis=request.POST.get("diagnosis", "").strip(),
                    short_description=request.POST.get("short_description", "").strip(),
                    address=request.POST.get("address", "").strip(),
                )
            linked_visits = _link_prior_visitor_records(location, customer, phone)
            CustomerCall.objects.filter(
                customer__isnull=True,
                location=location,
                caller_name__iexact=name,
                caller_phone=phone,
            ).exclude(caller_phone="").update(customer=customer)
            CustomerVisit.objects.create(
                customer=customer,
                location=location,
                visit_type=(
                    CustomerVisit.VisitType.RETURNING_CUSTOMER
                    if is_returning
                    else CustomerVisit.VisitType.NEW_CUSTOMER
                ),
                visitor_name=name,
                visitor_phone=phone,
                recorded_by=request.user,
            )
            if is_returning:
                message = f"{customer.name} returned again today. Visit recorded."
            else:
                message = "Customer saved. First branch visit recorded."
            if linked_visits:
                message += f" Linked {linked_visits} earlier visitor record(s) to this customer."
            messages.success(request, message)
        except ValueError as exc:
            messages.error(request, str(exc))
    return _branch_dashboard_redirect(request)


@login_required(login_url="login")
@require_POST
@transaction.atomic
def record_branch_visit(request):
    _branch_role(request)
    try:
        location = _branch_location(request)
        location = StockLocation.objects.select_for_update().get(pk=location.pk)
        visit_mode = request.POST.get("visit_mode", "").strip()
        phone = request.POST.get("visitor_phone", "").strip()
        if visit_mode == "customer":
            customer_id = request.POST.get("customer_id", "").strip()
            if not customer_id:
                raise ValueError("Chagua mteja aliyefika.")
            customer = Customer.objects.get(pk=customer_id, location=location, active=True)
            linked_visits = _link_prior_visitor_records(location, customer, customer.phone)
            CustomerVisit.objects.create(
                customer=customer,
                location=location,
                visit_type=CustomerVisit.VisitType.RETURNING_CUSTOMER,
                visitor_name=customer.name,
                visitor_phone=customer.phone,
                notes=request.POST.get("notes", "").strip(),
                recorded_by=request.user,
            )
            message = f"{customer.name} returned again today. Visit recorded."
            if linked_visits:
                message += f" Linked {linked_visits} earlier visitor record(s) to this customer."
            messages.success(request, message)
        elif visit_mode == "visitor":
            name = request.POST.get("visitor_name", "").strip()
            visit_type = request.POST.get("visit_type", "").strip()
            if not name:
                raise ValueError("Andika jina la mgeni.")
            if not phone:
                raise ValueError("Weka namba ya simu ya mgeni ili mfumo uweze kumtambua akirudi.")
            if visit_type not in _VISITOR_VISIT_TYPES:
                raise ValueError("Chagua sababu sahihi ya ziara ya mgeni.")
            matches = _branch_customers_matching_phone(location, phone) if phone else []
            if len(matches) > 1:
                raise ValueError("Namba hii inahusishwa na wateja zaidi ya mmoja. Chagua mteja kwenye check-in.")
            if matches:
                customer = matches[0]
                _link_prior_visitor_records(location, customer, phone)
                CustomerVisit.objects.create(
                    customer=customer,
                    location=location,
                    visit_type=CustomerVisit.VisitType.RETURNING_CUSTOMER,
                    visitor_name=customer.name,
                    visitor_phone=phone,
                    notes=request.POST.get("notes", "").strip(),
                    recorded_by=request.user,
                )
                messages.success(request, f"{customer.name} already exists as a customer. Returning visit recorded.")
            else:
                normalized_phone = _normalized_phone(phone)
                previous_visits = 0
                if normalized_phone:
                    previous_visits = sum(
                        1
                        for saved_phone in CustomerVisit.objects.filter(
                            location=location,
                            visit_type__in=_VISITOR_VISIT_TYPES,
                        ).exclude(visitor_phone="").values_list("visitor_phone", flat=True)
                        if _normalized_phone(saved_phone) == normalized_phone
                    )
                CustomerVisit.objects.create(
                    customer=None,
                    location=location,
                    visit_type=visit_type,
                    visitor_name=name,
                    visitor_phone=phone,
                    notes=request.POST.get("notes", "").strip(),
                    recorded_by=request.user,
                )
                if previous_visits:
                    messages.success(request, f"Visitor returned. This person has {previous_visits} earlier visitor record(s); today's visit was saved.")
                else:
                    messages.success(request, "Visitor arrival recorded.")
        else:
            raise ValueError("Chagua kama anayefika ni mteja aliyesajiliwa au mgeni.")
    except (ValueError, Customer.DoesNotExist) as exc:
        messages.error(request, str(exc))
    return _branch_dashboard_redirect(request, view="visitors")


@login_required(login_url="login")
@require_POST
@transaction.atomic
def record_branch_delivery(request):
    _branch_role(request)
    try:
        location = _branch_location(request)
        recipient_name = request.POST.get("recipient_name", "").strip()
        destination = request.POST.get("destination", "").strip()
        phone = request.POST.get("recipient_phone", "").strip()
        if not recipient_name or not destination:
            raise ValueError("Jaza jina la mpokeaji na anwani ya delivery.")
        try:
            parcel_count = int(request.POST.get("parcel_count", "1"))
        except ValueError as exc:
            raise ValueError("Idadi ya parcels lazima iwe namba nzima.") from exc
        if parcel_count < 1:
            raise ValueError("Delivery lazima iwe na angalau parcel moja.")
        delivery_date_value = request.POST.get("delivery_date", "").strip()
        delivery_date = parse_date(delivery_date_value) if delivery_date_value else timezone.localdate()
        if delivery_date is None:
            raise ValueError("Weka tarehe sahihi ya delivery.")
        customer = None
        customer_id = request.POST.get("customer_id", "").strip()
        if customer_id:
            customer = Customer.objects.get(pk=customer_id, location=location, active=True)
        BranchDelivery.objects.create(
            customer=customer,
            location=location,
            recipient_name=recipient_name,
            recipient_phone=phone,
            destination=destination,
            parcel_count=parcel_count,
            delivery_date=delivery_date,
            notes=request.POST.get("notes", "").strip(),
            recorded_by=request.user,
        )
        messages.success(request, "Delivery/parcels record saved.")
    except (ValueError, Customer.DoesNotExist) as exc:
        messages.error(request, str(exc))
    return _branch_dashboard_redirect(request, view="deliveries")


@login_required(login_url="login")
@require_POST
@transaction.atomic
def update_branch_delivery_status(request, delivery_id):
    _branch_role(request)
    try:
        location = _branch_location(request)
        delivery = BranchDelivery.objects.get(pk=delivery_id, location=location)
        status = request.POST.get("status", "").strip()
        if status not in BranchDelivery.Status.values:
            raise ValueError("Chagua hali sahihi ya delivery.")
        delivery.status = status
        delivery.save(update_fields=("status", "updated_at"))
        messages.success(request, f"Delivery status updated to {delivery.get_status_display()}.")
    except (ValueError, BranchDelivery.DoesNotExist) as exc:
        messages.error(request, str(exc))
    return _branch_dashboard_redirect(request, view="deliveries")


@login_required(login_url="login")
@require_POST
def record_call(request):
    _branch_role(request)
    try:
        location = _branch_location(request)
        contact_mode = request.POST.get("contact_mode", "").strip()
        customer_id = request.POST.get("customer_id", "").strip()
        caller_name = request.POST.get("caller_name", "").strip()
        caller_phone = request.POST.get("caller_phone", "").strip()
        direction = request.POST.get("direction", "").strip()
        call_type = request.POST.get("call_type", "").strip()
        outcome = request.POST.get("outcome", "").strip()
        if not contact_mode:
            contact_mode = "customer" if customer_id else "caller"
        if contact_mode not in ("customer", "caller"):
            raise ValueError("Chagua kama mwasiliani ni mteja aliyesajiliwa au mtu ambaye hajasajiliwa.")
        if direction not in (CustomerCall.Direction.INBOUND, CustomerCall.Direction.OUTBOUND):
            raise ValueError("Chagua kama tumepigiwa au tumempigia mteja.")
        if not call_type or not outcome:
            raise ValueError("Chagua aina ya mawasiliano na ujaze matokeo.")
        if call_type not in CustomerCall.CallType.values:
            raise ValueError("Aina ya mawasiliano uliyochagua si sahihi.")
        customer = None
        if contact_mode == "customer":
            if not customer_id:
                raise ValueError("Chagua mteja aliyesajiliwa.")
            customer = Customer.objects.get(pk=customer_id, location=location, active=True)
        else:
            if not caller_name or not caller_phone:
                raise ValueError("Andika jina na namba ya simu ya mwasiliani.")
            if len(caller_name) > 150 or len(caller_phone) > 30:
                raise ValueError("Jina au namba ya simu imezidi urefu unaoruhusiwa.")
        follow_up_value = request.POST.get("follow_up", "").strip()
        follow_up = parse_date(follow_up_value) if follow_up_value else None
        if follow_up_value and follow_up is None:
            raise ValueError("Weka tarehe sahihi ya kuwasiliana tena.")
        CustomerCall.objects.create(
            customer=customer,
            location=location,
            called_by=request.user,
            direction=direction,
            call_type=call_type,
            caller_name=caller_name if contact_mode == "caller" else "",
            caller_phone=caller_phone if contact_mode == "caller" else "",
            outcome=outcome,
            notes=request.POST.get("notes", "").strip(),
            follow_up_date=follow_up,
        )
        messages.success(request, "Mawasiliano na mteja yamehifadhiwa.")
    except (ValueError, InvalidOperation, Customer.DoesNotExist) as exc:
        messages.error(request, str(exc))
    dashboard = "mwanza_dashboard" if request.user.role == User.Role.BRANCH_MWANZA else "dar_dashboard"
    return redirect(dashboard)


@login_required(login_url="login")
@require_POST
@transaction.atomic
def record_loss(request):
    _require_one_of_roles(
        request,
        User.Role.FACTORY,
        User.Role.MANAGER,
        User.Role.BRANCH_MWANZA,
        User.Role.BRANCH_DAR,
    )
    try:
        sku = request.POST.get("sku", "").strip()
        quantity = _decimal(request.POST.get("quantity"))
        notes = request.POST.get("notes", "").strip()
        batch_id = request.POST.get("batch_id", "").strip()
        if not sku or quantity <= 0:
            raise ValueError("SKU and a positive quantity are required.")
        product = Product.objects.get(sku=sku)
        if product.category == Product.Category.FINISHED_GOOD and not batch_id:
            raise ValueError("Select the production batch for finished-product losses.")
        if request.user.role == User.Role.BRANCH_MWANZA:
            location = _location(StockLocation.LocationType.BRANCH_MWANZA)
        elif request.user.role == User.Role.BRANCH_DAR:
            location = _location(StockLocation.LocationType.BRANCH_DAR)
        else:
            location = _location(StockLocation.LocationType.FACTORY)
        batch = None
        if batch_id:
            batch = ProductionBatch.objects.select_for_update().get(
                pk=batch_id,
                status__in=(
                    ProductionBatch.Status.ACTIVE,
                    ProductionBatch.Status.COMPLETED,
                    ProductionBatch.Status.CLOSED,
                ),
            )
        if product.category == Product.Category.FINISHED_GOOD:
            if not batch or not (
                ProductionOutput.objects.filter(batch=batch, product=product).exists()
                or batch.recipe_id and batch.recipe.product_id == product.pk
            ):
                raise ValueError("The selected product does not belong to this production batch.")
        post_movement(
            product=product,
            location=location,
            movement="LOSS",
            quantity=-quantity,
            reference=_reference("LOSS"),
            notes=notes,
            production_batch=batch,
        )
        messages.success(request, "Stock loss recorded.")
    except (
        ValueError,
        StockLocation.DoesNotExist,
        Product.DoesNotExist,
        ProductionBatch.DoesNotExist,
    ) as exc:
        messages.error(request, str(exc))
    dashboard = (
        "mwanza_dashboard"
        if request.user.role == User.Role.BRANCH_MWANZA
        else "dar_dashboard"
        if request.user.role == User.Role.BRANCH_DAR
        else "manager_dashboard"
        if request.user.role == User.Role.MANAGER
        else "factory_dashboard"
    )
    return redirect(f"{reverse(dashboard)}?batch={batch_id}" if batch_id else dashboard)


@login_required(login_url="login")
@require_POST
@transaction.atomic
def submit_daily_report(request):
    _branch_role(request)
    try:
        location = _branch_location(request)
        batch_id = request.POST.get("batch_id", "").strip()
        if not batch_id:
            raise ValueError("Select the production batch for this report.")
        batch = ProductionBatch.objects.select_for_update().filter(
            pk=batch_id,
            inventory_movements__location=location,
            status__in=(
                ProductionBatch.Status.ACTIVE,
                ProductionBatch.Status.COMPLETED,
                ProductionBatch.Status.CLOSED,
            ),
        ).first()
        if batch is None:
            raise ValueError("Select a batch with stock at this branch.")
        report_date = timezone.localdate()
        decimal_fields = ("units_sold", "closing_balance", "loss_quantity")
        report_values = {}
        for field in decimal_fields:
            report_values[field] = _decimal(request.POST.get(field))
        integer_fields = ("instruction_calls", "compliance_calls", "followup_calls")
        for field in integer_fields:
            value = int(request.POST.get(field, "0") or "0")
            if value < 0:
                raise ValueError("Report counts cannot be negative.")
            report_values[field] = value
        visit_summary = CustomerVisit.objects.filter(
            location=location,
            visited_at__date=report_date,
        ).aggregate(
            new_customers=models.Count(
                "pk",
                filter=models.Q(visit_type=CustomerVisit.VisitType.NEW_CUSTOMER),
            ),
            returning_customers=models.Count(
                "pk",
                filter=models.Q(visit_type=CustomerVisit.VisitType.RETURNING_CUSTOMER),
            ),
            visitors=models.Count(
                "pk",
                filter=models.Q(visit_type__in=_VISITOR_VISIT_TYPES),
            ),
        )
        delivery_summary = BranchDelivery.objects.filter(
            location=location,
            delivery_date=report_date,
        ).aggregate(deliveries=models.Count("pk"), parcels=models.Sum("parcel_count"))
        report_values.update(
            new_customers=visit_summary["new_customers"],
            returning_customers=visit_summary["returning_customers"],
            total_customers=visit_summary["new_customers"] + visit_summary["returning_customers"],
            visitors=visit_summary["visitors"],
            deliveries=delivery_summary["deliveries"],
            parcels=delivery_summary["parcels"] or 0,
        )
        existing_report = BranchDailyReport.objects.filter(
            location=location.location_type,
            report_date=report_date,
            batch=batch,
        ).first()
        if existing_report and existing_report.status in (
            BranchDailyReport.Status.SUBMITTED,
            BranchDailyReport.Status.APPROVED,
        ):
            raise ValueError("This daily report has already been submitted and is read-only.")
        report, _ = BranchDailyReport.objects.update_or_create(
            location=location.location_type,
            report_date=report_date,
            batch=batch,
            defaults={
                **report_values,
                "customer_addresses": request.POST.get("customer_addresses", "").strip(),
                "status": BranchDailyReport.Status.SUBMITTED,
                "submitted_by": request.user,
            },
        )
        messages.success(request, f"Daily report {report.report_date} submitted.")
    except (ValueError, InvalidOperation) as exc:
        messages.error(request, str(exc))
    dashboard = "mwanza_dashboard" if request.user.role == User.Role.BRANCH_MWANZA else "dar_dashboard"
    batch_id = request.POST.get("batch_id", "").strip()
    return redirect(f"{reverse(dashboard)}?batch={batch_id}" if batch_id else dashboard)


@login_required(login_url="login")
@require_POST
@transaction.atomic
def approve_daily_report(request, report_id):
    if not (request.user.is_superuser or request.user.role == User.Role.MANAGER):
        raise PermissionDenied("Only managers can approve daily reports.")
    try:
        report = BranchDailyReport.objects.select_for_update().get(pk=report_id)
        report.status = BranchDailyReport.Status.APPROVED
        report.approved_by = request.user
        report.approved_at = timezone.now()
        report.save(update_fields=["status", "approved_by", "approved_at"])
        messages.success(request, f"Report for {report.report_date} approved.")
    except BranchDailyReport.DoesNotExist:
        messages.error(request, "Report not found.")
    return redirect("manager_dashboard")


@login_required(login_url="login")
@require_POST
@transaction.atomic
def cancel_production(request, batch_id):
    _require_one_of_roles(request, User.Role.FACTORY, User.Role.MANAGER)
    try:
        batch = ProductionBatch.objects.select_for_update().get(pk=batch_id)
        if batch.status != ProductionBatch.Status.PLANNED:
            raise ValueError("Only planned batches can be cancelled.")
        batch.status = ProductionBatch.Status.CANCELLED
        batch.save(update_fields=["status"])
        messages.success(request, f"Batch {batch.reference} cancelled.")
    except (ProductionBatch.DoesNotExist, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("manager_dashboard" if request.user.role == User.Role.MANAGER else "factory_dashboard")


@login_required(login_url="login")
@require_POST
@transaction.atomic
def receive_transfer(request, transfer_id):
    _require_role(request, User.Role.BRANCH_MWANZA if request.user.role == User.Role.BRANCH_MWANZA else User.Role.BRANCH_DAR)
    try:
        transfer = Transfer.objects.select_for_update().select_related("destination").get(pk=transfer_id)
        if not request.user.is_superuser:
            allowed = (
                request.user.role == User.Role.BRANCH_MWANZA and transfer.destination.location_type == StockLocation.LocationType.BRANCH_MWANZA
                or request.user.role == User.Role.BRANCH_DAR and transfer.destination.location_type == StockLocation.LocationType.BRANCH_DAR
            )
            if not allowed:
                raise PermissionDenied("Transfer belongs to another branch.")
        quantities = {str(item.pk): request.POST.get(f"received_{item.pk}", item.quantity_sent) for item in transfer.items.all()}
        receive_transfer_service(transfer, quantities)
        messages.success(request, f"Transfer {transfer.reference} received.")
    except (Transfer.DoesNotExist, ValueError) as exc:
        messages.error(request, str(exc))
    dashboard = "mwanza_dashboard" if request.user.role == User.Role.BRANCH_MWANZA else "dar_dashboard"
    return redirect(dashboard)
