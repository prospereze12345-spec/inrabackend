"""
Resolve a 2-letter country code for an incoming request.

Cheapest path first: most edge/CDN providers already resolve geo and hand it
to you in a header — no DB, no extra lookup, no extra latency.
  - Vercel:      x-vercel-ip-country
  - Cloudflare:  cf-ipcountry
  - Fastly:      (varies by config, often set manually)

Falls back to GeoIP2 (MaxMind) if you have GEOIP_PATH configured in
settings and the `geoip2` package installed. If neither is available,
returns None — the analytics endpoint just buckets those as "Unknown".
"""

from django.conf import settings


def get_client_ip(request) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def get_country_code(request) -> str | None:
    header_country = (
        request.headers.get("x-vercel-ip-country")
        or request.headers.get("cf-ipcountry")
        or request.headers.get("x-country-code")
    )
    if header_country and header_country != "XX":
        return header_country.upper()

    if getattr(settings, "GEOIP_PATH", None):
        try:
            from django.contrib.gis.geoip2 import GeoIP2

            ip = get_client_ip(request)
            if not ip:
                return None
            g = GeoIP2()
            return g.country_code(ip)
        except Exception:
            return None

    return None
