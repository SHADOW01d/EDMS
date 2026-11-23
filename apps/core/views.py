import os

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.cache import patch_vary_headers


def home(request):
    return render(request, "core/home.html")


def _static_asset_response(filename, content_type):
    asset_path = os.path.join(settings.BASE_DIR, "static", filename)
    with open(asset_path, "rb") as asset:
        response = HttpResponse(asset.read(), content_type=content_type)
    response["Cache-Control"] = "no-cache"
    if filename == "sw.js":
        response["Service-Worker-Allowed"] = "/"
    patch_vary_headers(response, ("Accept-Encoding",))
    return response


def service_worker(request):
    return _static_asset_response("sw.js", "application/javascript; charset=utf-8")


def web_manifest(request):
    return _static_asset_response("manifest.json", "application/manifest+json")


def offline(request):
    return render(request, "pwa/offline.html")
