from __future__ import annotations

import hashlib

from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle


class _ScopedThrottle(SimpleRateThrottle):
    def _cache_key(self, ident: str) -> str:
        return self.cache_format % {"scope": self.scope, "ident": ident}


class TelegramLoginIPThrottle(_ScopedThrottle):
    scope = "telegram_login"

    def get_cache_key(self, request, view):
        return self._cache_key(self.get_ident(request))


class TelegramLoginClaimThrottle(_ScopedThrottle):
    scope = "telegram_login_user"

    def get_cache_key(self, request, view):
        telegram_id = request.data.get("id")
        if not telegram_id:
            return None
        return self._cache_key(str(telegram_id))


class RefreshIPThrottle(_ScopedThrottle):
    scope = "refresh"

    def get_cache_key(self, request, view):
        return self._cache_key(self.get_ident(request))


class RefreshSessionThrottle(_ScopedThrottle):
    scope = "refresh_session"

    def get_cache_key(self, request, view):
        raw_cookie = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME)
        if not raw_cookie:
            return None
        digest = hashlib.sha256(raw_cookie.encode()).hexdigest()
        return self._cache_key(digest)


class AccountMutationThrottle(_ScopedThrottle):
    scope = "account_mutation"

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return self._cache_key(self.get_ident(request))
        return self._cache_key(f"{request.user.pk}:{self.get_ident(request)}")
