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
from datetime import date

from apps.accounts.models import User
from apps.inventory.models import InventoryLedger, Product, StockLocation
from apps.inventory.services import post_movement
from apps.procurement.models import Supplier, Purchase, PurchaseItem
from apps.procurement.services import receive_purchase
from apps.production.models import Recipe, RecipeItem, ProductionBatch
from apps.production.services import complete_batch
from apps.distribution.models import Transfer, TransferItem
from apps.distribution.services import receive_transfer as receive_transfer_service
from apps.sales.models import Sale, SaleItem
from apps.sales.services import confirm_sale
from apps.customers.models import Customer, CustomerCall, BranchExpense, BranchDailyReport
from .services import factory_dashboard_data, branch_dashboard_data, manager_dashboard_data
from apps.reports.exports import csv_response


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


def _next_batch_number(product):
    numbers = ProductionBatch.objects.filter(
        recipe__product=product,
        batch_number__isnull=False,
    ).values_list("batch_number", flat=True)
    if not numbers:
        numbers = []
    return (max(numbers, default=0) or 0) + 1


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
    manager_name = request.user.get_full_name() or request.user.username
    return render(
        request,
        "dashboard/manager.html",
        {
            "manager_name": manager_name,
            "manager_initial": manager_name[:1].upper(),
            "dashboard_data_is_sample": False,
            **manager_dashboard_data(),
        },
    )


@login_required(login_url="login")
def export_manager_report(request):
    if not (request.user.is_superuser or request.user.role == User.Role.MANAGER):
        raise PermissionDenied("Only managers can export reports.")
    report_type = request.GET.get("type", "sales")
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
                call.customer.name,
                call.outcome,
                call.notes,
                call.follow_up_date or "",
                call.called_by.username,
            ]
            for call in CustomerCall.objects.select_related("customer", "called_by").order_by("-called_at")
        ]
        return csv_response(
            "customer-calls.csv",
            ["Date", "Customer", "Outcome", "Notes", "Follow-up", "Recorded by"],
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
def factory_dashboard(request):
    if not (request.user.is_superuser or request.user.role == User.Role.FACTORY):
        raise PermissionDenied("The factory workspace is restricted to factory users.")

    _location(StockLocation.LocationType.FACTORY)
    return _render_workspace(
        request,
        "factory",
        "factory_dashboard",
        **factory_dashboard_data(),
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

    return _render_workspace(
        request,
        "branch",
        "mwanza_dashboard",
        branch_name="Mwanza",
        branch_location="Mwanza",
        branch_location_type=StockLocation.LocationType.BRANCH_MWANZA,
        **branch_dashboard_data(StockLocation.LocationType.BRANCH_MWANZA),
    )


@login_required(login_url="login")
def dar_dashboard(request):
    if not (request.user.is_superuser or request.user.role == User.Role.BRANCH_DAR):
        raise PermissionDenied("The Dar workspace is restricted to Dar branch users.")

    return _render_workspace(
        request,
        "branch",
        "dar_dashboard",
        branch_name="Dar es Salaam",
        branch_location="Dar es Salaam",
        branch_location_type=StockLocation.LocationType.BRANCH_DAR,
        **branch_dashboard_data(StockLocation.LocationType.BRANCH_DAR),
    )


def _render_workspace(request, workspace, dashboard_url_name, **extra_context):
    display_name = request.user.get_full_name() or request.user.username
    context = {
        "workspace": workspace,
        "dashboard_url": reverse(dashboard_url_name),
        "user_name": display_name,
        "user_initial": display_name[:1].upper(),
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
        quantity = _decimal(request.POST.get("quantity"))
        unit_cost = _decimal(request.POST.get("unit_cost"))
        actual_payment_value = request.POST.get("actual_payment", "").strip()
        if not supplier_name or quantity <= 0:
            raise ValueError("Supplier and quantity are required.")
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
    except (ValueError, StockLocation.DoesNotExist, Product.DoesNotExist) as exc:
        messages.error(request, str(exc))
    return redirect("manager_dashboard" if request.user.role == User.Role.MANAGER or request.user.is_superuser else "factory_dashboard")


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
    return redirect(dashboard)


@login_required(login_url="login")
@require_POST
@transaction.atomic
def record_production(request):
    _require_one_of_roles(request, User.Role.FACTORY, User.Role.MANAGER)
    try:
        with transaction.atomic():
            sku = request.POST.get("sku", "").strip()
            quantity = _decimal(request.POST.get("quantity"))
            batch_name = request.POST.get("batch_name", "").strip()
            if not sku or quantity <= 0:
                raise ValueError("Product SKU and quantity are required.")
            product = Product.objects.get(sku=sku)
            if product.category != Product.Category.FINISHED_GOOD:
                raise ValueError("Only finished goods can be recorded as production output.")
            _location(StockLocation.LocationType.FACTORY)
            recipe, _ = Recipe.objects.get_or_create(product=product, defaults={"yield_quantity": quantity})
            recipe.yield_quantity = quantity
            recipe.save(update_fields=["yield_quantity"])
            RecipeItem.objects.filter(recipe=recipe).delete()
            material_skus = request.POST.getlist("material_sku")
            material_names = request.POST.getlist("material_name")
            material_units = request.POST.getlist("material_unit")
            material_quantities = request.POST.getlist("material_quantity")
            for index, used_quantity_value in enumerate(material_quantities):
                if not used_quantity_value:
                    continue
                used_quantity = _decimal(used_quantity_value)
                if used_quantity <= 0:
                    raise ValueError("Material quantity must be positive.")
                material_sku = material_skus[index].strip() if index < len(material_skus) else ""
                material_name = material_names[index].strip() if index < len(material_names) else ""
                material_unit = material_units[index].strip() if index < len(material_units) else ""
                if material_sku:
                    material = Product.objects.select_for_update().get(
                        sku=material_sku,
                        active=True,
                    )
                    if material.category not in (
                        Product.Category.RAW_MATERIAL,
                        Product.Category.PACKAGING,
                    ):
                        raise ValueError("Only raw materials or packaging can be consumed.")
                else:
                    material = _find_or_create_inventory_item(
                        material_name,
                        "",
                        material_unit,
                        Product.Category.RAW_MATERIAL,
                    )
                RecipeItem.objects.create(recipe=recipe, material=material, quantity=used_quantity)
            packaging_skus = request.POST.getlist("packaging_sku")
            packaging_names = request.POST.getlist("packaging_name")
            packaging_units = request.POST.getlist("packaging_unit")
            packaging_quantities = request.POST.getlist("packaging_quantity")
            for index, used_quantity_value in enumerate(packaging_quantities):
                if not used_quantity_value:
                    continue
                used_quantity = _decimal(used_quantity_value)
                if used_quantity <= 0:
                    raise ValueError("Packaging quantity must be positive.")
                packaging_sku = packaging_skus[index].strip() if index < len(packaging_skus) else ""
                packaging_name = packaging_names[index].strip() if index < len(packaging_names) else ""
                packaging_unit = packaging_units[index].strip() if index < len(packaging_units) else ""
                if packaging_sku:
                    packaging = Product.objects.select_for_update().get(
                        sku=packaging_sku,
                        active=True,
                        category=Product.Category.PACKAGING,
                    )
                else:
                    packaging = _find_or_create_inventory_item(
                        packaging_name,
                        "",
                        packaging_unit,
                        Product.Category.PACKAGING,
                    )
                RecipeItem.objects.create(recipe=recipe, material=packaging, quantity=used_quantity)
            batch_number = _next_batch_number(product)
            batch_reference = batch_name or f"BATCH-{batch_number:03d}-{product.sku}"
            if ProductionBatch.objects.filter(reference=batch_reference).exists():
                batch_reference = f"{batch_reference}-{get_random_string(6).upper()}"
            batch = ProductionBatch.objects.create(
                reference=batch_reference,
                recipe=recipe,
                quantity=quantity,
                batch_number=batch_number,
                production_date=timezone.localdate(),
                created_by=request.user,
            )
            complete_batch(batch)
        messages.success(request, f"Production batch {batch.reference} completed.")
    except (ValueError, StockLocation.DoesNotExist, Product.DoesNotExist) as exc:
        messages.error(request, str(exc))
    return redirect("manager_dashboard" if request.user.role == User.Role.MANAGER or request.user.is_superuser else "factory_dashboard")


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
            if not sku or quantity <= 0:
                raise ValueError("SKU and quantity are required.")
            batch = None
            if destination not in ("DAR", "MWANZA"):
                raise ValueError("Select a valid branch destination.")
            product = Product.objects.get(
                sku=sku,
                active=True,
                category=Product.Category.FINISHED_GOOD,
            )
            if batch_id:
                batch = ProductionBatch.objects.select_for_update().get(
                    pk=batch_id,
                    recipe__product=product,
                    status=ProductionBatch.Status.COMPLETED,
                )
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
    except (ValueError, StockLocation.DoesNotExist, Product.DoesNotExist) as exc:
        messages.error(request, str(exc))
    return redirect("manager_dashboard" if request.user.role == User.Role.MANAGER or request.user.is_superuser else "factory_dashboard")


def _branch_role(request):
    if request.user.is_superuser:
        return
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
            if not sku or not customer_id or quantity <= 0:
                raise ValueError("Customer, SKU, and quantity are required.")
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
            if batch_id:
                batch = ProductionBatch.objects.select_for_update().get(
                    pk=batch_id,
                    recipe__product=product,
                    status=ProductionBatch.Status.COMPLETED,
                )
                stock_entries = InventoryLedger.objects.filter(
                    location=location,
                    product=product,
                    production_batch=batch,
                )
            else:
                stock_entries = InventoryLedger.objects.filter(
                    location=location,
                    product=product,
                )
            available = stock_entries.aggregate(
                total=models.Sum("quantity")
            )["total"] or Decimal("0")
            if quantity > available:
                raise ValueError(
                    f"Stock haitoshi kwenye batch hii: stock {available} {product.unit}."
                )
            unit_price = product.unit_price
            sale = Sale.objects.create(
                reference=_reference("SALE"),
                location=location,
                customer=customer,
                sold_by=request.user,
                total_amount=quantity * unit_price,
            )
            SaleItem.objects.create(
                sale=sale,
                product=product,
                batch=batch,
                quantity=quantity,
                unit_price=unit_price,
            )
            confirm_sale(sale)
        messages.success(request, f"Sale {sale.reference} recorded.")
    except (
        ValueError,
        StockLocation.DoesNotExist,
        Product.DoesNotExist,
        Customer.DoesNotExist,
    ) as exc:
        messages.error(request, str(exc))
    dashboard = "mwanza_dashboard" if request.user.role == User.Role.BRANCH_MWANZA else "dar_dashboard"
    return redirect(dashboard)


@login_required(login_url="login")
@require_POST
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
            batch = ProductionBatch.objects.select_for_update().get(pk=batch_id)
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
    except ValueError as exc:
        messages.error(request, str(exc))
    dashboard = "mwanza_dashboard" if request.user.role == User.Role.BRANCH_MWANZA else "dar_dashboard"
    return redirect(dashboard)


@login_required(login_url="login")
@require_POST
def record_customer(request):
    _branch_role(request)
    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, "Customer name is required.")
    else:
        try:
            location = _branch_location(request)
            Customer.objects.get_or_create(
                name=name,
                location=location,
                defaults={
                    "phone": request.POST.get("phone", "").strip(),
                    "email": request.POST.get("email", "").strip(),
                    "address": request.POST.get("address", "").strip(),
                },
            )
            messages.success(request, "Customer saved to this branch.")
        except ValueError as exc:
            messages.error(request, str(exc))
    dashboard = "mwanza_dashboard" if request.user.role == User.Role.BRANCH_MWANZA else "dar_dashboard"
    return redirect(dashboard)


@login_required(login_url="login")
@require_POST
def record_call(request):
    _branch_role(request)
    try:
        customer_id = request.POST.get("customer_id", "").strip()
        outcome = request.POST.get("outcome", "").strip()
        if not customer_id or not outcome:
            raise ValueError("Customer and outcome are required.")
        location = _branch_location(request)
        customer = Customer.objects.get(
            pk=customer_id,
            location=location,
            active=True,
        )
        follow_up_value = request.POST.get("follow_up", "").strip()
        follow_up = parse_date(follow_up_value) if follow_up_value else None
        if follow_up_value and follow_up is None:
            raise ValueError("Enter a valid follow-up date.")
        CustomerCall.objects.create(
            customer=customer,
            called_by=request.user,
            outcome=outcome,
            notes=request.POST.get("notes", "").strip(),
            follow_up_date=follow_up,
        )
        messages.success(request, "Customer call recorded.")
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
        if request.user.role == User.Role.BRANCH_MWANZA:
            location = _location(StockLocation.LocationType.BRANCH_MWANZA)
        elif request.user.role == User.Role.BRANCH_DAR:
            location = _location(StockLocation.LocationType.BRANCH_DAR)
        else:
            location = _location(StockLocation.LocationType.FACTORY)
        batch = None
        if batch_id:
            batch = ProductionBatch.objects.select_for_update().get(pk=batch_id)
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
    except (ValueError, StockLocation.DoesNotExist, Product.DoesNotExist) as exc:
        messages.error(request, str(exc))
    if request.user.role == User.Role.BRANCH_MWANZA:
        return redirect("mwanza_dashboard")
    if request.user.role == User.Role.BRANCH_DAR:
        return redirect("dar_dashboard")
    return redirect("manager_dashboard" if request.user.role == User.Role.MANAGER else "factory_dashboard")


@login_required(login_url="login")
@require_POST
@transaction.atomic
def submit_daily_report(request):
    _branch_role(request)
    try:
        location = _branch_location(request)
        batch_id = request.POST.get("batch_id", "").strip()
        batch = None
        if batch_id:
            batch = ProductionBatch.objects.select_for_update().get(
                pk=batch_id,
            )
        report_date = timezone.localdate()
        decimal_fields = ("units_sold", "closing_balance", "loss_quantity")
        report_values = {}
        for field in decimal_fields:
            report_values[field] = _decimal(request.POST.get(field))
        integer_fields = (
            "total_customers",
            "new_customers",
            "returning_customers",
            "visitors",
            "deliveries",
            "parcels",
            "instruction_calls",
            "compliance_calls",
            "followup_calls",
        )
        for field in integer_fields:
            value = int(request.POST.get(field, "0") or "0")
            if value < 0:
                raise ValueError("Report counts cannot be negative.")
            report_values[field] = value
        report, _ = BranchDailyReport.objects.update_or_create(
            location=location.location_type,
            report_date=report_date,
            defaults={
                **report_values,
                "customer_addresses": request.POST.get("customer_addresses", "").strip(),
                "status": BranchDailyReport.Status.SUBMITTED,
                "submitted_by": request.user,
                "batch": batch,
            },
        )
        messages.success(request, f"Daily report {report.report_date} submitted.")
    except (ValueError, InvalidOperation) as exc:
        messages.error(request, str(exc))
    if request.user.role == User.Role.BRANCH_MWANZA:
        return redirect("mwanza_dashboard")
    return redirect("dar_dashboard")


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
