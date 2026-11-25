from collections import defaultdict

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction
from psycopg import sql


COPY_APP_LABELS = {
    "accounts",
    "auth",
    "admin",
    "inventory",
    "procurement",
    "production",
    "distribution",
    "sales",
    "customers",
    "reports",
    "notifications",
    "dashboard",
    "sessions",
}
EXCLUDED_MODELS = {
    ("contenttypes", "ContentType"),
    ("auth", "Permission"),
}


class Command(BaseCommand):
    help = "Safely copy business data from the baseline SQLite database to PostgreSQL."

    def add_arguments(self, parser):
        parser.add_argument("--source", default="db.sqlite3")
        parser.add_argument("--confirm-copy", action="store_true")

    def handle(self, *args, **options):
        if not options["confirm_copy"]:
            raise CommandError("Pass --confirm-copy after backing up and verifying the source database.")

        target = connections["default"]
        if target.vendor != "postgresql":
            raise CommandError("The default database must be PostgreSQL.")

        source = connections.databases.setdefault(
            "sqlite_source",
            {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": options["source"],
                "CONN_MAX_AGE": 0,
                "CONN_HEALTH_CHECKS": False,
                "ATOMIC_REQUESTS": False,
                "AUTOCOMMIT": True,
                "TIME_ZONE": None,
                "OPTIONS": {},
                "USER": "",
                "PASSWORD": "",
                "HOST": "",
                "PORT": "",
                "TEST": {"CHARSET": None, "COLLATION": None, "MIGRATE": True, "MIRROR": None, "NAME": None},
            },
        )
        connections["sqlite_source"]

        models = self._ordered_models()
        report = {"models": [], "many_to_many": []}

        with transaction.atomic(using="default"):
            for model in reversed(models):
                if model._meta.app_label in COPY_APP_LABELS:
                    model._base_manager.using("default").all().delete()

            for model in models:
                if model._meta.app_label not in COPY_APP_LABELS:
                    continue
                key = (model._meta.app_label, model.__name__)
                if key in EXCLUDED_MODELS:
                    continue

                source_rows = list(model._base_manager.using("sqlite_source").all().iterator(chunk_size=1000))
                target_instances = []
                for source_row in source_rows:
                    target_instance = model()
                    for field in model._meta.concrete_fields:
                        setattr(target_instance, field.attname, getattr(source_row, field.attname))
                    target_instances.append(target_instance)

                if target_instances:
                    model._base_manager.using("default").bulk_create(target_instances, batch_size=500)

                target_count = model._base_manager.using("default").count()
                report["models"].append({
                    "model": f"{model._meta.app_label}.{model.__name__}",
                    "source": len(source_rows),
                    "target": target_count,
                })

            for through_model in apps.get_models(include_auto_created=True):
                if not through_model._meta.auto_created:
                    continue
                if through_model._meta.app_label not in COPY_APP_LABELS:
                    continue

                table = through_model._meta.db_table
                source_cursor = connections["sqlite_source"].cursor()
                source_query = "SELECT * FROM " + connections["sqlite_source"].ops.quote_name(table)
                source_cursor.execute(source_query)
                column_names = [column[0] for column in source_cursor.description]
                rows = source_cursor.fetchall()
                source_cursor.close()

                target_cursor = target.cursor()
                target_cursor.execute(
                    sql.SQL("DELETE FROM {}").format(sql.Identifier(table))
                )
                if rows:
                    quoted_columns = ", ".join(f'"{name}"' for name in column_names)
                    placeholders = ", ".join(["%s"] * len(column_names))
                    insert_query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                        sql.Identifier(table),
                        sql.SQL(", ").join(sql.Identifier(name) for name in column_names),
                        sql.SQL(", ").join(sql.Placeholder() for _ in column_names),
                    )
                    target_cursor.executemany(insert_query, rows)
                target_cursor.close()
                report["many_to_many"].append({
                    "table": table,
                    "source": len(rows),
                })

            self._reset_sequences(models)

        mismatches = [row for row in report["models"] if row["source"] != row["target"]]
        if mismatches:
            raise CommandError(f"Source/target row count mismatch: {mismatches}")

        self.stdout.write(self.style.SUCCESS("SQLite-to-PostgreSQL copy completed and counts verified."))
        for row in report["models"]:
            self.stdout.write(f"{row['model']}: {row['source']} -> {row['target']}")

    def _ordered_models(self):
        concrete = [
            model for model in apps.get_models(include_auto_created=False)
            if model._meta.app_label in COPY_APP_LABELS
            and not model._meta.proxy
            and (model._meta.app_label, model.__name__) not in EXCLUDED_MODELS
        ]

        dependencies = {model: set() for model in concrete}
        by_name = {(model._meta.app_label, model.__name__): model for model in concrete}
        for model in concrete:
            for field in model._meta.concrete_fields:
                remote = getattr(field, "remote_field", None)
                if remote and getattr(remote, "model", None):
                    remote_model = remote.model
                    if remote_model in dependencies:
                        dependencies[model].add(remote_model)

        remaining = set(concrete)
        ordered = []
        while remaining:
            ready = [model for model in remaining if not (dependencies[model] & remaining)]
            if not ready:
                raise CommandError("Could not resolve model dependency order for migration.")
            for model in ready:
                ordered.append(model)
                remaining.remove(model)
        return ordered

    def _reset_sequences(self, models):
        cursor = connections["default"].cursor()
        for model in models:
            if model._meta.app_label not in COPY_APP_LABELS:
                continue
            pk = model._meta.pk
            if pk.get_internal_type() not in {"AutoField", "BigAutoField", "SmallAutoField"}:
                continue
            table = model._meta.db_table
            column = pk.column
            sequence_query = sql.SQL(
                "SELECT setval(pg_get_serial_sequence(%s, %s), COALESCE(MAX({}), 1), MAX({}) IS NOT NULL) FROM {}"
            ).format(sql.Identifier(column), sql.Identifier(column), sql.Identifier(table))
            cursor.execute(sequence_query, [table, column])
        cursor.close()
