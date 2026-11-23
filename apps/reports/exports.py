import csv

from django.http import HttpResponse


def _spreadsheet_safe(value):
    if isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def csv_response(filename, headers, rows):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow([_spreadsheet_safe(value) for value in headers])
    writer.writerows(
        [_spreadsheet_safe(value) for value in row]
        for row in rows
    )
    return response
