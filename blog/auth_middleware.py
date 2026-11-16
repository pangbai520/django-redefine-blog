from django.http import HttpResponse, JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.utils.translation import gettext as _

from blog.services.throttle import login_rate_limited


class AuthenticationRateLimitMiddleware(MiddlewareMixin):
    """Apply the same checks before any project password login view runs."""

    login_views = {"admin:login", "comment_login", "comment_login_ajax"}

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = request.resolver_match
        if request.method != "POST" or not match or match.view_name not in self.login_views:
            return None
        if not login_rate_limited(request):
            return None
        message = _("Too many sign-in attempts. Please try again later.")
        if match.view_name == "comment_login_ajax":
            response = JsonResponse({"ok": False, "error": message}, status=429)
        else:
            response = HttpResponse(message, status=429, content_type="text/plain; charset=utf-8")
        response["Retry-After"] = "900"
        response["Cache-Control"] = "no-store"
        return response
