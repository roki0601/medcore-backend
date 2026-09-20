from __future__ import annotations

from django.conf import settings
from django.core.checks import Error, Tags, register

SUPPORTED_ROBOKASSA_HASH_ALGORITHMS = {"md5", "sha256"}


@register(Tags.security)
def check_robokassa_configuration(app_configs, **kwargs) -> list[Error]:
    """Validate Robokassa configuration settings for production safety.

    Robokassa must not be used without credentials, and the hash algorithm
    must be one of the supported algorithms ('md5', 'sha256').
    Outside DEBUG (production), missing merchant credentials or passwords
    are treated as critical security deployment errors.
    """
    errors: list[Error] = []

    hash_algo = getattr(settings, "ROBOKASSA_HASH_ALGORITHM", "sha256")
    if str(hash_algo).strip().lower() not in SUPPORTED_ROBOKASSA_HASH_ALGORITHMS:
        errors.append(
            Error(
                f"ROBOKASSA_HASH_ALGORITHM='{hash_algo}' is not supported.",
                hint="Set ROBOKASSA_HASH_ALGORITHM to 'sha256' or 'md5'.",
                id="subscriptions.E001",
            )
        )

    if not settings.DEBUG:
        login = getattr(settings, "ROBOKASSA_MERCHANT_LOGIN", "")
        pwd_1 = getattr(settings, "ROBOKASSA_PASSWORD_1", "")
        pwd_2 = getattr(settings, "ROBOKASSA_PASSWORD_2", "")

        missing = []
        if not str(login).strip():
            missing.append("ROBOKASSA_MERCHANT_LOGIN")
        if not str(pwd_1).strip():
            missing.append("ROBOKASSA_PASSWORD_1")
        if not str(pwd_2).strip():
            missing.append("ROBOKASSA_PASSWORD_2")

        if missing:
            errors.append(
                Error(
                    "Production Robokassa configuration is missing required "
                    f"secrets: {', '.join(missing)}.",
                    hint=(
                        "Set ROBOKASSA_MERCHANT_LOGIN, ROBOKASSA_PASSWORD_1, and "
                        "ROBOKASSA_PASSWORD_2 environment variables."
                    ),
                    id="subscriptions.E002",
                )
            )

    return errors
