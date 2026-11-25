from datetime import datetime, time, timedelta
from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from apps.accounts.models import User
from apps.customers.models import BranchDelivery, Customer, CustomerCall, CustomerVisit
from apps.inventory.models import InventoryLedger, Product, StockLocation
from apps.production.models import ProductionBatch, ProductionOutput
from apps.reports.models import GeneratedReport
from apps.reports.pdf import generate_report_pdf
from apps.reports.services import build_report_data
from apps.sales.models import Sale, SaleItem


class ReportTestDataMixin:
    def setUp(self):
        super().setUp()
        self.manager = User.objects.create_user(
            username="report-manager",
            password="report-password-123",
            role=User.Role.MANAGER,
        )
        self.mwanza_user = User.objects.create_user(
            username="report-mwanza",
            password="report-password-123",
            role=User.Role.BRANCH_MWANZA,
        )
        self.mwanza, _ = StockLocation.objects.get_or_create(
            location_type=StockLocation.LocationType.BRANCH_MWANZA,
            defaults={"name": "Mwanza"},
        )
        self.dar, _ = StockLocation.objects.get_or_create(
            location_type=StockLocation.LocationType.BRANCH_DAR,
            defaults={"name": "Dar es Salaam"},
        )
        self.store, _ = StockLocation.objects.get_or_create(
            location_type=StockLocation.LocationType.FACTORY,
            defaults={"name": "Store"},
        )
        self.products = {}
        product_specs = {
            "diet": ("Effective Diet", "ED-SINGLE", "jar", "500", "1"),
            "masala": ("Presha Masala", "PRESHA-SINGLE", "piece", "600", "0"),
            "honey": ("Wild Honey", "HONEY-SINGLE", "jar", "700", "0"),
            "package": (
                "Effective Diet Full Package",
                "ED-PK-FULL",
                "package",
                "750",
                "0",
            ),
        }
        for key, (name, sku, unit, price, reorder_level) in product_specs.items():
            self.products[key], _ = Product.objects.update_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "unit": unit,
                    "unit_price": Decimal(price),
                    "reorder_level": Decimal(reorder_level),
                    "category": Product.Category.FINISHED_GOOD,
                    "active": True,
                },
            )
        self.report_date = timezone.localdate()
        self.customer = Customer.objects.create(
            name="Test Customer",
            location=self.mwanza,
            phone="+255712345678",
            address="Mwanza",
        )
        self._create_production_and_stock()
        self._create_sales_and_activity()

    def _at(self, day, hour=10):
        return timezone.make_aware(datetime.combine(day, time(hour=hour)))

    def _create_production_and_stock(self):
        batch = ProductionBatch.objects.create(
            reference="REPORT-BATCH-1",
            quantity=Decimal("38"),
            status=ProductionBatch.Status.COMPLETED,
            production_date=self.report_date,
            created_by=self.manager,
        )
        for key, quantity in (("diet", 20), ("masala", 10), ("honey", 8)):
            ProductionOutput.objects.create(
                batch=batch,
                product=self.products[key],
                quantity=Decimal(quantity),
                production_date=self.report_date,
                reference=f"REPORT-OUT-{key}",
                created_by=self.manager,
            )
        balances = {
            "diet": (10, 5, 2),
            "masala": (5, 3, 1),
            "honey": (4, 3, 2),
        }
        locations = (self.store, self.mwanza, self.dar)
        for key, quantities in balances.items():
            for location, quantity in zip(locations, quantities):
                InventoryLedger.objects.create(
                    product=self.products[key],
                    location=location,
                    movement=InventoryLedger.Movement.PRODUCTION_IN,
                    quantity=Decimal(quantity),
                    balance_after=Decimal(quantity),
                    created_at=self._at(self.report_date - timedelta(days=2)),
                )
        InventoryLedger.objects.create(
            product=self.products["diet"],
            location=self.mwanza,
            movement=InventoryLedger.Movement.LOSS,
            quantity=Decimal("-1"),
            balance_after=Decimal("4"),
            created_at=self._at(self.report_date),
        )

    def _sale(self, reference, day, amount, customer=None):
        sale = Sale.objects.create(
            reference=reference,
            location=self.mwanza,
            customer=customer,
            sold_by=self.manager,
            total_amount=Decimal(amount),
        )
        sale.sold_at = self._at(day)
        sale.save(update_fields=("sold_at",))
        return sale

    def _create_sales_and_activity(self):
        sale = self._sale("REPORT-SALE-1", self.report_date, "1750", self.customer)
        SaleItem.objects.create(
            sale=sale,
            product=self.products["diet"],
            quantity=Decimal("2"),
            unit_price=Decimal("500"),
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.products["package"],
            quantity=Decimal("1"),
            unit_price=Decimal("750"),
        )
        previous_day = self._sale(
            "REPORT-SALE-2",
            self.report_date - timedelta(days=1),
            "1000",
        )
        SaleItem.objects.create(
            sale=previous_day,
            product=self.products["diet"],
            quantity=Decimal("2"),
            unit_price=Decimal("500"),
        )
        visit = CustomerVisit.objects.create(
            customer=self.customer,
            location=self.mwanza,
            visit_type=CustomerVisit.VisitType.RETURNING_CUSTOMER,
            visitor_name=self.customer.name,
            recorded_by=self.manager,
        )
        visit.visited_at = self._at(self.report_date)
        visit.save(update_fields=("visited_at",))
        delivery = BranchDelivery.objects.create(
            customer=self.customer,
            location=self.mwanza,
            recipient_name=self.customer.name,
            destination="Mwanza",
            parcel_count=2,
            delivery_date=self.report_date,
            recorded_by=self.manager,
        )
        delivery.created_at = self._at(self.report_date)
        delivery.save(update_fields=("created_at",))
        call = CustomerCall.objects.create(
            customer=self.customer,
            location=self.mwanza,
            called_by=self.manager,
            call_type=CustomerCall.CallType.FOLLOW_UP,
            outcome="Customer understood instructions",
            follow_up_date=self.report_date,
        )
        call.called_at = self._at(self.report_date)
        call.save(update_fields=("called_at",))


class BuildReportDataTests(ReportTestDataMixin, TestCase):
    def test_daily_report_data_includes_seven_day_sales_trend_by_branch(self):
        data = build_report_data(self.report_date, self.report_date, "all")

        self.assertEqual(len(data["daily_sales_trend"]), 7)
        self.assertEqual(
            data["daily_sales_trend"][-2]["offices"]["mwanza"],
            Decimal("1000"),
        )
        self.assertEqual(
            data["daily_sales_trend"][-1]["offices"]["mwanza"],
            Decimal("1750"),
        )
        self.assertEqual(
            data["daily_sales_trend"][-1]["offices"]["dar"],
            Decimal("0"),
        )

    def test_report_data_uses_period_sale_lines_and_physical_stock(self):
        data = build_report_data(self.report_date, self.report_date, "all")

        self.assertEqual(data["sales_total"], Decimal("1750"))
        self.assertEqual(data["sales_last_day"], Decimal("1750"))
        self.assertEqual(data["yesterday_sales"], Decimal("1000"))
        self.assertEqual(data["sales_change_percent"], Decimal("75.00"))
        self.assertEqual(data["units_sold"], Decimal("3"))
        self.assertEqual(data["produced_total"], Decimal("38"))
        self.assertEqual(data["store_stock"], Decimal("19"))
        self.assertEqual(data["branch_stock"], Decimal("15"))
        self.assertEqual(data["current_stock"], Decimal("34"))
        self.assertEqual(data["loss_total"], Decimal("1"))
        self.assertEqual(data["customers_served"], 1)
        self.assertEqual(data["delivery_count"], 1)
        self.assertEqual(data["parcel_count"], 2)
        self.assertEqual(data["followups_due_today"], 1)

        daily = next(row for row in data["sales_table_rows"] if row["date"] == self.report_date and row["office_key"] == "mwanza")
        daily_diet = next(row for row in daily["products"] if row["product"].sku == "ED-SINGLE")
        self.assertEqual(daily_diet["quantity"], Decimal("2"))
        self.assertEqual(daily_diet["revenue"], Decimal("1000"))
        virtual_package = next(row for row in data["products"] if row["sku"] == "ED-PK-FULL")
        self.assertTrue(virtual_package["is_virtual"])
        self.assertEqual(virtual_package["current_stock"], Decimal("8"))
        self.assertEqual(
            data["current_stock"],
            sum((row["current_stock"] for row in data["tangible_products"]), Decimal("0")),
        )

    def test_daily_sales_table_is_ordered_newest_date_first(self):
        data = build_report_data(
            self.report_date - timedelta(days=6),
            self.report_date,
            "all",
        )

        row_dates = [row["date"] for row in data["sales_table_rows"]]
        self.assertEqual(row_dates, sorted(row_dates, reverse=True))
        self.assertEqual(
            [row["office_key"] for row in data["sales_table_rows"][:2]],
            ["mwanza", "dar"],
        )

    def test_branch_report_only_returns_the_requested_office(self):
        data = build_report_data(self.report_date, self.report_date, "mwanza")

        self.assertEqual([row["key"] for row in data["branches"]], ["mwanza"])
        self.assertIsNone(data["store_stock"])
        self.assertIsNone(data["products"][0]["store_stock"])
        self.assertEqual(data["branches"][0]["sales"], Decimal("1750"))

    def test_invalid_date_range_is_rejected(self):
        with self.assertRaises(ValueError):
            build_report_data(self.report_date, self.report_date - timedelta(days=1), "all")


class ReportPdfTests(ReportTestDataMixin, TestCase):
    def test_daily_and_period_pdfs_have_expected_page_count_and_content(self):
        daily_data = build_report_data(self.report_date, self.report_date, "all")
        period_data = build_report_data(
            self.report_date - timedelta(days=6),
            self.report_date,
            "all",
        )
        daily_reader = PdfReader(BytesIO(generate_report_pdf(daily_data, "DAILY")))
        period_reader = PdfReader(BytesIO(generate_report_pdf(period_data, "CUSTOM")))

        self.assertEqual(len(daily_reader.pages), 2)
        self.assertEqual(len(period_reader.pages), 6)
        for reader in (daily_reader, period_reader):
            for page_number, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text() or ""
                self.assertGreater(len(page_text), 50)
                self.assertIn("Confidential - for management use", page_text)
                self.assertIn(f"Page {page_number} of {len(reader.pages)}", page_text)
                self.assertTrue(page["/Resources"].get("/XObject"))
        self.assertIn("Day at a Glance", daily_reader.pages[0].extract_text())
        self.assertIn("Key Highlights", daily_reader.pages[0].extract_text())
        self.assertIn("Sales Performance", period_reader.pages[1].extract_text())
        self.assertIn("TOTAL", period_reader.pages[1].extract_text())
        self.assertIn("Page 6 of 6", period_reader.pages[5].extract_text())

    def test_zero_sales_day_is_valid_and_previous_day_percentage_is_unavailable(self):
        zero_date = self.report_date + timedelta(days=10)
        data = build_report_data(zero_date, zero_date, "mwanza")
        pdf = PdfReader(BytesIO(generate_report_pdf(data, "DAILY")))

        self.assertEqual(data["sales_total"], Decimal("0"))
        self.assertIsNone(data["sales_change_percent"])
        self.assertEqual(len(pdf.pages), 2)
        self.assertIn("n/a", pdf.pages[0].extract_text())

    def test_long_customer_log_paginates_without_losing_rows(self):
        for index in range(45):
            visit = CustomerVisit.objects.create(
                location=self.mwanza,
                visit_type=CustomerVisit.VisitType.OTHER,
                visitor_name=f"Visitor {index:02d}",
                recorded_by=self.manager,
            )
            visit.visited_at = self._at(self.report_date)
            visit.save(update_fields=("visited_at",))
        data = build_report_data(
            self.report_date - timedelta(days=6),
            self.report_date,
            "mwanza",
        )
        pdf = PdfReader(BytesIO(generate_report_pdf(data, "CUSTOM")))
        all_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

        self.assertGreaterEqual(len(pdf.pages), 6)
        self.assertIn("Visitor 44", all_text)
        self.assertGreater(all_text.count("Customer / visitor"), 1)


class GeneratedReportAccessTests(ReportTestDataMixin, TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media = TemporaryDirectory()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media.name)
        cls._media_override.enable()
        cls.addClassCleanup(cls._media.cleanup)
        cls.addClassCleanup(cls._media_override.disable)

    def test_manager_can_generate_and_redownload_a_report(self):
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse("generate_report"),
            {
                "report_type": "daily",
                "end_date": self.report_date.isoformat(),
                "office": "all",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(
            f"Effective_Diet_Daily_Report_{self.report_date.isoformat()}.pdf",
            response["Content-Disposition"],
        )
        report = GeneratedReport.objects.get()
        self.assertEqual(report.generated_by, self.manager)
        self.assertEqual(report.office, GeneratedReport.Office.ALL)
        self.assertEqual(report.report_type, GeneratedReport.ReportType.DAILY)

        history_response = self.client.get(
            reverse("download_report", args=(report.pk,)),
        )
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(history_response["Content-Type"], "application/pdf")

    def test_monthly_report_covers_thirty_days_ending_on_selected_date(self):
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse("generate_report"),
            {
                "report_type": "monthly",
                "end_date": self.report_date.isoformat(),
                "office": "all",
            },
        )

        self.assertEqual(response.status_code, 200)
        report = GeneratedReport.objects.get()
        self.assertEqual(report.to_date, self.report_date)
        self.assertEqual(report.from_date, self.report_date - timedelta(days=29))
        self.assertEqual((report.to_date - report.from_date).days + 1, 30)

    def test_branch_user_cannot_generate_or_download_pdf_reports(self):
        report = GeneratedReport.objects.create(
            report_type=GeneratedReport.ReportType.CUSTOM,
            from_date=self.report_date,
            to_date=self.report_date,
            office=GeneratedReport.Office.DAR,
            generated_by=self.manager,
        )
        self.client.force_login(self.mwanza_user)
        response = self.client.get(
            reverse("generate_report"),
            {
                "report_type": "daily",
                "end_date": self.report_date.isoformat(),
                "office": "dar",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            self.client.get(reverse("download_report", args=(report.pk,))).status_code,
            403,
        )
        self.assertEqual(GeneratedReport.objects.count(), 1)
