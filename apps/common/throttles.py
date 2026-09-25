from __future__ import annotations

from rest_framework.throttling import SimpleRateThrottle


class _ScopedThrottle(SimpleRateThrottle):
    def _cache_key(self, ident: str) -> str:
        return self.cache_format % {"scope": self.scope, "ident": ident}


class FeedbackAnonThrottle(_ScopedThrottle):
    scope = "feedback_anon"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            return None
        return self._cache_key(self.get_ident(request))


class FeedbackUserThrottle(_ScopedThrottle):
    scope = "feedback_user"

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None
        return self._cache_key(str(request.user.pk))
