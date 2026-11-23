import csv
from decimal import Decimal

from django.contrib.messages import get_messages
from django.db.models import Sum
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.customers.models import BranchDailyReport, Customer, CustomerCall
from apps.distribution.models import Transfer, TransferItem
from apps.inventory.models import InventoryLedger, Product, StockLocation
from apps.production.models import ProductionBatch, Recipe
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
        self.assertNotContains(response, "figures in this prototype are illustrative")

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
                self.assertContains(response, "Customer calls &amp; follow-ups")
                self.assertContains(response, "Recent branch activity")
                self.assertContains(response, "branch-account-role")
                for section in ("overview", "transfers", "sales", "customers", "expenses", "calls", "report"):
                    self.assertContains(response, f'data-branch-view="{section}"')
                self.assertContains(response, "No sales recorded today")
                self.assertNotContains(response, "450K")
                self.assertContains(response, "/operations/reports/submit/")
                self.assertContains(response, "Submit daily report")
                self.client.logout()

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

        self.assertRedirects(response, reverse("mwanza_dashboard"))
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
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("record_production"),
            {
                "sku": product.sku,
                "quantity": "300",
                "material_sku": [material.sku],
                "material_quantity": ["200"],
            },
        )

        self.assertRedirects(response, reverse("manager_dashboard"))
        self.assertEqual(ProductionBatch.objects.count(), 0)
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
            {"name": "Branch Customer", "phone": "255700000001"},
        )

        self.assertRedirects(response, reverse("mwanza_dashboard"))
        customer = Customer.objects.get(name="Branch Customer")
        self.assertEqual(
            customer.location.location_type,
            StockLocation.LocationType.BRANCH_MWANZA,
        )

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
            name="POS Product",
            sku="POS-001",
            unit_price="120",
            category=Product.Category.FINISHED_GOOD,
        )
        post_movement(
            product=product,
            location=mwanza_location,
            movement=InventoryLedger.Movement.PURCHASE,
            quantity=2,
            reference="POS-OPENING-STOCK",
        )
        self.client.force_login(self.branch)

        payload = {
            "customer_id": "",
            "sku": product.sku,
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
            {"customer": "Unregistered customer", "outcome": "Instruction"},
        )

        self.assertRedirects(response, reverse("mwanza_dashboard"))
        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(CustomerCall.objects.count(), 0)

    def test_two_individual_dispatches_reduce_store_by_combined_quantity(self):
        factory_user = User.objects.create_user(
            username="individual-dispatch",
            password="test-password-123",
            role=User.Role.FACTORY,
        )
        product = Product.objects.create(
            name="Individual Dispatch Product",
            sku="INDIVIDUAL-DISPATCH",
            category=Product.Category.FINISHED_GOOD,
        )
        post_movement(
            product=product,
            location=self.factory_location,
            movement=InventoryLedger.Movement.PRODUCTION_IN,
            quantity=2000,
            reference="PRODUCTION-2000",
        )
        self.client.force_login(factory_user)

        first = self.client.post(
            reverse("record_dispatch"),
            {"sku": product.sku, "quantity": "300", "destination": "MWANZA"},
        )
        second = self.client.post(
            reverse("record_dispatch"),
            {"sku": product.sku, "quantity": "400", "destination": "DAR"},
        )

        self.assertRedirects(first, reverse("factory_dashboard"))
        self.assertRedirects(second, reverse("factory_dashboard"))
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
            name="Dispatch Product",
            sku="DISPATCH-001",
            category=Product.Category.FINISHED_GOOD,
        )
        post_movement(
            product=product,
            location=self.factory_location,
            movement=InventoryLedger.Movement.PRODUCTION_OUT,
            quantity=10,
            reference="DISPATCH-OPENING-STOCK",
        )
        self.client.force_login(factory_user)

        response = self.client.post(
            reverse("record_dispatch"),
            {"sku": product.sku, "quantity": "4", "destination": "DAR"},
        )

        self.assertRedirects(response, reverse("factory_dashboard"))
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
            {"sku": product.sku, "quantity": "20", "destination": "MWANZA"},
        )

        self.assertRedirects(response, reverse("factory_dashboard"))
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
        self.client.force_login(self.branch)
        response = self.client.post(
            reverse("submit_daily_report"),
            {
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
        self.assertRedirects(response, reverse("mwanza_dashboard"))
        report = BranchDailyReport.objects.get(
            location=StockLocation.LocationType.BRANCH_MWANZA,
        )
        self.assertEqual(report.units_sold, 12)
        self.assertEqual(report.status, BranchDailyReport.Status.SUBMITTED)

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
                name="Effective Diet",
                unit_price="100000",
                category=Product.Category.FINISHED_GOOD,
            ).exists()
        )
        self.assertEqual(
            Product.objects.filter(category=Product.Category.RAW_MATERIAL).count(),
            9,
        )
        self.assertEqual(
            Product.objects.filter(category=Product.Category.PACKAGING).count(),
            7,
        )
