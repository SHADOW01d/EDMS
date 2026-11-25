import csv
from datetime import datetime, time, timedelta
from decimal import Decimal
import uuid

from django.contrib.messages import get_messages
from django.db.models import Sum
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.customers.models import (
    BranchDailyReport,
    BranchDelivery,
    BranchExpense,
    Customer,
    CustomerCall,
    CustomerVisit,
)
from apps.distribution.models import Transfer, TransferItem
from apps.inventory.models import InventoryLedger, Product, StockLocation
from apps.production.models import ProductionBatch, ProductionConsumption, ProductionOutput, Recipe
from apps.procurement.models import Purchase, PurchaseItem, Supplier
from apps.reports.exports import csv_response
from apps.sales.models import Sale, SaleItem
from apps.inventory.services import post_movement


class ManagerDashboardTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="manager",
            password="test-password-123",
            role=User.Role.MANAGER,
        )

    def test_manager_login_redirects_to_dashboard(self):
        response = self.client.post(
            reverse("login"),
            {"username": "manager", "password": "test-password-123"},
        )

        self.assertRedirects(response, reverse("manager_dashboard"))

    def test_admin_can_create_a_non_superuser_manager_who_logs_into_manager_dashboard(self):
        admin_user = User.objects.create_superuser(
            username="site-admin",
            email="admin@example.com",
            password="Admin-password-123",
        )
        admin_login_response = self.client.post(
            reverse("admin:login"),
            {
                "username": admin_user.username,
                "password": "Admin-password-123",
            },
        )
        self.assertRedirects(admin_login_response, reverse("admin:index"))

        add_url = reverse("admin:accounts_user_add")
        add_page = self.client.get(add_url)
        self.assertTrue(add_page.context["adminform"].form.fields["role"].required)
        missing_role_response = self.client.post(
            add_url,
            {
                "username": "manager-without-role",
                "password1": "Unassigned-password-123",
                "password2": "Unassigned-password-123",
            },
        )
        self.assertEqual(missing_role_response.status_code, 200)
        self.assertFalse(User.objects.filter(username="manager-without-role").exists())

        response = self.client.post(
            add_url,
            {
                "username": "operations-manager",
                "password1": "Manager-password-123",
                "password2": "Manager-password-123",
                "role": User.Role.MANAGER,
            },
        )

        self.assertEqual(response.status_code, 302)
        manager = User.objects.get(username="operations-manager")
        self.assertEqual(manager.role, User.Role.MANAGER)
        self.assertFalse(manager.is_superuser)
        self.assertFalse(manager.is_staff)
        change_page = self.client.get(
            reverse("admin:accounts_user_change", args=[manager.pk])
        )
        self.assertTrue(change_page.context["adminform"].form.fields["role"].required)

        self.client.logout()
        login_response = self.client.post(
            reverse("login"),
            {
                "username": "operations-manager",
                "password": "Manager-password-123",
                "next": reverse("factory_dashboard"),
            },
        )

        self.assertRedirects(login_response, reverse("manager_dashboard"))

    def test_manager_dashboard_contains_branch_and_calls_views(self):
        self.client.force_login(self.manager)

        response = self.client.get(reverse("manager_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-view="mwanza"')
        self.assertContains(response, 'data-view="dar"')
        self.assertContains(response, 'data-view="calls"')
        self.assertContains(response, "Follow-up queue")
        self.assertContains(response, "manager")
        self.assertContains(response, 'id="managerBatchConfirm"')
        self.assertContains(response, 'id="workspaceConfirmDialog"')
        self.assertContains(response, "Rekodi za batch zilizopo hazitafutwa wala kuhamishwa.")
        self.assertNotContains(response, "figures in this prototype are illustrative")
        self.assertContains(response, "Stock by product across all locations")
        self.assertContains(response, "Produced all time")

    def test_manager_dashboard_shows_production_and_current_stock_by_product_and_location(self):
        product = Product.objects.create(
            name="Effective Diet",
            sku="CEO-STOCK-EFFECTIVE-DIET",
            category=Product.Category.FINISHED_GOOD,
            unit="pieces",
        )
        batch = ProductionBatch.objects.create(
            reference="CEO-STOCK-SUMMARY",
            quantity=120,
            batch_number=1,
            status=ProductionBatch.Status.COMPLETED,
            production_date=timezone.localdate(),
            created_by=self.manager,
        )
        ProductionOutput.objects.create(
            batch=batch,
            product=product,
            quantity=120,
            production_date=timezone.localdate(),
            reference="CEO-STOCK-SUMMARY-OUTPUT",
            created_by=self.manager,
        )
        factory, _ = StockLocation.objects.get_or_create(
            location_type=StockLocation.LocationType.FACTORY,
            defaults={"name": "Factory"},
        )
        mwanza, _ = StockLocation.objects.get_or_create(
            location_type=StockLocation.LocationType.BRANCH_MWANZA,
            defaults={"name": "Mwanza"},
        )
        dar, _ = StockLocation.objects.get_or_create(
            location_type=StockLocation.LocationType.BRANCH_DAR,
            defaults={"name": "Dar es Salaam"},
        )
        for location, quantity in ((factory, 50), (mwanza, 40), (dar, 30)):
            post_movement(
                product=product,
                location=location,
                movement=InventoryLedger.Movement.PRODUCTION_IN,
                quantity=quantity,
                reference=f"CEO-STOCK-{location.location_type}",
                production_batch=batch,
            )
        self.client.force_login(self.manager)

        response = self.client.get(reverse("manager_dashboard"))

        self.assertEqual(response.status_code, 200)
        stock_row = next(
            row for row in response.context["production_by_product"]
            if row["product"] == product
        )
        self.assertEqual(stock_row["produced_total"], Decimal("120"))
        self.assertEqual(stock_row["factory_balance"], Decimal("50"))
        self.assertEqual(stock_row["mwanza_balance"], Decimal("40"))
        self.assertEqual(stock_row["dar_balance"], Decimal("30"))
        self.assertEqual(stock_row["current_stock"], Decimal("120"))
        self.assertContains(response, "Effective Diet")

    def test_manager_dashboard_creates_factory_location_for_empty_database(self):
        self.client.force_login(self.manager)

        response = self.client.get(reverse("manager_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            StockLocation.objects.filter(
                location_type=StockLocation.LocationType.FACTORY,
            ).exists()
        )

    def test_manager_dashboard_shows_receiving_form_with_each_items_unit_and_stock(self):
        raw_material = Product.objects.create(
            name="Soya lishe",
            sku="TEST-SOYA",
            category=Product.Category.RAW_MATERIAL,
            unit="kg",
        )
        post_movement(
            product=raw_material,
            location=StockLocation.objects.create(
                name="Factory",
                location_type=StockLocation.LocationType.FACTORY,
            ),
            movement=InventoryLedger.Movement.PURCHASE,
            quantity=12,
            reference="OPENING-SOYA",
        )
        self.client.force_login(self.manager)

        response = self.client.get(reverse("manager_dashboard"))

        self.assertContains(response, "Pokea bidhaa stoo")
        self.assertContains(response, 'data-unit="kg"')
        raw_row = next(
            row for row in response.context["purchase_product_rows"]
            if row["product"] == raw_material
        )
        self.assertEqual(raw_row["balance"], Decimal("12"))
        self.assertContains(response, "Jumla ya malipo")

    def test_sales_trend_shows_daily_monday_to_sunday_totals_with_dates(self):
        mwanza = StockLocation.objects.create(
            name="Mwanza",
            location_type=StockLocation.LocationType.BRANCH_MWANZA,
        )
        dar = StockLocation.objects.create(
            name="Dar es Salaam",
            location_type=StockLocation.LocationType.BRANCH_DAR,
        )
        today = timezone.localdate()
        monday = today - timedelta(days=today.weekday())
        monday_sale = Sale.objects.create(
            reference="WEEKLY-GRAPH-MWANZA",
            location=mwanza,
            sold_by=self.manager,
            total_amount="120000",
        )
        tuesday_sale = Sale.objects.create(
            reference="WEEKLY-GRAPH-TUESDAY",
            location=mwanza,
            sold_by=self.manager,
            total_amount="30000",
        )
        dar_sale = Sale.objects.create(
            reference="WEEKLY-GRAPH-DAR",
            location=dar,
            sold_by=self.manager,
            total_amount="45000",
        )
        Sale.objects.filter(pk=monday_sale.pk).update(
            sold_at=timezone.make_aware(datetime.combine(monday, time(10)))
        )
        Sale.objects.filter(pk=tuesday_sale.pk).update(
            sold_at=timezone.make_aware(datetime.combine(monday + timedelta(days=1), time(10)))
        )
        Sale.objects.filter(pk=dar_sale.pk).update(
            sold_at=timezone.make_aware(datetime.combine(monday, time(11)))
        )
        self.client.force_login(self.manager)

        response = self.client.get(reverse("manager_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["sales_trend_labels"]), 7)
        self.assertEqual(
            response.context["sales_trend_labels"],
            [
                f"{day} {(monday + timedelta(days=index)).strftime('%d/%m')}"
                for index, day in enumerate(
                    ("Jumatatu", "Jumanne", "Jumatano", "Alhamisi", "Ijumaa", "Jumamosi", "Jumapili")
                )
            ],
        )
        self.assertEqual(response.context["sales_trend_mwanza"][0], 120000)
        self.assertEqual(response.context["sales_trend_mwanza"][1], 30000)
        self.assertEqual(response.context["sales_trend_dar"][0], 45000)
        self.assertEqual(response.context["sales_trend_dar"][1:], [0, 0, 0, 0, 0, 0])
        self.assertContains(response, "Jumatatu–Jumapili")

    def test_manager_can_update_catalog_product(self):
        product = Product.objects.create(
            name="Asali mbichi",
            sku="TEST-HONEY",
            category=Product.Category.FINISHED_GOOD,
            unit="package",
            unit_price="15000",
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("update_catalog_product", args=[product.pk]),
            {
                "name": "Wild Honey / Asali Pekee",
                "sku": "TEST-HONEY",
                "unit": "package",
                "unit_price": "15000",
            },
        )

        self.assertRedirects(response, reverse("manager_dashboard"))
        product.refresh_from_db()
        self.assertEqual(product.name, "Wild Honey / Asali Pekee")
        self.assertEqual(product.sku, "TEST-HONEY")
        self.assertEqual(product.unit_price, Decimal("15000"))

    def test_manager_can_add_a_product_with_its_unit_and_price(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("create_catalog_product"),
            {
                "name": "Custom product",
                "sku": "CUSTOM-PRODUCT",
                "unit": "pcs",
                "unit_price": "32000",
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('manager_dashboard')}?view=catalog",
        )
        product = Product.objects.get(sku="CUSTOM-PRODUCT")
        self.assertEqual(product.category, Product.Category.FINISHED_GOOD)
        self.assertEqual(product.unit, "pcs")
        self.assertEqual(product.unit_price, Decimal("32000"))

    def test_manager_chart_product_labels_are_json_script_escaped(self):
        malicious_name = "</script><script>alert(1)</script>"
        Product.objects.create(
            name=malicious_name,
            sku="XSS-TEST",
            category=Product.Category.FINISHED_GOOD,
        )
        self.client.force_login(self.manager)

        response = self.client.get(reverse("manager_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            r"\u003C/script\u003E\u003Cscript\u003Ealert(1)\u003C/script\u003E",
        )
        self.assertNotContains(response, f'labels: ["{malicious_name}"]')

    def test_distribution_chart_uses_matching_per_product_stock_series(self):
        product = Product.objects.create(
            name="Chart Product",
            sku="CHART-STOCK-001",
            category=Product.Category.FINISHED_GOOD,
        )
        factory = StockLocation.objects.create(
            name="Factory",
            location_type=StockLocation.LocationType.FACTORY,
        )
        mwanza = StockLocation.objects.create(
            name="Mwanza",
            location_type=StockLocation.LocationType.BRANCH_MWANZA,
        )
        dar = StockLocation.objects.create(
            name="Dar",
            location_type=StockLocation.LocationType.BRANCH_DAR,
        )
        for location, quantity in ((factory, 10), (mwanza, 4), (dar, 7)):
            post_movement(
                product=product,
                location=location,
                movement=InventoryLedger.Movement.ADJUSTMENT,
                quantity=quantity,
            )
        self.client.force_login(self.manager)

        response = self.client.get(reverse("manager_dashboard"))

        self.assertEqual(response.status_code, 200)
        labels = response.context["distribution_product_labels"]
        factory_stock = response.context["distribution_factory_stock"]
        mwanza_stock = response.context["distribution_mwanza_stock"]
        dar_stock = response.context["distribution_dar_stock"]
        product_index = labels.index(product.name)
        self.assertEqual(factory_stock[product_index], 10.0)
        self.assertEqual(mwanza_stock[product_index], 4.0)
        self.assertEqual(dar_stock[product_index], 7.0)
        self.assertEqual(
            {len(labels), len(factory_stock), len(mwanza_stock), len(dar_stock)},
            {len(labels)},
        )

    def test_distribution_new_transfer_button_opens_a_working_dispatch_form(self):
        self.client.force_login(self.manager)

        response = self.client.get(reverse("manager_dashboard"))

        self.assertContains(response, 'data-bs-target="#managerTransferModal"')
        self.assertContains(response, 'id="managerTransferModal"')
        self.assertContains(response, 'action="/operations/transfers/record/"')
        self.assertContains(response, 'name="sku"')
        self.assertContains(response, 'name="quantity"')
        self.assertContains(response, 'name="destination"')

    def test_money_amounts_are_displayed_with_thousands_separators(self):
        location = StockLocation.objects.create(
            name="Dar",
            location_type=StockLocation.LocationType.BRANCH_DAR,
        )
        Sale.objects.create(
            reference="SALE-COMMA-TEST",
            location=location,
            sold_by=self.manager,
            total_amount=Decimal("1234567.89"),
        )
        self.client.force_login(self.manager)

        manager_response = self.client.get(reverse("manager_dashboard"))
        branch_user = User.objects.create_user(
            username="comma-dar",
            password="test-password-123",
            role=User.Role.BRANCH_DAR,
        )
        self.client.force_login(branch_user)
        branch_response = self.client.get(reverse("dar_dashboard"))

        self.assertEqual(manager_response.status_code, 200)
        self.assertEqual(branch_response.status_code, 200)
        self.assertIn("TZS 1,234,568", manager_response.content.decode())
        self.assertIn("1,234,568", branch_response.content.decode())

    def test_non_manager_cannot_open_manager_dashboard(self):
        branch_user = User.objects.create_user(
            username="mwanza",
            password="test-password-123",
            role=User.Role.BRANCH_MWANZA,
        )
        self.client.force_login(branch_user)

        response = self.client.get(reverse("manager_dashboard"))

        self.assertEqual(response.status_code, 403)


class RoleWorkspaceTests(TestCase):
    def test_root_branch_pages_redirect_to_the_current_workspaces(self):
        cases = (
            ("mwanza-manager-page", "mwanza_dashboard"),
            ("dar-manager-page", "dar_dashboard"),
        )

        for page_name, dashboard_name in cases:
            with self.subTest(page=page_name):
                response = self.client.get(reverse(page_name))
                self.assertRedirects(
                    response,
                    reverse(dashboard_name),
                    fetch_redirect_response=False,
                )

    def test_standalone_factory_page_is_role_protected_and_serves_its_own_ui(self):
        page_url = reverse("factory-workspace-page")
        anonymous_response = self.client.get(page_url)
        self.assertRedirects(
            anonymous_response,
            f"{reverse('login')}?next={page_url}",
            fetch_redirect_response=False,
        )

        factory_user = User.objects.create_user(
            username="standalone-factory",
            password="standalone-password-123",
            role=User.Role.FACTORY,
        )
        self.client.force_login(factory_user)
        response = self.client.get(page_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")
        page_html = b"".join(response.streaming_content).decode()
        self.assertIn("Kiwanda Factory Workspace", page_html)
        self.assertIn("Raw materials &amp; procurement", page_html)
        self.assertIn("No purchase records yet", page_html)
        self.assertIn("No production batches yet", page_html)
        self.assertIn("No dispatches recorded", page_html)
        self.assertNotIn("http-equiv=\"refresh\"", page_html)
        for section in ("overview", "materials", "production", "dispatch"):
            self.assertIn(f'data-section-panel="{section}"', page_html)
        self.assertIn("> Tuma kwa Ofisi</a>", page_html)
        self.assertIn("text-decoration: none;", page_html)
        self.assertIn('id="materials" data-section-panel="materials" aria-labelledby="materialsTitle" hidden', page_html)
        self.assertIn('id="production" data-section-panel="production" aria-labelledby="productionTitle" hidden', page_html)
        self.assertIn('id="dispatch" data-section-panel="dispatch" aria-labelledby="dispatchTitle" hidden', page_html)

        manager_user = User.objects.create_user(
            username="not-factory",
            password="not-factory-password-123",
            role=User.Role.MANAGER,
        )
        self.client.force_login(manager_user)
        self.assertEqual(self.client.get(page_url).status_code, 403)

        branch_user = User.objects.create_user(
            username="not-factory-branch",
            password="not-factory-branch-password-123",
            role=User.Role.BRANCH_DAR,
        )
        self.client.force_login(branch_user)
        self.assertEqual(self.client.get(page_url).status_code, 403)

        superuser = User.objects.create_superuser(
            username="factory-page-admin",
            email="admin@example.com",
            password="factory-page-admin-password-123",
        )
        self.client.force_login(superuser)
        self.assertEqual(self.client.get(page_url).status_code, 200)

    def test_role_logins_redirect_to_their_own_workspaces(self):
        cases = (
            (User.Role.FACTORY, "factory_dashboard"),
            (User.Role.BRANCH_MWANZA, "mwanza_dashboard"),
            (User.Role.BRANCH_DAR, "dar_dashboard"),
        )

        for index, (role, route_name) in enumerate(cases):
            with self.subTest(role=role):
                username = f"workspace-user-{index}"
                User.objects.create_user(
                    username=username,
                    password="workspace-password-123",
                    role=role,
                )
                response = self.client.post(
                    reverse("login"),
                    {"username": username, "password": "workspace-password-123"},
                )

                self.assertRedirects(response, reverse(route_name))
                self.client.logout()

    def test_unassigned_regular_user_cannot_sign_in(self):
        User.objects.create_user(
            username="unassigned-user",
            password="unassigned-password-123",
        )

        response = self.client.post(
            reverse("login"),
            {"username": "unassigned-user", "password": "unassigned-password-123"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This account has no assigned EDMS role.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_superuser_login_defaults_to_admin_site(self):
        User.objects.create_superuser(
            username="root-admin",
            email="root@example.com",
            password="Root-password-123",
        )

        response = self.client.post(
            reverse("login"),
            {"username": "root-admin", "password": "Root-password-123"},
        )

        self.assertRedirects(response, reverse("admin:index"))

    def test_factory_workspace_shows_empty_states_not_fabricated_totals(self):
        factory_user = User.objects.create_user(
            username="factory",
            password="workspace-password-123",
            role=User.Role.FACTORY,
        )
        self.client.force_login(factory_user)

        response = self.client.get(reverse("factory_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Welcome, factory")
        self.assertContains(response, "Kiwanda")
        self.assertContains(response, "KIWANDA (FACTORY)")
        self.assertContains(response, "Factory Manager")
        self.assertContains(response, "factory-account")
        self.assertContains(response, "Start new batch")
        self.assertContains(response, 'id="factoryBatchConfirm"')
        self.assertContains(response, "Batch hii haitakuwa tayari kwa uzalishaji mpaka CEO aidhinishe.")
        self.assertContains(response, '<button class="factory-hero-action" type="button" onclick="activateFactorySection(\'production\', true)">')
        self.assertContains(response, "No purchase records yet")
        self.assertContains(response, "No production batches yet")
        self.assertContains(response, "No dispatches recorded")
        for section in ("overview", "procurement", "production", "dispatch"):
            self.assertContains(response, f'data-factory-panel="{section}"')
        for section in ("overview", "procurement", "production"):
            self.assertContains(response, f'data-factory-section="{section}"')
        self.assertContains(response, "> Tuma kwa Ofisi</a>")
        self.assertContains(response, 'id="factory-procurement" data-factory-panel="procurement" aria-labelledby="factoryProcurementTitle" hidden')
        self.assertContains(response, 'id="factory-production" data-factory-panel="production" aria-labelledby="factoryProductionTitle" hidden')
        self.assertContains(response, 'id="factory-dispatch" data-factory-panel="dispatch" aria-labelledby="factoryDispatchTitle" hidden')
        self.assertNotContains(response, "1,350")

    def test_branch_workspaces_are_role_scoped_and_have_report_preview(self):
        cases = (
            (User.Role.BRANCH_MWANZA, "mwanza_dashboard", "Mwanza branch overview"),
            (User.Role.BRANCH_DAR, "dar_dashboard", "Dar es Salaam branch overview"),
        )

        for index, (role, route_name, heading) in enumerate(cases):
            with self.subTest(role=role):
                user = User.objects.create_user(
                    username=f"branch-user-{index}",
                    password="workspace-password-123",
                    role=role,
                )
                self.client.force_login(user)
                response = self.client.get(reverse(route_name))

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, heading)
                self.assertContains(response, f"Welcome, branch-user-{index}")
                self.assertContains(response, "Incoming transfers")
                self.assertContains(response, "Daily branch report")
                self.assertContains(response, "Mawasiliano na ufuatiliaji wa wateja")
                self.assertContains(response, "Recent branch activity")
                self.assertContains(response, "branch-account-role")
                self.assertContains(
                    response,
                    "Full Package (1 Wild Honey + 1 Presha Masala + 1 Effective Diet)",
                )
                self.assertContains(response, 'id="branchQuickCustomerButton"')
                self.assertContains(response, 'id="branchQuickCustomerDialog"')
                self.assertContains(response, 'name="name" maxlength="150" autocomplete="name" required')
                self.assertContains(response, 'name="diagnosis"')
                self.assertContains(response, 'name="short_description"')
                self.assertContains(response, 'name="address"')
                self.assertContains(response, 'action="/operations/customers/record/"')
                for section in ("overview", "transfers", "sales", "customers", "visitors", "deliveries", "expenses", "calls", "report"):
                    self.assertContains(response, f'data-branch-view="{section}"')
                self.assertContains(response, "No sales recorded today")
                self.assertNotContains(response, "450K")
                self.assertContains(response, "/operations/reports/submit/")
                self.assertContains(response, "Submit daily report")
                self.client.logout()

    def test_branch_stock_cards_show_package_components_not_full_package_card(self):
        package = Product.objects.get(sku="ED-PK-FULL")
        package.name = "Effective Diet Full Package"
        package.save(update_fields=["name"])
        location, _ = StockLocation.objects.get_or_create(
            location_type=StockLocation.LocationType.BRANCH_MWANZA,
            defaults={"name": "Mwanza"},
        )
        post_movement(
            product=package,
            location=location,
            movement=InventoryLedger.Movement.TRANSFER_IN,
            quantity=192,
            reference="PACKAGE-STOCK-TEST",
        )
        user = User.objects.create_user(
            username="mwanza-stock-test",
            password="workspace-password-123",
            role=User.Role.BRANCH_MWANZA,
        )
        self.client.force_login(user)
        response = self.client.get(reverse("mwanza_dashboard"))
        rows = response.context["finished_stock_rows"]
        balances = {row["display_name"]: row["balance"] for row in rows}
        self.assertEqual(balances["Effective Diet"], 192)
        self.assertEqual(balances["Pressure Masala"], 192)
        self.assertEqual(balances["Wild Honey / Asali"], 192)
        self.assertNotIn("Effective Diet Full Package", {row["display_name"] for row in rows})

    def test_users_cannot_open_another_role_workspace(self):
        branch_user = User.objects.create_user(
            username="branch-access-check",
            password="workspace-password-123",
            role=User.Role.BRANCH_MWANZA,
        )
        self.client.force_login(branch_user)

        self.assertEqual(self.client.get(reverse("factory_dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("dar_dashboard")).status_code, 403)

    def test_every_role_is_limited_to_its_own_dashboard(self):
        dashboard_by_role = {
            User.Role.MANAGER: "manager_dashboard",
            User.Role.FACTORY: "factory_dashboard",
            User.Role.BRANCH_MWANZA: "mwanza_dashboard",
            User.Role.BRANCH_DAR: "dar_dashboard",
        }

        for index, (role, allowed_dashboard) in enumerate(dashboard_by_role.items()):
            user = User.objects.create_user(
                username=f"role-access-{index}",
                password="role-access-password-123",
                role=role,
            )
            self.client.force_login(user)
            for other_dashboard in dashboard_by_role.values():
                with self.subTest(role=role, dashboard=other_dashboard):
                    response = self.client.get(reverse(other_dashboard))
                    expected_status = 200 if other_dashboard == allowed_dashboard else 403
                    self.assertEqual(response.status_code, expected_status)
            self.client.logout()

    def test_anonymous_users_are_sent_to_sign_in_for_every_workspace(self):
        dashboard_routes = (
            "manager_dashboard",
            "factory_dashboard",
            "mwanza_dashboard",
            "dar_dashboard",
        )

        for dashboard_route in dashboard_routes:
            with self.subTest(dashboard=dashboard_route):
                response = self.client.get(reverse(dashboard_route))
                self.assertRedirects(
                    response,
                    f"{reverse('login')}?next={reverse(dashboard_route)}",
                    fetch_redirect_response=False,
                )

    def test_dashboard_admin_alias_redirects_to_django_admin(self):
        response = self.client.get(reverse("dashboard_admin"))
        self.assertRedirects(
            response,
            reverse("admin:index"),
            fetch_redirect_response=False,
        )

        no_slash_response = self.client.get("/dashboard/admin")
        self.assertRedirects(
            no_slash_response,
            reverse("dashboard_admin"),
            status_code=301,
            fetch_redirect_response=False,
        )


class OperationalFlowTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="operations-manager",
            password="Operations-password-123",
            role=User.Role.MANAGER,
        )
        self.branch = User.objects.create_user(
            username="operations-mwanza",
            password="Operations-password-123",
            role=User.Role.BRANCH_MWANZA,
        )
        StockLocation.objects.create(
            name="Mwanza",
            location_type=StockLocation.LocationType.BRANCH_MWANZA,
        )
        self.dar_location = StockLocation.objects.create(
            name="Dar es Salaam",
            location_type=StockLocation.LocationType.BRANCH_DAR,
        )
        self.factory_location = StockLocation.objects.create(
            name="Factory",
            location_type=StockLocation.LocationType.FACTORY,
        )

    def test_actual_purchase_payment_is_saved_separately(self):
        material = Product.objects.create(
            name="Negotiated raw material",
            sku="NEGOTIATED-MATERIAL",
            category=Product.Category.RAW_MATERIAL,
            unit="kg",
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("record_purchase"),
            {
                "supplier": "Negotiated Supplier",
                "sku": material.sku,
                "quantity": "10",
                "unit_cost": "15000",
                "actual_payment": "135000",
            },
        )

        self.assertRedirects(response, reverse("manager_dashboard"))
        purchase = Purchase.objects.get()
        item = purchase.items.get()
        self.assertEqual(purchase.total_amount, Decimal("135000"))
        self.assertEqual(purchase.actual_payment, Decimal("135000"))
        self.assertEqual(purchase.calculated_amount, Decimal("150000"))
        self.assertEqual(item.pricing_unit, PurchaseItem.PricingUnit.KG)

    def test_batch_sales_deduct_only_the_selected_batch(self):
        factory = self.factory_location
        mwanza = StockLocation.objects.get(location_type=StockLocation.LocationType.BRANCH_MWANZA)
        product = Product.objects.create(
            name="Batch Product",
            sku="BATCH-PRODUCT",
            category=Product.Category.FINISHED_GOOD,
            unit="packs",
        )
        recipe = Recipe.objects.create(product=product, yield_quantity=1)
        batch_one = ProductionBatch.objects.create(
            reference="BATCH-001",
            batch_number=1,
            recipe=recipe,
            quantity=150,
            status=ProductionBatch.Status.COMPLETED,
            production_date=timezone.localdate(),
            created_by=self.manager,
        )
        batch_two = ProductionBatch.objects.create(
            reference="BATCH-002",
            batch_number=2,
            recipe=recipe,
            quantity=500,
            status=ProductionBatch.Status.COMPLETED,
            production_date=timezone.localdate(),
            created_by=self.manager,
        )
        post_movement(
            product=product,
            location=mwanza,
            movement=InventoryLedger.Movement.TRANSFER_IN,
            quantity=150,
            reference="TRANSFER-BATCH-001",
            production_batch=batch_one,
        )
        post_movement(
            product=product,
            location=mwanza,
            movement=InventoryLedger.Movement.TRANSFER_IN,
            quantity=500,
            reference="TRANSFER-BATCH-002",
            production_batch=batch_two,
        )
        customer = Customer.objects.create(
            name="Batch Customer",
            location=mwanza,
            active=True,
        )
        self.client.force_login(self.branch)

        response = self.client.post(
            reverse("record_sale"),
            {
                "customer_id": customer.pk,
                "sku": product.sku,
                "batch_id": batch_one.pk,
                "quantity": "10",
                "location_type": StockLocation.LocationType.BRANCH_MWANZA,
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('mwanza_dashboard')}?batch={batch_one.pk}",
        )
        batch_one_balance = InventoryLedger.objects.filter(
            location=mwanza,
            product=product,
            production_batch=batch_one,
        ).aggregate(total=Sum("quantity"))["total"]
        batch_two_balance = InventoryLedger.objects.filter(
            location=mwanza,
            product=product,
            production_batch=batch_two,
        ).aggregate(total=Sum("quantity"))["total"]
        self.assertEqual(batch_one_balance, Decimal("140"))
        self.assertEqual(batch_two_balance, Decimal("500"))

    def test_factory_batch_requires_manager_approval_and_manager_can_start_directly(self):
        factory_user = User.objects.create_user(
            username="batch-requester",
            password="test-password-123",
            role=User.Role.FACTORY,
        )
        self.client.force_login(factory_user)

        response = self.client.post(
            reverse("start_new_batch"),
            {"reference": "BATCH-NEEDS-CEO", "request_note": "New production run"},
        )

        self.assertRedirects(response, reverse("factory_dashboard"))
        batch = ProductionBatch.objects.get(reference="BATCH-NEEDS-CEO")
        self.assertEqual(batch.status, ProductionBatch.Status.PENDING_APPROVAL)
        self.assertEqual(batch.quantity, Decimal("0"))
        self.assertEqual(batch.outputs.count(), 0)
        self.assertEqual(batch.inventory_movements.count(), 0)

        self.client.force_login(self.manager)
        approve_response = self.client.post(
            reverse("approve_batch_request", args=[batch.pk]),
        )
        self.assertRedirects(
            approve_response,
            f"{reverse('manager_dashboard')}?batch={batch.pk}&welcome=1",
        )
        batch.refresh_from_db()
        self.assertEqual(batch.status, ProductionBatch.Status.ACTIVE)
        self.assertEqual(batch.approved_by, self.manager)
        self.assertIsNotNone(batch.approved_at)

        self.client.post(reverse("start_new_batch"), {"reference": "BATCH-CEO-DIRECT"})
        ceo_batch = ProductionBatch.objects.get(reference="BATCH-CEO-DIRECT")
        self.assertEqual(ceo_batch.status, ProductionBatch.Status.ACTIVE)
        self.assertEqual(ceo_batch.approved_by, self.manager)

    def test_production_output_consumes_multiple_materials_and_is_idempotent(self):
        factory_user = User.objects.create_user(
            username="production-recorder",
            password="test-password-123",
            role=User.Role.FACTORY,
        )
        product = Product.objects.create(
            name="Effective Diet",
            sku="OUTPUT-EFFECTIVE-DIET",
            category=Product.Category.FINISHED_GOOD,
            unit="packs",
        )
        cloves = Product.objects.create(
            name="Karafuu",
            sku="OUTPUT-CLOVE",
            category=Product.Category.RAW_MATERIAL,
            unit="kg",
        )
        nuts = Product.objects.create(
            name="Karanga",
            sku="OUTPUT-NUTS",
            category=Product.Category.RAW_MATERIAL,
            unit="kg",
        )
        packaging_a = Product.objects.create(
            name="Packaging A",
            sku="OUTPUT-PACK-A",
            category=Product.Category.PACKAGING,
            unit="piece",
        )
        packaging_b = Product.objects.create(
            name="Packaging B",
            sku="OUTPUT-PACK-B",
            category=Product.Category.PACKAGING,
            unit="piece",
        )
        batch = ProductionBatch.objects.create(
            reference="SHARED-PRODUCTION-BATCH",
            quantity=0,
            batch_number=2,
            status=ProductionBatch.Status.ACTIVE,
            production_date=timezone.localdate(),
            created_by=self.manager,
            approved_by=self.manager,
            approved_at=timezone.now(),
        )
        for material, quantity in (
            (cloves, 10),
            (nuts, 10),
            (packaging_a, 500),
            (packaging_b, 500),
        ):
            post_movement(
                product=material,
                location=self.factory_location,
                movement=InventoryLedger.Movement.PURCHASE,
                quantity=quantity,
                reference=f"OPENING-{material.sku}",
            )
        request_key = str(uuid.uuid4())
        payload = {
            "batch_id": batch.pk,
            "sku": product.sku,
            "quantity": "200",
            "production_date": timezone.localdate().isoformat(),
            "production_request_key": request_key,
            "material_sku": [cloves.sku, nuts.sku],
            "material_quantity": ["3", "2"],
            "packaging_sku": [packaging_a.sku, packaging_b.sku],
            "packaging_quantity": ["100", "100"],
        }
        self.client.force_login(factory_user)

        response = self.client.post(reverse("record_production"), payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(batch.outputs.count(), 1)
        output = batch.outputs.get()
        self.assertEqual(output.product, product)
        self.assertEqual(output.quantity, Decimal("200"))
        self.assertEqual(output.consumptions.count(), 4)
        self.assertEqual(
            InventoryLedger.objects.filter(
                product=cloves,
                location=self.factory_location,
                movement=InventoryLedger.Movement.PRODUCTION_OUT,
            ).aggregate(total=Sum("quantity"))["total"],
            Decimal("-3"),
        )
        self.assertEqual(
            InventoryLedger.objects.filter(
                product=product,
                location=self.factory_location,
                production_batch=batch,
            ).aggregate(total=Sum("quantity"))["total"],
            Decimal("200"),
        )
        response = self.client.post(reverse("record_production"), payload)
        self.assertEqual(batch.outputs.count(), 1)
        self.assertEqual(
            InventoryLedger.objects.filter(
                reference=output.reference,
                movement=InventoryLedger.Movement.PRODUCTION_IN,
            ).count(),
            1,
        )
        response = self.client.get(reverse("factory_dashboard"))
        self.assertEqual(response.status_code, 200)
        inventory_rows = {
            row["product"].sku: row
            for row in response.context["material_inventory_rows"]
        }
        self.assertEqual(inventory_rows[cloves.sku]["used_quantity"], Decimal("3"))
        self.assertEqual(inventory_rows[cloves.sku]["balance"], Decimal("7"))
        self.assertEqual(inventory_rows[nuts.sku]["used_quantity"], Decimal("2"))
        self.assertEqual(inventory_rows[nuts.sku]["balance"], Decimal("8"))
        self.assertEqual(inventory_rows[packaging_a.sku]["used_quantity"], Decimal("100"))
        self.assertEqual(inventory_rows[packaging_a.sku]["balance"], Decimal("400"))
        self.assertContains(response, "Matumizi halisi ya malighafi na vifungashio")
        self.assertEqual(len(response.context["production_consumption_rows"]), 4)

    def test_production_requires_selecting_a_registered_material(self):
        factory_user = User.objects.create_user(
            username="new-material-recorder",
            password="test-password-123",
            role=User.Role.FACTORY,
        )
        product = Product.objects.create(
            name="Pressure Masala",
            sku="OUTPUT-PRESSURE",
            category=Product.Category.FINISHED_GOOD,
        )
        material = Product.objects.create(
            name="Registered production herb",
            sku="REGISTERED-PRODUCTION-HERB",
            category=Product.Category.RAW_MATERIAL,
            unit="kg",
        )
        batch = ProductionBatch.objects.create(
            reference="NEW-MATERIAL-BATCH",
            quantity=0,
            batch_number=3,
            status=ProductionBatch.Status.ACTIVE,
            production_date=timezone.localdate(),
            created_by=self.manager,
        )
        self.client.force_login(factory_user)

        response = self.client.post(
            reverse("record_production"),
            {
                "batch_id": batch.pk,
                "sku": product.sku,
                "quantity": "50",
                "production_request_key": str(uuid.uuid4()),
                "material_name": ["New Herb"],
                "material_unit": ["kg"],
                "material_quantity": ["2"],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Product.objects.filter(name="New Herb").exists())
        self.assertEqual(batch.outputs.count(), 0)
        self.assertIn(
            "Select a registered raw material.",
            str(list(get_messages(response.wsgi_request))),
        )

        page = self.client.get(reverse("factory_dashboard"), {"batch": batch.pk})
        self.assertContains(
            page,
            f'<option value="{material.sku}" data-unit="kg">',
            html=False,
        )
        self.assertContains(page, 'data-consumption-unit', html=False)
        self.assertNotContains(page, 'name="material_name"')
        self.assertNotContains(page, 'placeholder="New material name (optional)"')
        self.assertNotContains(page, 'name="material_unit"')

    def test_wild_honey_is_bottled_in_its_own_section_as_three_production_outputs(self):
        factory_user = User.objects.create_user(
            username="honey-production-recorder",
            password="test-password-123",
            role=User.Role.FACTORY,
        )
        raw_honey = Product.objects.get(sku="RAW-RAW-HONEY")
        honey_jars = Product.objects.get(sku="PKG-HONEY-CANS")
        honey = Product.objects.get(sku="HONEY-SINGLE")
        full_package = Product.objects.get(sku="ED-PK-FULL")
        batch = ProductionBatch.objects.create(
            reference="HONEY-BOTTLING-BATCH",
            quantity=0,
            status=ProductionBatch.Status.ACTIVE,
            production_date=timezone.localdate(),
            created_by=self.manager,
        )
        self.client.force_login(factory_user)
        for material, quantity in ((raw_honey, 5), (honey_jars, 30)):
            purchase_response = self.client.post(
                reverse("record_purchase"),
                {
                    "supplier": "Honey production supplier",
                    "sku": material.sku,
                    "quantity": str(quantity),
                    "unit_cost": "1000",
                },
            )
            self.assertRedirects(purchase_response, reverse("factory_dashboard"))

        factory_page = self.client.get(
            reverse("factory_dashboard"),
            {"batch": batch.pk},
        )
        self.assertContains(factory_page, honey.name)
        self.assertContains(factory_page, "Kufungasha Wild Honey kwenye vikopo vya 800 g")
        self.assertNotContains(factory_page, "800 g/pakiti")
        self.assertContains(factory_page, "Kila kopo maalumu linajazwa asali na lina uzito wa 800 g")
        self.assertNotContains(factory_page, f'<option value="{full_package.sku}">', html=False)

        rejected_main_form = self.client.post(
            reverse("record_production"),
            {
                "batch_id": batch.pk,
                "sku": honey.sku,
                "quantity": "30",
                "production_request_key": str(uuid.uuid4()),
                "material_sku": [raw_honey.sku],
                "material_quantity": ["5"],
                "packaging_sku": [honey_jars.sku],
                "packaging_quantity": ["30"],
            },
        )
        self.assertEqual(batch.outputs.count(), 0)
        self.assertIn("separate honey bottling section", str(list(get_messages(rejected_main_form.wsgi_request))))

        honey_response = self.client.post(
            reverse("record_honey_bottling"),
            {
                "batch_id": batch.pk,
                "honey_quantity": "5",
                "jars_filled": "30",
                "production_date": timezone.localdate().isoformat(),
                "production_request_key": str(uuid.uuid4()),
            },
        )

        self.assertRedirects(
            honey_response,
            f"{reverse('factory_dashboard')}?batch={batch.pk}",
        )
        honey_output = batch.outputs.get(product=honey)
        self.assertEqual(honey_output.quantity, Decimal("30"))
        self.assertEqual(honey_output.consumptions.get(product=raw_honey).unit, "madumu")
        self.assertEqual(honey_output.consumptions.get(product=honey_jars).quantity, Decimal("30"))
        honey_stock = InventoryLedger.objects.filter(
            product=honey,
            location=self.factory_location,
            production_batch=batch,
        ).aggregate(total=Sum("quantity"))["total"]
        self.assertEqual(honey_stock, Decimal("30"))
        raw_honey_stock = InventoryLedger.objects.filter(
            product=raw_honey,
            location=self.factory_location,
        ).aggregate(total=Sum("quantity"))["total"]
        self.assertEqual(raw_honey_stock, Decimal("0"))

        self.client.force_login(self.manager)
        manager_page = self.client.get(reverse("manager_dashboard"), {"batch": batch.pk})
        self.assertEqual(manager_page.status_code, 200)
        bottling_consumptions = [
            row["consumption"]
            for row in manager_page.context["production_consumption_rows"]
            if row["consumption"].output_id == honey_output.pk
        ]
        self.assertSetEqual(
            {consumption.product_id for consumption in bottling_consumptions},
            {raw_honey.pk, honey_jars.pk},
        )
        self.assertContains(manager_page, "Mgawanyo wa Wild Honey")

        for material, quantity in ((raw_honey, "2"), (honey_jars, "3")):
            purchase_response = self.client.post(
                reverse("record_purchase"),
                {
                    "supplier": "CEO honey supplier",
                    "sku": material.sku,
                    "quantity": quantity,
                    "unit_cost": "1000",
                },
            )
            self.assertRedirects(purchase_response, reverse("manager_dashboard"))
        manager_bottling = self.client.post(
            reverse("record_honey_bottling"),
            {
                "batch_id": batch.pk,
                "honey_quantity": "2",
                "jars_filled": "3",
                "production_date": timezone.localdate().isoformat(),
                "production_request_key": str(uuid.uuid4()),
            },
        )
        self.assertRedirects(
            manager_bottling,
            f"{reverse('manager_dashboard')}?batch={batch.pk}",
        )
        self.assertEqual(
            batch.outputs.filter(product=honey).aggregate(total=Sum("quantity"))["total"],
            Decimal("33"),
        )

    def test_full_package_sale_deducts_one_of_each_component_from_selected_batch(self):
        package = Product.objects.get(sku="ED-PK-FULL")
        components = [
            Product.objects.get(sku=sku)
            for sku in ("ED-SINGLE", "PRESHA-SINGLE", "HONEY-SINGLE")
        ]
        batch = ProductionBatch.objects.create(
            reference="FULL-PACKAGE-SALE-BATCH",
            quantity=0,
            status=ProductionBatch.Status.ACTIVE,
            production_date=timezone.localdate(),
            created_by=self.manager,
        )
        branch_location = StockLocation.objects.get(
            location_type=StockLocation.LocationType.BRANCH_MWANZA,
        )
        for component in components:
            post_movement(
                product=component,
                location=branch_location,
                movement=InventoryLedger.Movement.TRANSFER_IN,
                quantity=3,
                reference=f"PACKAGE-SALE-OPENING-{component.sku}",
                production_batch=batch,
            )
            ProductionOutput.objects.create(
                batch=batch,
                product=component,
                quantity=3,
                production_date=timezone.localdate(),
                reference=f"PACKAGE-SALE-OUTPUT-{component.sku}",
                created_by=self.manager,
            )
        customer = Customer.objects.create(
            name="Full package customer",
            location=branch_location,
            active=True,
        )
        self.client.force_login(self.branch)

        response = self.client.post(
            reverse("record_sale"),
            {
                "customer_id": customer.pk,
                "sku": package.sku,
                "batch_id": batch.pk,
                "quantity": "2",
                "location_type": branch_location.location_type,
                "request_key": str(uuid.uuid4()),
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('mwanza_dashboard')}?batch={batch.pk}",
        )
        self.assertEqual(SaleItem.objects.get().product, package)
        for component in components:
            balance = InventoryLedger.objects.filter(
                product=component,
                location=branch_location,
                production_batch=batch,
            ).aggregate(total=Sum("quantity"))["total"]
            self.assertEqual(balance, Decimal("1"))
        self.assertFalse(
            InventoryLedger.objects.filter(
                product=package,
                location=branch_location,
                production_batch=batch,
            ).exists()
        )

    def test_recording_one_material_purchase_adds_it_to_store(self):
        material = Product.objects.create(
            name="Soya lishe",
            sku="PURCHASE-SOYA",
            category=Product.Category.RAW_MATERIAL,
            unit="kg",
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("record_purchase"),
            {
                "supplier": "Soko la Kariakoo",
                "sku": material.sku,
                "quantity": "10",
                "unit_cost": "5000",
            },
        )

        self.assertRedirects(response, reverse("manager_dashboard"))
        purchase = Purchase.objects.get()
        self.assertEqual(purchase.total_amount, Decimal("50000"))
        self.assertEqual(
            InventoryLedger.objects.filter(
                product=material,
                location=self.factory_location,
                movement=InventoryLedger.Movement.PURCHASE,
            ).aggregate(total=Sum("quantity"))["total"],
            Decimal("10"),
        )

    def test_new_batch_carries_forward_previous_stock_and_adds_its_purchases(self):
        material = Product.objects.create(
            name="Batch carryover material",
            sku="BATCH-CARRYOVER",
            category=Product.Category.RAW_MATERIAL,
            unit="kg",
        )
        self.client.force_login(self.manager)
        first_batch = ProductionBatch.objects.create(
            reference="CARRYOVER-BATCH-001",
            batch_number=1,
            quantity=0,
            status=ProductionBatch.Status.ACTIVE,
            production_date=timezone.localdate(),
            created_by=self.manager,
        )
        self.client.post(
            reverse("record_purchase"),
            {
                "batch_id": first_batch.pk,
                "supplier": "Carryover Supplier",
                "sku": material.sku,
                "quantity": "10",
                "unit_cost": "1000",
            },
        )
        post_movement(
            product=material,
            location=self.factory_location,
            movement=InventoryLedger.Movement.PRODUCTION_OUT,
            quantity="-6",
            reference="CARRYOVER-BATCH-001-USE",
            production_batch=first_batch,
        )
        second_batch = ProductionBatch.objects.create(
            reference="CARRYOVER-BATCH-002",
            batch_number=2,
            quantity=0,
            status=ProductionBatch.Status.ACTIVE,
            production_date=timezone.localdate(),
            created_by=self.manager,
        )
        purchase_response = self.client.post(
            reverse("record_purchase"),
            {
                "batch_id": second_batch.pk,
                "supplier": "Carryover Supplier",
                "sku": material.sku,
                "quantity": "3",
                "unit_cost": "1000",
            },
        )

        self.assertRedirects(
            purchase_response,
            f"{reverse('manager_dashboard')}?batch={second_batch.pk}",
        )
        second_batch_purchase = Purchase.objects.get(batch=second_batch)
        purchase_movement = InventoryLedger.objects.get(
            reference=second_batch_purchase.reference,
            product=material,
        )
        self.assertEqual(purchase_movement.production_batch, second_batch)
        ProductionConsumption.objects.create(
            batch=second_batch,
            product=material,
            quantity="2",
            unit=material.unit,
            reference="CARRYOVER-BATCH-002-USE",
        )
        post_movement(
            product=material,
            location=self.factory_location,
            movement=InventoryLedger.Movement.PRODUCTION_OUT,
            quantity="-2",
            reference="CARRYOVER-BATCH-002-USE",
            production_batch=second_batch,
        )

        response = self.client.get(
            reverse("manager_dashboard"),
            {"batch": second_batch.pk},
        )

        self.assertEqual(response.status_code, 200)
        material_row = next(
            row for row in response.context["material_inventory_rows"]
            if row["product"] == material
        )
        self.assertEqual(material_row["batch_opening_balance"], Decimal("4"))
        self.assertEqual(material_row["batch_purchase_quantity"], Decimal("3"))
        self.assertEqual(material_row["used_quantity"], Decimal("2"))
        self.assertEqual(material_row["batch_balance"], Decimal("5"))
        self.assertEqual(material_row["balance"], Decimal("5"))
        self.assertContains(response, "Mabaki batch ilipoanza")
        self.assertNotContains(response, "Jumla ya batch hii")

        factory_user = User.objects.create_user(
            username="carryover-factory",
            password="test-password-123",
            role=User.Role.FACTORY,
        )
        self.client.force_login(factory_user)
        factory_response = self.client.get(
            reverse("factory_dashboard"),
            {"batch": second_batch.pk},
        )
        self.assertEqual(factory_response.status_code, 200)
        factory_row = next(
            row for row in factory_response.context["material_inventory_rows"]
            if row["product"] == material
        )
        self.assertEqual(factory_row["batch_balance"], Decimal("5"))
        self.assertNotContains(factory_response, "Jumla iliyobaki kwa batch")

    def test_manager_can_register_new_material_or_packaging_from_purchase_form(self):
        self.client.force_login(self.manager)
        page = self.client.get(reverse("manager_dashboard"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'name="item_name"')
        self.assertContains(page, 'name="item_unit"')
        self.assertContains(page, 'name="category"')

        for name, category, unit, quantity in (
            ("New factory spice", Product.Category.RAW_MATERIAL, "kg", "4"),
            ("New factory pouch", Product.Category.PACKAGING, "piece", "250"),
        ):
            with self.subTest(category=category):
                self.client.force_login(self.manager)
                batch = ProductionBatch.objects.create(
                    reference=f"NEW-PRODUCT-{category}",
                    batch_number=Product.objects.count(),
                    quantity=0,
                    status=ProductionBatch.Status.ACTIVE,
                    production_date=timezone.localdate(),
                    created_by=self.manager,
                )
                response = self.client.post(
                    reverse("record_purchase"),
                    {
                        "batch_id": batch.pk,
                        "supplier": "New Inventory Supplier",
                        "item_name": name,
                        "item_unit": unit,
                        "category": category,
                        "quantity": quantity,
                        "unit_cost": "1000",
                        "actual_payment": "1000",
                    },
                )
                self.assertRedirects(
                    response,
                    f"{reverse('manager_dashboard')}?batch={batch.pk}",
                )
                product = Product.objects.get(name=name)
                self.assertEqual(product.category, category)
                self.assertEqual(product.unit, unit)
                self.assertEqual(
                    InventoryLedger.objects.filter(
                        product=product,
                        location=self.factory_location,
                    ).aggregate(total=Sum("quantity"))["total"],
                    Decimal(quantity),
                )
                manager_page = self.client.get(
                    reverse("manager_dashboard"),
                    {"batch": batch.pk},
                )
                factory_user = User.objects.create_user(
                    username=f"purchase-dropdown-{product.pk}",
                    password="test-password-123",
                    role=User.Role.FACTORY,
                )
                self.client.force_login(factory_user)
                factory_page = self.client.get(
                    reverse("factory_dashboard"),
                    {"batch": batch.pk},
                )
                if category == Product.Category.RAW_MATERIAL:
                    manager_production_rows = (
                        manager_page.content.decode().split('id="managerRawRows"', 1)[1]
                        .split('id="managerPackagingRows"', 1)[0]
                    )
                    factory_production_rows = (
                        factory_page.content.decode().split('id="factoryRawRows"', 1)[1]
                        .split('id="factoryPackagingRows"', 1)[0]
                    )
                else:
                    manager_production_rows = (
                        manager_page.content.decode().split('id="managerPackagingRows"', 1)[1]
                        .split("</form>", 1)[0]
                    )
                    factory_production_rows = (
                        factory_page.content.decode().split('id="factoryPackagingRows"', 1)[1]
                        .split("</form>", 1)[0]
                    )
                self.assertIn(f'<option value="{product.sku}"', manager_production_rows)
                self.assertIn(f'<option value="{product.sku}"', factory_production_rows)
                self.assertIn(f'data-unit="{unit}"', manager_production_rows)
                self.assertIn(f'data-unit="{unit}"', factory_production_rows)
                self.assertIn("data-consumption-unit", manager_production_rows)
                self.assertIn("data-consumption-unit", factory_production_rows)
                self.assertTrue(Product.objects.get(pk=product.pk).active)

    def test_receiving_existing_inactive_material_reactivates_it_for_production(self):
        material = Product.objects.create(
            name="Reactivated purchase material",
            sku="REACTIVATED-PURCHASE-MATERIAL",
            category=Product.Category.RAW_MATERIAL,
            unit="kg",
            active=False,
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("record_purchase"),
            {
                "supplier": "Reactivation Supplier",
                "item_name": material.name,
                "item_unit": material.unit,
                "category": Product.Category.RAW_MATERIAL,
                "quantity": "5",
                "unit_cost": "1000",
            },
        )

        self.assertRedirects(response, reverse("manager_dashboard"))
        material.refresh_from_db()
        self.assertTrue(material.active)
        manager_page = self.client.get(reverse("manager_dashboard"))
        manager_production_rows = (
            manager_page.content.decode().split('id="managerRawRows"', 1)[1]
            .split('id="managerPackagingRows"', 1)[0]
        )
        self.assertIn(f'<option value="{material.sku}"', manager_production_rows)

    def test_manager_can_receive_saved_draft_purchase_to_store_once(self):
        material = Product.objects.create(
            name="Mbegu za maboga",
            sku="PUMPKIN-SEEDS-DRAFT",
            category=Product.Category.RAW_MATERIAL,
            unit="kg",
        )
        supplier = Supplier.objects.create(name="Muuzaji wa mbegu")
        purchase = Purchase.objects.create(
            reference="PO-DRAFT-PUMPKIN",
            supplier=supplier,
            purchase_date=timezone.localdate(),
            total_amount="15000",
            created_by=self.manager,
        )
        PurchaseItem.objects.create(
            purchase=purchase,
            product=material,
            quantity="5",
            unit_cost="3000",
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("receive_saved_purchase", args=[purchase.pk])
        )

        self.assertRedirects(response, reverse("manager_dashboard"))
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, Purchase.Status.RECEIVED)
        self.assertEqual(
            InventoryLedger.objects.filter(
                product=material,
                location=self.factory_location,
                movement=InventoryLedger.Movement.PURCHASE,
            ).aggregate(total=Sum("quantity"))["total"],
            Decimal("5"),
        )

        self.client.post(reverse("receive_saved_purchase", args=[purchase.pk]))
        self.assertEqual(
            InventoryLedger.objects.filter(
                product=material,
                location=self.factory_location,
                movement=InventoryLedger.Movement.PURCHASE,
            ).count(),
            1,
        )

    def test_failed_production_does_not_leave_a_planned_batch_or_partial_changes(self):
        product = Product.objects.create(
            name="Effective Diet",
            sku="FAILED-BATCH-PRODUCT",
            category=Product.Category.FINISHED_GOOD,
        )
        material = Product.objects.create(
            name="Hiliki",
            sku="FAILED-BATCH-MATERIAL",
            category=Product.Category.RAW_MATERIAL,
            unit="kg",
        )
        batch = ProductionBatch.objects.create(
            reference="FAILED-OUTPUT-BATCH",
            quantity=0,
            batch_number=1,
            status=ProductionBatch.Status.ACTIVE,
            production_date=timezone.localdate(),
            created_by=self.manager,
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("record_production"),
            {
                "sku": product.sku,
                "quantity": "300",
                "batch_id": batch.pk,
                "material_sku": [material.sku],
                "material_quantity": ["200"],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProductionBatch.objects.count(), 1)
        self.assertEqual(batch.outputs.count(), 0)
        self.assertFalse(Recipe.objects.filter(product=product).exists())
        self.assertEqual(
            InventoryLedger.objects.filter(location=self.factory_location).count(),
            0,
        )
        self.assertIn(
            "Hiliki ipo 0 kg kwenye Factory; umeomba 200 kg",
            str(list(get_messages(response.wsgi_request))),
        )

    def test_customer_records_belong_to_the_branch_that_added_them(self):
        self.client.force_login(self.branch)

        response = self.client.post(
            reverse("record_customer"),
            {
                "name": "Branch Customer",
                "phone": "255700000001",
                "diagnosis": "Flu",
                "short_description": "Mild symptoms reported",
            },
        )

        self.assertRedirects(response, reverse("mwanza_dashboard"))
        customer = Customer.objects.get(name="Branch Customer")
        self.assertEqual(customer.diagnosis, "Flu")
        self.assertEqual(customer.short_description, "Mild symptoms reported")
        self.assertEqual(customer.email, "")
        self.assertEqual(customer.visits.count(), 1)
        self.assertEqual(
            customer.visits.get().visit_type,
            CustomerVisit.VisitType.NEW_CUSTOMER,
        )
        self.assertEqual(
            customer.location.location_type,
            StockLocation.LocationType.BRANCH_MWANZA,
        )

    def test_existing_customer_registration_records_a_return_visit(self):
        self.client.force_login(self.branch)
        payload = {
            "name": "Returning Customer",
            "phone": "0712345678",
        }

        self.client.post(reverse("record_customer"), payload)
        response = self.client.post(
            reverse("record_customer"),
            {**payload, "phone": "+255 712 345 678"},
            follow=True,
        )

        customer = Customer.objects.get(name="Returning Customer")
        self.assertEqual(Customer.objects.filter(location=customer.location).count(), 1)
        self.assertEqual(customer.visits.count(), 2)
        self.assertEqual(
            list(customer.visits.order_by("visited_at").values_list("visit_type", flat=True)),
            [
                CustomerVisit.VisitType.NEW_CUSTOMER,
                CustomerVisit.VisitType.RETURNING_CUSTOMER,
            ],
        )
        self.assertContains(response, "returned again today")
        dashboard_response = self.client.get(reverse("mwanza_dashboard"))
        annotated_customer = dashboard_response.context["branch_customers"].get(pk=customer.pk)
        self.assertEqual(annotated_customer.branch_visit_count, 2)

    def test_visitor_history_is_linked_when_they_later_register_as_customer(self):
        self.client.force_login(self.branch)
        visitor_response = self.client.post(
            reverse("record_branch_visit"),
            {
                "visit_mode": "visitor",
                "visitor_name": "Asha Mushi",
                "visitor_phone": "0712345678",
                "visit_type": CustomerVisit.VisitType.GOVERNMENT_OFFICIAL,
            },
        )
        self.assertRedirects(
            visitor_response,
            f"{reverse('mwanza_dashboard')}?view=visitors",
        )

        response = self.client.post(
            reverse("record_customer"),
            {
                "name": "Asha Mushi",
                "phone": "+255 712 345 678",
            },
            follow=True,
        )

        customer = Customer.objects.get(name="Asha Mushi")
        earlier_visit = CustomerVisit.objects.get(
            visit_type=CustomerVisit.VisitType.GOVERNMENT_OFFICIAL,
        )
        self.assertEqual(earlier_visit.customer, customer)
        self.assertEqual(customer.visits.count(), 2)
        self.assertContains(response, "Linked 1 earlier visitor record")

    def test_repeat_visitors_are_recognized_from_their_phone_number(self):
        self.client.force_login(self.branch)
        payload = {
            "visit_mode": "visitor",
            "visitor_name": "Guest Visitor",
            "visitor_phone": "0712345678",
            "visit_type": CustomerVisit.VisitType.MANAGEMENT_GUEST,
        }
        self.client.post(reverse("record_branch_visit"), payload)

        response = self.client.post(
            reverse("record_branch_visit"),
            {**payload, "visitor_name": "Guest Visitor Again"},
            follow=True,
        )

        self.assertEqual(CustomerVisit.objects.count(), 2)
        self.assertContains(response, "Visitor returned")
        self.assertContains(response, "1 earlier visitor record")

    def test_visitor_with_existing_customer_phone_is_logged_as_returning_customer(self):
        location = StockLocation.objects.get(
            location_type=StockLocation.LocationType.BRANCH_MWANZA,
        )
        customer = Customer.objects.create(
            name="Known Customer",
            phone="0712345678",
            location=location,
        )
        self.client.force_login(self.branch)

        response = self.client.post(
            reverse("record_branch_visit"),
            {
                "visit_mode": "visitor",
                "visitor_name": customer.name,
                "visitor_phone": "+255712345678",
                "visit_type": CustomerVisit.VisitType.CUSTOMER_INQUIRY,
            },
            follow=True,
        )

        visit = CustomerVisit.objects.get()
        self.assertEqual(visit.customer, customer)
        self.assertEqual(visit.visit_type, CustomerVisit.VisitType.RETURNING_CUSTOMER)
        self.assertContains(response, "already exists as a customer")

    def test_branch_delivery_records_parcels_and_allows_status_updates(self):
        self.client.force_login(self.branch)

        response = self.client.post(
            reverse("record_branch_delivery"),
            {
                "recipient_name": "Parcel Recipient",
                "recipient_phone": "0712345678",
                "destination": "Mwanza CBD",
                "parcel_count": "3",
                "delivery_date": timezone.localdate().isoformat(),
            },
        )

        delivery = BranchDelivery.objects.get()
        self.assertEqual(delivery.parcel_count, 3)
        self.assertEqual(delivery.status, BranchDelivery.Status.PENDING)
        self.assertRedirects(
            response,
            f"{reverse('mwanza_dashboard')}?view=deliveries",
        )
        update_response = self.client.post(
            reverse("update_branch_delivery_status", args=[delivery.pk]),
            {"status": BranchDelivery.Status.DELIVERED},
        )
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, BranchDelivery.Status.DELIVERED)
        self.assertRedirects(
            update_response,
            f"{reverse('mwanza_dashboard')}?view=deliveries",
        )

    def test_branch_recent_activity_combines_visits_calls_expenses_and_deliveries(self):
        location = StockLocation.objects.get(
            location_type=StockLocation.LocationType.BRANCH_MWANZA,
        )
        customer = Customer.objects.create(
            name="Activity Customer",
            location=location,
            phone="0712345678",
        )
        CustomerVisit.objects.create(
            customer=customer,
            location=location,
            visit_type=CustomerVisit.VisitType.RETURNING_CUSTOMER,
            visitor_name=customer.name,
            visitor_phone=customer.phone,
            recorded_by=self.branch,
        )
        CustomerCall.objects.create(
            customer=customer,
            location=location,
            called_by=self.branch,
            direction=CustomerCall.Direction.OUTBOUND,
            call_type=CustomerCall.CallType.FOLLOW_UP,
            outcome="Customer reached",
        )
        BranchExpense.objects.create(
            location=location.location_type,
            category="Transport",
            amount=Decimal("12000"),
            expense_date=timezone.localdate(),
            recorded_by=self.branch,
        )
        BranchDelivery.objects.create(
            location=location,
            recipient_name="Activity Recipient",
            destination="Mwanza CBD",
            parcel_count=2,
            recorded_by=self.branch,
        )
        self.client.force_login(self.branch)

        response = self.client.get(reverse("mwanza_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="workspaceConfirmDialog"')
        activity_kinds = {item["kind"] for item in response.context["recent_activity"]}
        self.assertTrue(
            {"Customer / visitor", "Customer call", "Expense", "Delivery"}.issubset(activity_kinds)
        )
        for action in (
            "New customer",
            "Record sale",
            "Customer check-in / visitor",
            "Delivery / parcels",
            "Record call",
            "Record expense",
            "Incoming transfers",
            "Daily report",
        ):
            self.assertContains(response, action)

    def test_branch_customer_directory_only_shows_its_own_customers(self):
        mwanza_customer = Customer.objects.create(
            name="Mwanza Only",
            location=StockLocation.objects.get(
                location_type=StockLocation.LocationType.BRANCH_MWANZA
            ),
        )
        Customer.objects.create(name="Dar Only", location=self.dar_location)
        self.client.force_login(self.branch)

        response = self.client.get(reverse("mwanza_dashboard"))

        self.assertContains(response, mwanza_customer.name)
        self.assertContains(response, f'value="{mwanza_customer.pk}"')
        self.assertNotContains(response, "Dar Only")

    def test_pos_requires_a_saved_customer_from_its_own_branch_and_rolls_back(self):
        mwanza_location = StockLocation.objects.get(
            location_type=StockLocation.LocationType.BRANCH_MWANZA
        )
        customer = Customer.objects.create(
            name="Mwanza POS Customer",
            location=mwanza_location,
        )
        dar_customer = Customer.objects.create(
            name="Dar POS Customer",
            location=self.dar_location,
        )
        product = Product.objects.create(
            name="Effective Diet POS Product",
            sku="POS-001",
            unit_price="120",
            category=Product.Category.FINISHED_GOOD,
        )
        recipe = Recipe.objects.create(product=product)
        batch = ProductionBatch.objects.create(
            reference="POS-BATCH",
            recipe=recipe,
            quantity=2,
            batch_number=1,
            status=ProductionBatch.Status.COMPLETED,
            production_date=timezone.localdate(),
            created_by=self.manager,
        )
        post_movement(
            product=product,
            location=mwanza_location,
            movement=InventoryLedger.Movement.PURCHASE,
            quantity=2,
            reference="POS-OPENING-STOCK",
            production_batch=batch,
        )
        self.client.force_login(self.branch)

        payload = {
            "customer_id": "",
            "sku": product.sku,
            "batch_id": batch.pk,
            "quantity": "1",
            "unit_price": "1",
        }
        self.client.post(reverse("record_sale"), payload)
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(SaleItem.objects.count(), 0)
        self.assertEqual(InventoryLedger.objects.count(), 1)

        payload["customer_id"] = dar_customer.pk
        self.client.post(reverse("record_sale"), payload)
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(SaleItem.objects.count(), 0)
        self.assertEqual(InventoryLedger.objects.count(), 1)

        payload["customer_id"] = customer.pk
        payload["quantity"] = "3"
        self.client.post(reverse("record_sale"), payload)
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(SaleItem.objects.count(), 0)
        self.assertEqual(InventoryLedger.objects.count(), 1)

        payload["quantity"] = "1"
        self.client.post(reverse("record_sale"), payload)
        sale = Sale.objects.get()
        item = SaleItem.objects.get(sale=sale)
        self.assertEqual(sale.customer, customer)
        self.assertEqual(sale.location, mwanza_location)
        self.assertEqual(sale.total_amount, Decimal("120.00"))
        self.assertEqual(item.unit_price, Decimal("120.00"))
        self.assertEqual(InventoryLedger.objects.count(), 2)

    def test_customer_calls_require_a_saved_customer_from_the_same_branch(self):
        self.client.force_login(self.branch)
        response = self.client.post(
            reverse("record_call"),
            {
                "customer": "Unregistered customer",
                "direction": CustomerCall.Direction.INBOUND,
                "outcome": "Instruction",
            },
        )

        self.assertRedirects(response, reverse("mwanza_dashboard"))
        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(CustomerCall.objects.count(), 0)

    def test_customer_call_records_type_outcome_and_notes(self):
        location = StockLocation.objects.get(
            location_type=StockLocation.LocationType.BRANCH_MWANZA
        )
        customer = Customer.objects.create(name="Call Customer", location=location)
        self.client.force_login(self.branch)

        response = self.client.post(
            reverse("record_call"),
            {
                "customer_id": customer.pk,
                "direction": CustomerCall.Direction.OUTBOUND,
                "call_type": CustomerCall.CallType.INSTRUCTION,
                "outcome": "Mteja ameelewa maelekezo",
                "notes": "Atatumia bidhaa baada ya chakula",
                "follow_up": "",
            },
        )

        self.assertRedirects(response, reverse("mwanza_dashboard"))
        call = CustomerCall.objects.get()
        self.assertEqual(call.customer, customer)
        self.assertEqual(call.direction, CustomerCall.Direction.OUTBOUND)
        self.assertEqual(call.call_type, CustomerCall.CallType.INSTRUCTION)
        self.assertEqual(call.outcome, "Mteja ameelewa maelekezo")
        self.assertEqual(call.notes, "Atatumia bidhaa baada ya chakula")
        dashboard_response = self.client.get(reverse("mwanza_dashboard"))
        self.assertContains(dashboard_response, "Mwelekeo wa simu")
        self.assertContains(dashboard_response, "Tumepigiwa na mteja")
        self.assertContains(dashboard_response, "Tumempigia mteja")

    def test_customer_call_rejects_an_unknown_call_type(self):
        location = StockLocation.objects.get(
            location_type=StockLocation.LocationType.BRANCH_MWANZA
        )
        customer = Customer.objects.create(name="Call Customer", location=location)
        self.client.force_login(self.branch)

        response = self.client.post(
            reverse("record_call"),
            {
                "customer_id": customer.pk,
                "direction": CustomerCall.Direction.INBOUND,
                "call_type": "UNKNOWN",
                "outcome": "Mteja amepatikana",
            },
        )

        self.assertRedirects(response, reverse("mwanza_dashboard"))
        self.assertEqual(CustomerCall.objects.count(), 0)

    def test_customer_call_requires_a_direction(self):
        location = StockLocation.objects.get(
            location_type=StockLocation.LocationType.BRANCH_MWANZA
        )
        customer = Customer.objects.create(name="Call Customer", location=location)
        self.client.force_login(self.branch)

        response = self.client.post(
            reverse("record_call"),
            {
                "customer_id": customer.pk,
                "call_type": CustomerCall.CallType.FOLLOW_UP,
                "outcome": "Mteja amepatikana",
            },
            follow=True,
        )

        self.assertEqual(CustomerCall.objects.count(), 0)
        self.assertContains(response, "Chagua kama tumepigiwa au tumempigia mteja.")

    def test_prospective_caller_is_saved_without_customer_and_linked_when_registered(self):
        location = StockLocation.objects.get(
            location_type=StockLocation.LocationType.BRANCH_MWANZA
        )
        self.client.force_login(self.branch)

        call_response = self.client.post(
            reverse("record_call"),
            {
                "contact_mode": "caller",
                "caller_name": "Asha Mushi",
                "caller_phone": "0712345678",
                "direction": CustomerCall.Direction.INBOUND,
                "call_type": CustomerCall.CallType.INSTRUCTION,
                "outcome": "Ameuliza kuhusu matumizi ya bidhaa",
                "notes": "Atakuja ofisini wiki ijayo",
                "follow_up": "",
            },
        )

        self.assertRedirects(call_response, reverse("mwanza_dashboard"))
        self.assertEqual(Customer.objects.count(), 0)
        call = CustomerCall.objects.get()
        self.assertIsNone(call.customer)
        self.assertEqual(call.location, location)
        self.assertEqual(call.contact_name, "Asha Mushi")
        self.assertEqual(call.caller_phone, "0712345678")

        self.client.post(
            reverse("record_customer"),
            {
                "name": "Asha Mushi",
                "phone": "0712345678",
            },
        )

        customer = Customer.objects.get(name="Asha Mushi", location=location)
        call.refresh_from_db()
        self.assertEqual(call.customer, customer)

    def test_two_individual_dispatches_reduce_store_by_combined_quantity(self):
        factory_user = User.objects.create_user(
            username="individual-dispatch",
            password="test-password-123",
            role=User.Role.FACTORY,
        )
        product = Product.objects.create(
            name="Effective Diet Individual Dispatch Product",
            sku="INDIVIDUAL-DISPATCH",
            category=Product.Category.FINISHED_GOOD,
        )
        recipe = Recipe.objects.create(product=product)
        batch = ProductionBatch.objects.create(
            reference="INDIVIDUAL-DISPATCH-BATCH",
            recipe=recipe,
            quantity=2000,
            batch_number=1,
            status=ProductionBatch.Status.COMPLETED,
            production_date=timezone.localdate(),
            created_by=factory_user,
        )
        post_movement(
            product=product,
            location=self.factory_location,
            movement=InventoryLedger.Movement.PRODUCTION_IN,
            quantity=2000,
            reference="PRODUCTION-2000",
            production_batch=batch,
        )
        self.client.force_login(factory_user)

        first = self.client.post(
            reverse("record_dispatch"),
            {"sku": product.sku, "batch_id": batch.pk, "quantity": "300", "destination": "MWANZA"},
        )
        second = self.client.post(
            reverse("record_dispatch"),
            {"sku": product.sku, "batch_id": batch.pk, "quantity": "400", "destination": "DAR"},
        )

        self.assertRedirects(first, f"{reverse('factory_dashboard')}?batch={batch.pk}")
        self.assertRedirects(second, f"{reverse('factory_dashboard')}?batch={batch.pk}")
        store_balance = InventoryLedger.objects.filter(
            product=product,
            location=self.factory_location,
        ).aggregate(total=Sum("quantity"))["total"]
        self.assertEqual(store_balance, Decimal("1300"))

    def test_dispatch_decreases_store_stock_and_failed_dispatch_leaves_no_transfer(self):
        factory_user = User.objects.create_user(
            username="dispatch-factory",
            password="test-password-123",
            role=User.Role.FACTORY,
        )
        product = Product.objects.create(
            name="Effective Diet Dispatch Product",
            sku="DISPATCH-001",
            category=Product.Category.FINISHED_GOOD,
        )
        recipe = Recipe.objects.create(product=product)
        batch = ProductionBatch.objects.create(
            reference="DISPATCH-BATCH",
            recipe=recipe,
            quantity=10,
            batch_number=1,
            status=ProductionBatch.Status.COMPLETED,
            production_date=timezone.localdate(),
            created_by=factory_user,
        )
        post_movement(
            product=product,
            location=self.factory_location,
            movement=InventoryLedger.Movement.PRODUCTION_OUT,
            quantity=10,
            reference="DISPATCH-OPENING-STOCK",
            production_batch=batch,
        )
        self.client.force_login(factory_user)

        response = self.client.post(
            reverse("record_dispatch"),
            {"sku": product.sku, "batch_id": batch.pk, "quantity": "4", "destination": "DAR"},
        )

        self.assertRedirects(response, f"{reverse('factory_dashboard')}?batch={batch.pk}")
        self.assertEqual(
            InventoryLedger.objects.filter(
                product=product,
                location=self.factory_location,
            ).aggregate(total=Sum("quantity"))["total"],
            Decimal("6"),
        )
        self.assertEqual(
            InventoryLedger.objects.filter(
                product=product,
                location=self.dar_location,
            ).count(),
            0,
        )
        transfer = Transfer.objects.get()
        self.assertEqual(transfer.destination, self.dar_location)
        self.assertEqual(TransferItem.objects.get(transfer=transfer).quantity_sent, Decimal("4"))
        self.assertTrue(
            InventoryLedger.objects.filter(
                reference=transfer.reference,
                location=self.factory_location,
                movement=InventoryLedger.Movement.TRANSFER_OUT,
                quantity=Decimal("-4"),
            ).exists()
        )

        response = self.client.post(
            reverse("record_dispatch"),
            {"sku": product.sku, "batch_id": batch.pk, "quantity": "20", "destination": "MWANZA"},
        )

        self.assertRedirects(response, f"{reverse('factory_dashboard')}?batch={batch.pk}")
        self.assertEqual(Transfer.objects.count(), 1)
        self.assertEqual(TransferItem.objects.count(), 1)
        self.assertIn(
            "Dispatch Product ipo 6 unit kwenye Factory; umeomba 20 unit",
            str(list(get_messages(response.wsgi_request))),
        )

    def test_manager_customer_activity_is_scoped_to_each_branch(self):
        mwanza_location = StockLocation.objects.get(
            location_type=StockLocation.LocationType.BRANCH_MWANZA
        )
        mwanza_customer = Customer.objects.create(
            name="Mwanza Activity Customer",
            location=mwanza_location,
            address="Mwanza CBD",
        )
        mwanza_second_customer = Customer.objects.create(
            name="Mwanza Second Activity Customer",
            location=mwanza_location,
            address="Nyamagana",
        )
        dar_customer = Customer.objects.create(
            name="Dar Activity Customer",
            location=self.dar_location,
            address="Kinondoni",
        )
        dar_user = User.objects.create_user(
            username="activity-dar",
            password="test-password-123",
            role=User.Role.BRANCH_DAR,
        )
        CustomerCall.objects.create(
            customer=mwanza_customer,
            called_by=self.branch,
            outcome="Instruction",
            follow_up_date=timezone.localdate(),
        )
        CustomerCall.objects.create(
            customer=mwanza_second_customer,
            called_by=self.branch,
            outcome="Instruction",
        )
        CustomerCall.objects.create(
            customer=dar_customer,
            called_by=dar_user,
            outcome="Compliance",
            follow_up_date=timezone.localdate(),
        )
        self.client.force_login(self.manager)

        response = self.client.get(reverse("manager_dashboard"))

        mwanza_data = response.context["mwanza_data"]
        dar_data = response.context["dar_data"]
        self.assertEqual(mwanza_data["customer_count"], 2)
        self.assertEqual(mwanza_data["customer_call_count"], 2)
        self.assertEqual(mwanza_data["open_followup_count"], 1)
        self.assertEqual(mwanza_data["customer_areas"], ["Mwanza CBD", "Nyamagana"])
        self.assertEqual(dar_data["customer_count"], 1)
        self.assertEqual(dar_data["customer_call_count"], 1)
        self.assertEqual(dar_data["open_followup_count"], 1)
        self.assertEqual(dar_data["customer_areas"], ["Kinondoni"])
        self.assertContains(response, "Mwanza CBD")
        self.assertContains(response, "Nyamagana")
        self.assertContains(response, "Kinondoni")

    def test_branch_can_submit_daily_report(self):
        product = Product.objects.create(
            name="Effective Diet Report Product",
            sku="REPORT-EFFECTIVE-DIET",
            category=Product.Category.FINISHED_GOOD,
        )
        batch = ProductionBatch.objects.create(
            reference="REPORT-BATCH",
            recipe=Recipe.objects.create(product=product),
            quantity=50,
            batch_number=1,
            status=ProductionBatch.Status.COMPLETED,
            production_date=timezone.localdate(),
            created_by=self.manager,
        )
        mwanza_location = StockLocation.objects.get(
            location_type=StockLocation.LocationType.BRANCH_MWANZA,
        )
        post_movement(
            product=product,
            location=mwanza_location,
            movement=InventoryLedger.Movement.TRANSFER_IN,
            quantity=50,
            reference="REPORT-BATCH-TRANSFER",
            production_batch=batch,
        )
        report_customer = Customer.objects.create(
            name="Report Customer",
            location=mwanza_location,
        )
        for visit_type in (
            CustomerVisit.VisitType.NEW_CUSTOMER,
            CustomerVisit.VisitType.RETURNING_CUSTOMER,
            CustomerVisit.VisitType.CUSTOMER_INQUIRY,
        ):
            CustomerVisit.objects.create(
                customer=report_customer if visit_type != CustomerVisit.VisitType.CUSTOMER_INQUIRY else None,
                location=mwanza_location,
                visit_type=visit_type,
                visitor_name=report_customer.name,
                recorded_by=self.branch,
            )
        BranchDelivery.objects.create(
            location=mwanza_location,
            recipient_name="Report Recipient",
            destination="Mwanza CBD",
            parcel_count=3,
            recorded_by=self.branch,
        )
        self.client.force_login(self.branch)
        response = self.client.post(
            reverse("submit_daily_report"),
            {
                "batch_id": batch.pk,
                "units_sold": "12",
                "closing_balance": "40",
                "loss_quantity": "2",
                "total_customers": "15",
                "new_customers": "5",
                "returning_customers": "10",
                "visitors": "8",
                "deliveries": "3",
                "parcels": "2",
                "instruction_calls": "4",
                "compliance_calls": "3",
                "followup_calls": "2",
                "customer_addresses": "Mwanza CBD",
            },
        )
        self.assertRedirects(response, f"{reverse('mwanza_dashboard')}?batch={batch.pk}")
        report = BranchDailyReport.objects.get(
            location=StockLocation.LocationType.BRANCH_MWANZA,
        )
        self.assertEqual(report.units_sold, 12)
        self.assertEqual(report.status, BranchDailyReport.Status.SUBMITTED)
        self.assertEqual(report.total_customers, 2)
        self.assertEqual(report.new_customers, 1)
        self.assertEqual(report.returning_customers, 1)
        self.assertEqual(report.visitors, 1)
        self.assertEqual(report.deliveries, 1)
        self.assertEqual(report.parcels, 3)

        response = self.client.post(
            reverse("submit_daily_report"),
            {
                "batch_id": batch.pk,
                "units_sold": "99",
                "closing_balance": "40",
                "loss_quantity": "2",
            },
        )
        self.assertRedirects(response, f"{reverse('mwanza_dashboard')}?batch={batch.pk}")
        report.refresh_from_db()
        self.assertEqual(report.units_sold, 12)

        second_product = Product.objects.create(
            name="Pressure Masala Report Product",
            sku="REPORT-PRESSURE-MASALA",
            category=Product.Category.FINISHED_GOOD,
        )
        second_batch = ProductionBatch.objects.create(
            reference="REPORT-BATCH-SECOND",
            recipe=Recipe.objects.create(product=second_product),
            quantity=30,
            batch_number=2,
            status=ProductionBatch.Status.COMPLETED,
            production_date=timezone.localdate(),
            created_by=self.manager,
        )
        post_movement(
            product=second_product,
            location=mwanza_location,
            movement=InventoryLedger.Movement.TRANSFER_IN,
            quantity=30,
            reference="REPORT-BATCH-SECOND-TRANSFER",
            production_batch=second_batch,
        )
        response = self.client.post(
            reverse("submit_daily_report"),
            {
                "batch_id": second_batch.pk,
                "units_sold": "3",
                "closing_balance": "27",
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('mwanza_dashboard')}?batch={second_batch.pk}",
        )
        self.assertEqual(
            BranchDailyReport.objects.filter(
                location=StockLocation.LocationType.BRANCH_MWANZA,
            ).count(),
            2,
        )

    def test_manager_can_approve_submitted_report(self):
        report = BranchDailyReport.objects.create(
            location=StockLocation.LocationType.BRANCH_MWANZA,
            report_date="2026-11-21",
            submitted_by=self.branch,
        )
        self.client.force_login(self.manager)
        response = self.client.post(reverse("approve_daily_report", args=[report.pk]))
        self.assertRedirects(response, reverse("manager_dashboard"))
        report.refresh_from_db()
        self.assertEqual(report.status, BranchDailyReport.Status.APPROVED)
        self.assertEqual(report.approved_by, self.manager)

    def test_manager_sales_export_is_csv(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("export_manager_report"), {"type": "sales"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("attachment;", response["Content-Disposition"])

    def test_csv_export_neutralizes_spreadsheet_formulas(self):
        response = csv_response(
            "test.csv",
            ["=Header"],
            [["=1+1", "  @SUM(1,1)", -5]],
        )

        rows = list(csv.reader(response.content.decode("utf-8").splitlines()))
        self.assertEqual(rows[0], ["'=Header"])
        self.assertEqual(rows[1], ["'=1+1", "'  @SUM(1,1)", "-5"])

    def test_service_worker_never_caches_navigation_responses(self):
        response = self.client.get(reverse("service-worker"))
        script = response.content.decode("utf-8")
        navigation_handler = script.split(
            'if (request.mode === "navigate"',
            1,
        )[1].split('self.addEventListener("push"', 1)[0]

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("PAGE_CACHE", script)
        self.assertNotIn("cache.put", navigation_handler)

    def test_catalog_contains_all_categories_and_prices(self):
        self.assertTrue(
            Product.objects.filter(
                name="Effective Diet Full Package",
                unit="pcs",
                unit_price="100000",
                category=Product.Category.FINISHED_GOOD,
            ).exists()
        )
        self.assertTrue(Product.objects.filter(name="Effective Diet Pekee", unit="pcs", unit_price="65000").exists())
        self.assertTrue(Product.objects.filter(name="Presha Masala Pekee", unit="pcs", unit_price="25000").exists())
        self.assertTrue(Product.objects.filter(name="Wild Honey / Asali Pekee", unit="vikopo", unit_price="15000").exists())
        self.assertEqual(
            Product.objects.filter(category=Product.Category.RAW_MATERIAL).count(),
            9,
        )
        self.assertEqual(
            Product.objects.filter(category=Product.Category.PACKAGING).count(),
            7,
        )
        self.assertEqual(
            Product.objects.filter(category=Product.Category.FINISHED_GOOD).count(),
            4,
        )
        expected_units = {
            "RAW-SOYA": "kg",
            "RAW-RAW-HONEY": "madumu",
            "PKG-ED-BAGS": "pcs",
            "ED-PK-FULL": "pcs",
            "HONEY-SINGLE": "vikopo",
        }
        for sku, unit in expected_units.items():
            with self.subTest(sku=sku):
                self.assertEqual(Product.objects.get(sku=sku).unit, unit)
