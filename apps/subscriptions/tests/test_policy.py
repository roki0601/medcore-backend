from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from apps.subscriptions import policy

User = get_user_model()


@pytest.mark.django_db
def test_no_entitlement_source_denies_paid_access():
    user = User(username="reader")
    user.set_unusable_password()
    user.save()

    assert policy.has_paid_content_entitlement(user) is False


@pytest.mark.django_db
def test_policy_is_callable_for_superuser_without_role_bypass():
    user = User(username="root", role=User.Role.ADMIN, is_staff=True, is_superuser=True)
    user.set_unusable_password()
    user.save()

    assert policy.has_paid_content_entitlement(user) is False
