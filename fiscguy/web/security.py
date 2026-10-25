import time

from django.contrib.auth.views import redirect_to_login
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.http import urlencode

from fiscguy import conf

REAUTH_SESSION_KEY = "fiscguy_reauth_at"

CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
)


def apply_security_headers(response: HttpResponse) -> HttpResponse:
    response["Cache-Control"] = "no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["X-Frame-Options"] = "DENY"
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "same-origin"
    response["Content-Security-Policy"] = CSP
    return response


def throttled(request, scope: str, limit: int, window: int = 60) -> bool:
    """True when the user (or IP) has used up `limit` hits for `scope` in `window` seconds."""
    who = request.user.pk if request.user.is_authenticated else request.META.get("REMOTE_ADDR", "")
    key = f"fiscguy:throttle:{scope}:{who}"
    cache.add(key, 0, window)
    try:
        return cache.incr(key) > limit
    except ValueError:
        cache.set(key, 1, window)
        return False


def mark_reauthenticated(request) -> None:
    request.session[REAUTH_SESSION_KEY] = int(time.time())


def recently_authenticated(request) -> bool:
    stamp = request.session.get(REAUTH_SESSION_KEY)
    return bool(stamp) and (time.time() - stamp) <= conf.reauth_max_age()


class FiscguyWebMixin:
    """Gate for every UI view: feature flag, login, permission, optional re-auth, secure headers.

    Set `action` to a fiscguy permission codename; set `require_reauth = True` for sensitive views.
    """

    action: str | None = "view_receipts"
    require_reauth = False

    def dispatch(self, request, *args, **kwargs):
        if not conf.ui_enabled():
            raise Http404
        if not request.user.is_authenticated:
            return apply_security_headers(redirect_to_login(request.get_full_path()))
        if self.action and not conf.access_allowed(request, self.action):
            raise PermissionDenied
        if self.require_reauth and not recently_authenticated(request):
            query = urlencode({"next": request.get_full_path()})
            return apply_security_headers(
                HttpResponseRedirect(f"{reverse('fiscguy_web:reauth')}?{query}")
            )
        return apply_security_headers(super().dispatch(request, *args, **kwargs))
