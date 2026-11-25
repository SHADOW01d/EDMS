# Management PDF reports

The report screen and PDF use `build_report_data(from_date, to_date, office)` in
`services.py` as the shared source for sales, product lines, production, stock,
losses, customer visits, deliveries, calls, and follow-ups.

Only managers can generate or download PDFs for all offices or either branch.
Daily reports use one date and the two-page layout; weekly, monthly-to-date,
and custom reports use the period layout. Generated PDFs are stored under
`MEDIA_ROOT/reports/` and listed in manager report history. Branch managers
cannot generate or download PDFs; they can review read-only figures for today
and submit their daily branch report from the branch dashboard.

Run the schema migration and focused tests with:

```sh
python manage.py migrate reports
python manage.py test apps.reports
```

The ReportLab renderer in `pdf.py` uses Pillow to create 240-DPI charts. The
bundled Poppins font files and their Open Font License are in `assets/`.
To extend report metrics, add them to `build_report_data` first and consume the
same fields from the dashboard or PDF renderer. Production margin remains
omitted until verified production costs are available. Full Package is shown
as a virtual bundle based on the minimum component stock and is excluded from
tangible stock totals to prevent double counting.
