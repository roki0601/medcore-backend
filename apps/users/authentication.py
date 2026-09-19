from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


class VersionedJWTAuthentication(JWTAuthentication):
    """Validate SimpleJWT credentials against the current User auth version."""

    def get_user(self, validated_token):
        try:
            user = super().get_user(validated_token)
        except AuthenticationFailed as exc:
            detail = exc.detail
            detail_code = detail.get("code") if isinstance(detail, dict) else None
            if str(detail_code) == "user_inactive":
                raise AuthenticationFailed(
                    "User account is inactive.",
                    code="AUTH_USER_INACTIVE",
                ) from exc
            raise

        token_auth_version = validated_token.get("auth_version")
        try:
            auth_version_matches = (
                token_auth_version is not None
                and int(token_auth_version) == user.auth_version
            )
        except (TypeError, ValueError):
            auth_version_matches = False
        if not auth_version_matches:
            raise AuthenticationFailed(
                "Authentication credentials are no longer valid.",
                code="AUTHENTICATION_REQUIRED",
            )
        if not user.is_active:
            raise AuthenticationFailed(
                "User account is inactive.",
                code="AUTH_USER_INACTIVE",
            )
        return user
