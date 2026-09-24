import hashlib
import json
import urllib.parse
from datetime import timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.subscriptions.models import Payment, Plan, Subscription
from apps.subscriptions.policy import has_paid_content_entitlement
from apps.subscriptions.robokassa import (
    build_payment_url,
    build_receipt,
    calculate_payment_signature,
    calculate_result_signature,
    format_out_sum,
    serialize_receipt,
    verify_result_signature,
)
from apps.subscriptions.selectors import get_active_subscription
from apps.subscriptions.services import create_payment, process_robokassa_result

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def configure_robokassa_test_settings(settings):
    settings.ROBOKASSA_MERCHANT_LOGIN = "test_merchant"
    settings.ROBOKASSA_PASSWORD_1 = "live_pass_1"
    settings.ROBOKASSA_PASSWORD_2 = "live_pass_2"
    settings.ROBOKASSA_TEST_PASSWORD_1 = "test_pass_1"
    settings.ROBOKASSA_TEST_PASSWORD_2 = "test_pass_2"
    settings.ROBOKASSA_HASH_ALGORITHM = "sha256"
    settings.ROBOKASSA_TEST_MODE = True


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="buyer_user",
        telegram_id=123456789,
        email="buyer@example.com",
    )


@pytest.fixture
def plan(db):
    return Plan.objects.create(
        code="pro-month",
        title="Месячная подписка Pro",
        description="Полный доступ на 30 дней",
        price_rub=Decimal("990.00"),
        duration_days=30,
        is_active=True,
    )


@pytest.fixture
def inactive_plan(db):
    return Plan.objects.create(
        code="disabled-plan",
        title="Отключенный тариф",
        description="Недоступен",
        price_rub=Decimal("490.00"),
        duration_days=14,
        is_active=False,
    )


# ==============================================================================
# 1. Robokassa Helper Unit Tests
# ==============================================================================


def test_format_out_sum():
    assert format_out_sum(Decimal("990.00")) == "990.00"
    assert format_out_sum(Decimal("990")) == "990.00"
    assert format_out_sum(150.5) == "150.50"
    assert format_out_sum("123.456") == "123.46"


def test_robokassa_signature_generation_deterministic():
    merchant_login = "medcore_merchant"
    out_sum = "990.00"
    inv_id = 42
    pwd_1 = "secret_pass_1"

    expected_sha256 = (
        hashlib.sha256(f"{merchant_login}:{out_sum}:{inv_id}:{pwd_1}".encode())
        .hexdigest()
        .lower()
    )

    sig = calculate_payment_signature(
        merchant_login=merchant_login,
        out_sum=out_sum,
        inv_id=inv_id,
        password_1=pwd_1,
        hash_algorithm="sha256",
    )
    assert sig == expected_sha256

    expected_md5 = (
        hashlib.md5(f"{merchant_login}:{out_sum}:{inv_id}:{pwd_1}".encode())
        .hexdigest()
        .lower()
    )
    sig_md5 = calculate_payment_signature(
        merchant_login=merchant_login,
        out_sum=out_sum,
        inv_id=inv_id,
        password_1=pwd_1,
        hash_algorithm="md5",
    )
    assert sig_md5 == expected_md5


def test_robokassa_signature_invalid_algorithm_raises():
    with pytest.raises(ValueError, match="Unsupported Robokassa hash algorithm"):
        calculate_payment_signature(
            merchant_login="m",
            out_sum="100.00",
            inv_id=1,
            password_1="p",
            hash_algorithm="sha512",
        )


def test_robokassa_verify_result_signature():
    out_sum = "990.00"
    inv_id = 100
    pwd_2 = "pass_two"

    correct_sig = calculate_result_signature(
        out_sum=out_sum,
        inv_id=inv_id,
        password_2=pwd_2,
        hash_algorithm="sha256",
    )

    # Verification must succeed with identical or upper-cased signature
    assert verify_result_signature(
        out_sum=out_sum,
        inv_id=inv_id,
        received_signature=correct_sig,
        password_2=pwd_2,
        hash_algorithm="sha256",
    )
    assert verify_result_signature(
        out_sum=out_sum,
        inv_id=inv_id,
        received_signature=correct_sig.upper(),
        password_2=pwd_2,
        hash_algorithm="sha256",
    )

    # Verification must fail with tampered sum, id, or signature
    assert not verify_result_signature(
        out_sum="991.00",
        inv_id=inv_id,
        received_signature=correct_sig,
        password_2=pwd_2,
        hash_algorithm="sha256",
    )
    assert not verify_result_signature(
        out_sum=out_sum,
        inv_id=101,
        received_signature=correct_sig,
        password_2=pwd_2,
        hash_algorithm="sha256",
    )
    assert not verify_result_signature(
        out_sum=out_sum,
        inv_id=inv_id,
        received_signature="invalid_signature_hex",
        password_2=pwd_2,
        hash_algorithm="sha256",
    )


@pytest.mark.django_db
def test_build_payment_url_contains_all_params(user, plan, settings):
    settings.ROBOKASSA_MERCHANT_LOGIN = "test_merchant"
    settings.ROBOKASSA_PASSWORD_1 = "test_pass_1"
    settings.ROBOKASSA_TEST_MODE = True
    settings.ROBOKASSA_BASE_URL = "https://auth.robokassa.ru/Merchant/Index.aspx"

    payment = Payment.objects.create(
        user=user,
        plan=plan,
        amount=plan.price_rub,
        status=Payment.Status.PENDING,
    )

    url = build_payment_url(payment)
    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "auth.robokassa.ru"
    assert parsed.path == "/Merchant/Index.aspx"

    params = parse_qs(parsed.query)
    assert params["MerchantLogin"] == ["test_merchant"]
    assert params["OutSum"] == ["990.00"]
    assert params["InvId"] == [str(payment.id)]
    assert params["IsTest"] == ["1"]
    assert params["Email"] == [user.email]
    assert "Description" in params
    assert "Receipt" in params
    assert "SignatureValue" in params


# ==============================================================================
# 2. Payment Domain Model Tests
# ==============================================================================


@pytest.mark.django_db
def test_payment_snapshot_price_immutability(user, plan):
    payment, _ = create_payment(user=user, plan_id=plan.id)
    assert payment.amount == Decimal("990.00")

    # Update plan price in DB
    plan.price_rub = Decimal("1490.00")
    plan.save()

    payment.refresh_from_db()
    assert payment.amount == Decimal("990.00")
    assert str(payment) == f"Payment #{payment.pk} (990.00 RUB, pending)"


@pytest.mark.django_db
def test_payment_retention_on_user_deletion(user, plan):
    payment, _ = create_payment(user=user, plan_id=plan.id)
    payment_id = payment.id

    user.delete()

    payment.refresh_from_db()
    assert payment.user is None
    assert payment.user_id is None
    assert payment.amount == Decimal("990.00")
    assert payment.plan == plan
    assert payment.status == Payment.Status.PENDING
    assert payment.provider == "robokassa"
    assert Payment.objects.filter(id=payment_id).exists()


@pytest.mark.django_db
def test_payment_protect_plan_deletion(user, plan):
    create_payment(user=user, plan_id=plan.id)

    with pytest.raises(ProtectedError):
        plan.delete()


# ==============================================================================
# 3. Payment Initialization API Tests
# ==============================================================================


@pytest.mark.django_db
def test_init_payment_unauthenticated_returns_401(api_client, plan):
    response = api_client.post(
        "/api/v1/subscriptions/payments/",
        {"plan_id": plan.id},
        format="json",
    )
    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.django_db
def test_init_payment_happy_path(api_client, user, plan, settings):
    settings.ROBOKASSA_MERCHANT_LOGIN = "test_merchant"
    settings.ROBOKASSA_PASSWORD_1 = "test_pass_1"

    api_client.force_authenticate(user=user)
    response = api_client.post(
        "/api/v1/subscriptions/payments/",
        {"plan_id": plan.id},
        format="json",
    )
    assert response.status_code == 201
    data = response.json()

    assert "payment_id" in data
    assert "payment_url" in data
    assert data["amount"] == "990.00"
    assert data["status"] == "pending"

    payment = Payment.objects.get(id=data["payment_id"])
    assert payment.user == user
    assert payment.plan == plan
    assert payment.status == Payment.Status.PENDING
    assert payment.paid_at is None
    assert payment.subscription is None


@pytest.mark.django_db
def test_init_payment_inactive_plan_returns_400(api_client, user, inactive_plan):
    api_client.force_authenticate(user=user)
    response = api_client.post(
        "/api/v1/subscriptions/payments/",
        {"plan_id": inactive_plan.id},
        format="json",
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "INVALID_REQUEST"
    assert "plan_id" in body["fields"]


@pytest.mark.django_db
def test_init_payment_nonexistent_plan_returns_400(api_client, user):
    api_client.force_authenticate(user=user)
    response = api_client.post(
        "/api/v1/subscriptions/payments/",
        {"plan_id": 99999},
        format="json",
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "INVALID_REQUEST"


@pytest.mark.django_db
def test_init_payment_missing_plan_id_returns_400(api_client, user):
    api_client.force_authenticate(user=user)
    response = api_client.post(
        "/api/v1/subscriptions/payments/",
        {},
        format="json",
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"


@pytest.mark.django_db
def test_payment_init_rejects_unconfigured_provider(api_client, user, plan, settings):
    settings.ROBOKASSA_MERCHANT_LOGIN = ""
    settings.ROBOKASSA_PASSWORD_1 = ""
    settings.ROBOKASSA_TEST_PASSWORD_1 = ""

    api_client.force_authenticate(user=user)
    response = api_client.post(
        "/api/v1/subscriptions/payments/",
        {"plan_id": plan.id},
        format="json",
    )
    assert response.status_code == 503
    assert response.json()["code"] == "PAYMENT_PROVIDER_UNCONFIGURED"
    assert Payment.objects.count() == 0


@pytest.mark.django_db
def test_payment_init_rejects_missing_password_2(api_client, user, plan, settings):
    settings.ROBOKASSA_PASSWORD_2 = ""
    settings.ROBOKASSA_TEST_PASSWORD_2 = ""

    api_client.force_authenticate(user=user)
    response = api_client.post(
        "/api/v1/subscriptions/payments/",
        {"plan_id": plan.id},
        format="json",
    )

    assert response.status_code == 503
    assert response.json()["code"] == "PAYMENT_PROVIDER_UNCONFIGURED"
    assert Payment.objects.count() == 0


# ==============================================================================
# 4. Robokassa ResultURL Callback Tests
# ==============================================================================


@pytest.mark.django_db
def test_robokassa_result_success_activates_subscription(
    api_client, user, plan, settings
):
    settings.ROBOKASSA_TEST_PASSWORD_2 = "pass_two_test"
    settings.ROBOKASSA_PASSWORD_2 = "live_pass_2"
    settings.ROBOKASSA_HASH_ALGORITHM = "sha256"

    payment, _ = create_payment(user=user, plan_id=plan.id)
    out_sum = "990.00"
    sig = calculate_result_signature(
        out_sum=out_sum,
        inv_id=payment.id,
        password_2="pass_two_test",
        hash_algorithm="sha256",
    )

    response = api_client.post(
        "/api/v1/subscriptions/payments/robokassa/result/",
        {
            "OutSum": out_sum,
            "InvId": str(payment.id),
            "SignatureValue": sig,
        },
    )
    assert response.status_code == 200
    assert response.content.decode("utf-8") == f"OK{payment.id}"

    payment.refresh_from_db()
    assert payment.status == Payment.Status.SUCCEEDED
    assert payment.paid_at is not None
    assert payment.subscription is not None

    sub = payment.subscription
    assert sub.user == user
    assert sub.plan == plan
    assert sub.status == Subscription.Status.ACTIVE
    assert sub.expires_at > sub.starts_at
    assert sub.expires_at - sub.starts_at == timedelta(days=30)
    assert has_paid_content_entitlement(user)


@pytest.mark.django_db
def test_robokassa_result_idempotent_duplicate_callback(
    api_client, user, plan, settings
):
    settings.ROBOKASSA_TEST_PASSWORD_2 = "pass_two_test"
    settings.ROBOKASSA_PASSWORD_2 = "live_pass_2"
    settings.ROBOKASSA_HASH_ALGORITHM = "sha256"

    payment, _ = create_payment(user=user, plan_id=plan.id)
    out_sum = "990.00"
    sig = calculate_result_signature(
        out_sum=out_sum,
        inv_id=payment.id,
        password_2="pass_two_test",
        hash_algorithm="sha256",
    )

    payload = {
        "OutSum": out_sum,
        "InvId": str(payment.id),
        "SignatureValue": sig,
    }

    # First callback
    resp1 = api_client.post("/api/v1/subscriptions/payments/robokassa/result/", payload)
    assert resp1.status_code == 200
    assert resp1.content.decode("utf-8") == f"OK{payment.id}"

    payment.refresh_from_db()
    original_paid_at = payment.paid_at
    original_sub_id = payment.subscription_id

    # Second callback (retry from provider)
    resp2 = api_client.post("/api/v1/subscriptions/payments/robokassa/result/", payload)
    assert resp2.status_code == 200
    assert resp2.content.decode("utf-8") == f"OK{payment.id}"

    payment.refresh_from_db()
    assert payment.paid_at == original_paid_at
    assert payment.subscription_id == original_sub_id
    assert Subscription.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_robokassa_result_invalid_signature_rejected(api_client, user, plan, settings):
    settings.ROBOKASSA_TEST_PASSWORD_2 = "pass_two_test"
    settings.ROBOKASSA_PASSWORD_2 = "live_pass_2"

    payment, _ = create_payment(user=user, plan_id=plan.id)

    response = api_client.post(
        "/api/v1/subscriptions/payments/robokassa/result/",
        {
            "OutSum": "990.00",
            "InvId": str(payment.id),
            "SignatureValue": "bad_signature_hash",
        },
    )
    assert response.status_code == 400
    assert "bad request: bad signature" in response.content.decode("utf-8")

    payment.refresh_from_db()
    assert payment.status == Payment.Status.PENDING
    assert payment.subscription is None
    assert not has_paid_content_entitlement(user)


@pytest.mark.django_db
def test_robokassa_result_cannot_succeed_when_password_2_is_empty(
    api_client, user, plan, settings
):
    settings.ROBOKASSA_MERCHANT_LOGIN = "test_merchant"
    settings.ROBOKASSA_PASSWORD_1 = "test_pass_1"
    settings.ROBOKASSA_TEST_PASSWORD_2 = "pass_two_test"
    settings.ROBOKASSA_PASSWORD_2 = "live_pass_2"

    payment, _ = create_payment(user=user, plan_id=plan.id)

    # Now password_2 is empty (e.g. misconfiguration in production)
    settings.ROBOKASSA_PASSWORD_2 = ""
    settings.ROBOKASSA_TEST_PASSWORD_2 = ""

    # Attacker tries to compute signature with empty password
    forged_sig = hashlib.sha256(f"990.00:{payment.id}:".encode()).hexdigest()

    response = api_client.post(
        "/api/v1/subscriptions/payments/robokassa/result/",
        {
            "OutSum": "990.00",
            "InvId": str(payment.id),
            "SignatureValue": forged_sig,
        },
    )
    assert response.status_code == 400
    assert "bad request: bad signature" in response.content.decode("utf-8")

    payment.refresh_from_db()
    assert payment.status == Payment.Status.PENDING
    assert payment.subscription is None
    assert not has_paid_content_entitlement(user)


@pytest.mark.django_db
def test_robokassa_result_amount_mismatch_rejected(api_client, user, plan, settings):
    settings.ROBOKASSA_TEST_PASSWORD_2 = "pass_two_test"
    settings.ROBOKASSA_PASSWORD_2 = "live_pass_2"

    payment, _ = create_payment(user=user, plan_id=plan.id)
    wrong_sum = "500.00"  # Plan was 990.00
    sig = calculate_result_signature(
        out_sum=wrong_sum,
        inv_id=payment.id,
        password_2="pass_two_test",
    )

    response = api_client.post(
        "/api/v1/subscriptions/payments/robokassa/result/",
        {
            "OutSum": wrong_sum,
            "InvId": str(payment.id),
            "SignatureValue": sig,
        },
    )
    assert response.status_code == 400
    assert "bad request: amount mismatch" in response.content.decode("utf-8")

    payment.refresh_from_db()
    assert payment.status == Payment.Status.PENDING
    assert payment.subscription is None


@pytest.mark.django_db
def test_robokassa_result_unknown_inv_id_rejected(api_client, settings):
    settings.ROBOKASSA_TEST_PASSWORD_2 = "pass_two_test"
    settings.ROBOKASSA_PASSWORD_2 = "live_pass_2"

    unknown_id = 999999
    out_sum = "990.00"
    sig = calculate_result_signature(
        out_sum=out_sum,
        inv_id=unknown_id,
        password_2="pass_two_test",
    )

    response = api_client.post(
        "/api/v1/subscriptions/payments/robokassa/result/",
        {
            "OutSum": out_sum,
            "InvId": str(unknown_id),
            "SignatureValue": sig,
        },
    )
    assert response.status_code == 400
    assert "bad request: payment not found" in response.content.decode("utf-8")


@pytest.mark.django_db
def test_robokassa_result_missing_parameters_rejected(api_client):
    response = api_client.post(
        "/api/v1/subscriptions/payments/robokassa/result/",
        {"InvId": "1"},
    )
    assert response.status_code == 400
    assert "bad request: missing parameters" in response.content.decode("utf-8")


@pytest.mark.django_db
def test_robokassa_result_get_fallback_success(api_client, user, plan, settings):
    settings.ROBOKASSA_TEST_PASSWORD_2 = "pass_two_test"
    settings.ROBOKASSA_PASSWORD_2 = "live_pass_2"
    settings.ROBOKASSA_HASH_ALGORITHM = "sha256"

    payment, _ = create_payment(user=user, plan_id=plan.id)
    out_sum = "990.00"
    sig = calculate_result_signature(
        out_sum=out_sum,
        inv_id=payment.id,
        password_2="pass_two_test",
        hash_algorithm="sha256",
    )

    response = api_client.get(
        f"/api/v1/subscriptions/payments/robokassa/result/?OutSum={out_sum}&InvId={payment.id}&SignatureValue={sig}"
    )
    assert response.status_code == 200
    assert response.content.decode("utf-8") == f"OK{payment.id}"

    payment.refresh_from_db()
    assert payment.status == Payment.Status.SUCCEEDED


@pytest.mark.django_db
def test_robokassa_overlapping_subscriptions(user, plan, settings):
    settings.ROBOKASSA_TEST_PASSWORD_2 = "pass_two_test"
    settings.ROBOKASSA_PASSWORD_2 = "live_pass_2"

    # User already has an active subscription expiring in 5 days
    now = timezone.now()
    sub1 = Subscription.objects.create(
        user=user,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        starts_at=now - timedelta(days=25),
        expires_at=now + timedelta(days=5),
    )

    # User purchases another plan
    payment, _ = create_payment(user=user, plan_id=plan.id)
    sig = calculate_result_signature(
        out_sum="990.00",
        inv_id=payment.id,
        password_2="pass_two_test",
    )

    success, msg = process_robokassa_result(
        inv_id=payment.id,
        out_sum="990.00",
        signature=sig,
    )
    assert success is True
    assert msg == f"OK{payment.id}"

    payment.refresh_from_db()

    # Verify both subscriptions exist
    subs = Subscription.objects.filter(user=user).order_by("id")
    assert subs.count() == 2
    assert has_paid_content_entitlement(user)

    # Active subscription selector deterministically picks latest expires_at
    active_sub = get_active_subscription(user)
    assert active_sub.id == payment.subscription_id
    assert active_sub.expires_at > sub1.expires_at


# ==============================================================================
# 5. UX Landing Endpoints (SuccessURL / FailURL)
# ==============================================================================


@pytest.mark.django_db
def test_robokassa_success_and_fail_views(api_client):
    success_resp = api_client.get("/api/v1/subscriptions/payments/robokassa/success/")
    assert success_resp.status_code == 200
    assert success_resp.json()["status"] == "success"

    fail_resp = api_client.get("/api/v1/subscriptions/payments/robokassa/fail/")
    assert fail_resp.status_code == 200
    assert fail_resp.json()["status"] == "failed"


# ==============================================================================
# 6. Robokassa System Checks Tests
# ==============================================================================


def test_robokassa_system_checks_in_production(settings):
    from apps.subscriptions.checks import check_robokassa_configuration

    settings.DEBUG = False
    settings.ROBOKASSA_MERCHANT_LOGIN = ""
    settings.ROBOKASSA_PASSWORD_1 = ""
    settings.ROBOKASSA_TEST_PASSWORD_1 = ""
    settings.ROBOKASSA_PASSWORD_2 = ""
    settings.ROBOKASSA_TEST_PASSWORD_2 = ""
    settings.ROBOKASSA_HASH_ALGORITHM = "sha256"
    settings.ROBOKASSA_TEST_MODE = False

    errors = check_robokassa_configuration(None)
    assert len(errors) == 1
    assert errors[0].id == "subscriptions.E002"

    settings.ROBOKASSA_HASH_ALGORITHM = "unsupported_algo"
    errors = check_robokassa_configuration(None)
    error_ids = {e.id for e in errors}
    assert "subscriptions.E001" in error_ids
    assert "subscriptions.E002" in error_ids


def test_robokassa_system_check_warns_when_test_mode_enabled_in_production(settings):
    from django.core.checks import Warning as CheckWarning

    from apps.subscriptions.checks import check_robokassa_configuration

    settings.DEBUG = False
    settings.ROBOKASSA_MERCHANT_LOGIN = "merchant"
    settings.ROBOKASSA_PASSWORD_1 = "password-1"
    settings.ROBOKASSA_PASSWORD_2 = "password-2"
    settings.ROBOKASSA_TEST_PASSWORD_1 = "test-pass-1"
    settings.ROBOKASSA_TEST_PASSWORD_2 = "test-pass-2"
    settings.ROBOKASSA_HASH_ALGORITHM = "sha256"
    settings.ROBOKASSA_TEST_MODE = True

    messages = check_robokassa_configuration(None)

    assert {message.id for message in messages} == {"subscriptions.W001"}
    assert isinstance(messages[0], CheckWarning)


@pytest.mark.django_db
def test_test_mode_uses_test_passwords_for_checkout_and_result(user, plan, settings):
    settings.ROBOKASSA_TEST_MODE = True
    settings.ROBOKASSA_PASSWORD_1 = "live_pass_1"
    settings.ROBOKASSA_PASSWORD_2 = "live_pass_2"
    settings.ROBOKASSA_TEST_PASSWORD_1 = "cabinet_test_1"
    settings.ROBOKASSA_TEST_PASSWORD_2 = "cabinet_test_2"

    payment = Payment.objects.create(
        user=user,
        plan=plan,
        amount=plan.price_rub,
        status=Payment.Status.PENDING,
    )
    out_sum = "990.00"
    receipt_json = serialize_receipt(payment)
    test_checkout = calculate_payment_signature(
        merchant_login="test_merchant",
        out_sum=out_sum,
        inv_id=payment.pk,
        password_1="cabinet_test_1",
        receipt=receipt_json,
    )
    live_checkout = calculate_payment_signature(
        merchant_login="test_merchant",
        out_sum=out_sum,
        inv_id=payment.pk,
        password_1="live_pass_1",
        receipt=receipt_json,
    )
    url = build_payment_url(payment)
    params = parse_qs(urlparse(url).query)
    assert params["SignatureValue"] == [test_checkout]
    assert params["SignatureValue"] != [live_checkout]
    assert params["IsTest"] == ["1"]

    live_result = calculate_result_signature(
        out_sum=out_sum, inv_id=payment.pk, password_2="live_pass_2"
    )
    test_result = calculate_result_signature(
        out_sum=out_sum, inv_id=payment.pk, password_2="cabinet_test_2"
    )
    assert verify_result_signature(out_sum, payment.pk, test_result) is True
    assert verify_result_signature(out_sum, payment.pk, live_result) is False

    settings.ROBOKASSA_TEST_MODE = False
    live_url = build_payment_url(payment)
    live_params = parse_qs(urlparse(live_url).query)
    assert live_params["SignatureValue"] == [live_checkout]
    assert "IsTest" not in live_params
    assert verify_result_signature(out_sum, payment.pk, live_result) is True
    assert verify_result_signature(out_sum, payment.pk, test_result) is False


def test_production_check_requires_test_passwords_in_test_mode(settings):
    from apps.subscriptions.checks import check_robokassa_configuration

    settings.DEBUG = False
    settings.ROBOKASSA_MERCHANT_LOGIN = "merchant"
    settings.ROBOKASSA_PASSWORD_1 = "password-1"
    settings.ROBOKASSA_PASSWORD_2 = "password-2"
    settings.ROBOKASSA_TEST_PASSWORD_1 = ""
    settings.ROBOKASSA_TEST_PASSWORD_2 = ""
    settings.ROBOKASSA_HASH_ALGORITHM = "sha256"
    settings.ROBOKASSA_TEST_MODE = True

    error_ids = {message.id for message in check_robokassa_configuration(None)}
    assert "subscriptions.E003" in error_ids
    assert "subscriptions.W001" in error_ids


# ==============================================================================
# 7. Fiscalization Receipt (FZ-54) & Signature Tests
# ==============================================================================


@pytest.mark.django_db
def test_build_receipt_structure_and_invariants(user, plan):
    payment = Payment.objects.create(
        user=user,
        plan=plan,
        amount=plan.price_rub,
        status=Payment.Status.PENDING,
    )

    receipt = build_receipt(payment)
    assert "items" in receipt
    assert len(receipt["items"]) == 1

    item = receipt["items"][0]
    assert item["quantity"] == 1
    assert item["sum"] == Decimal("990.00")
    assert item["payment_method"] == "full_payment"
    assert item["payment_object"] == "service"
    assert item["tax"] == "none"
    assert (
        item["name"]
        == f"Доступ к образовательной платформе Medcore — {plan.duration_days} дней"
    )
    assert str(plan.id) not in item["name"]
    assert plan.code not in item["name"]


@pytest.mark.django_db
def test_receipt_decimal_money_precision_399_90(user):
    plan_399 = Plan.objects.create(
        code="plan-399",
        title="Спец-тариф 399.90",
        price_rub=Decimal("399.90"),
        duration_days=30,
        is_active=True,
    )
    payment = Payment.objects.create(
        user=user,
        plan=plan_399,
        amount=plan_399.price_rub,
        status=Payment.Status.PENDING,
    )

    serialized = serialize_receipt(payment)
    assert '"sum":399.90' in serialized

    parsed = json.loads(serialized)
    assert parsed["items"][0]["quantity"] == 1
    assert Decimal(str(parsed["items"][0]["sum"])) == Decimal("399.90")

    url = build_payment_url(payment)
    parsed_url = urlparse(url)
    params = parse_qs(parsed_url.query)
    assert params["OutSum"] == ["399.90"]

    url_receipt_encoded = params["Receipt"][0]
    assert url_receipt_encoded.startswith("%7B")
    url_receipt_json = urllib.parse.unquote(url_receipt_encoded)
    url_parsed_receipt = json.loads(url_receipt_json)
    assert Decimal(str(url_parsed_receipt["items"][0]["sum"])) == Decimal("399.90")


@pytest.mark.django_db
def test_serialize_receipt_deterministic_and_cyrillic(user, plan):
    payment = Payment.objects.create(
        user=user,
        plan=plan,
        amount=plan.price_rub,
        status=Payment.Status.PENDING,
    )

    s1 = serialize_receipt(payment)
    s2 = serialize_receipt(payment)
    assert s1 == s2
    assert "Доступ к образовательной платформе Medcore" in s1
    assert "\\u04" not in s1


def test_signature_calculation_with_receipt():
    merchant_login = "test_merchant"
    out_sum = "990.00"
    inv_id = 42
    pwd_1 = "test_secret"
    receipt_json = (
        '{"items":[{"name":"Услуга","quantity":1,"sum":990.00,"tax":"none"}]}'
    )
    encoded_receipt = urllib.parse.quote(receipt_json, safe="")

    expected_sha256 = (
        hashlib.sha256(
            f"{merchant_login}:{out_sum}:{inv_id}:{encoded_receipt}:{pwd_1}".encode()
        )
        .hexdigest()
        .lower()
    )

    # Pass pre-encoded receipt
    sig_encoded = calculate_payment_signature(
        merchant_login=merchant_login,
        out_sum=out_sum,
        inv_id=inv_id,
        password_1=pwd_1,
        receipt=encoded_receipt,
        hash_algorithm="sha256",
    )
    assert sig_encoded == expected_sha256

    # Pass raw JSON string: calculate_payment_signature must automatically encode it
    sig_raw = calculate_payment_signature(
        merchant_login=merchant_login,
        out_sum=out_sum,
        inv_id=inv_id,
        password_1=pwd_1,
        receipt=receipt_json,
        hash_algorithm="sha256",
    )
    assert sig_raw == expected_sha256

    # MD5 support
    expected_md5 = (
        hashlib.md5(
            f"{merchant_login}:{out_sum}:{inv_id}:{encoded_receipt}:{pwd_1}".encode()
        )
        .hexdigest()
        .lower()
    )
    sig_md5 = calculate_payment_signature(
        merchant_login=merchant_login,
        out_sum=out_sum,
        inv_id=inv_id,
        password_1=pwd_1,
        receipt=encoded_receipt,
        hash_algorithm="md5",
    )
    assert sig_md5 == expected_md5


def test_signature_sensitivity_to_each_parameter():
    merchant_login = "test_merchant"
    out_sum = "990.00"
    inv_id = 42
    pwd_1 = "test_secret"
    receipt_1 = '{"items":[{"name":"Услуга 1","quantity":1,"sum":990.00,"tax":"none"}]}'
    receipt_2 = '{"items":[{"name":"Услуга 2","quantity":1,"sum":990.00,"tax":"none"}]}'

    base_sig = calculate_payment_signature(
        merchant_login=merchant_login,
        out_sum=out_sum,
        inv_id=inv_id,
        password_1=pwd_1,
        receipt=receipt_1,
    )

    # Changing Receipt changes signature
    assert (
        calculate_payment_signature(
            merchant_login=merchant_login,
            out_sum=out_sum,
            inv_id=inv_id,
            password_1=pwd_1,
            receipt=receipt_2,
        )
        != base_sig
    )

    # Changing OutSum changes signature
    assert (
        calculate_payment_signature(
            merchant_login=merchant_login,
            out_sum="991.00",
            inv_id=inv_id,
            password_1=pwd_1,
            receipt=receipt_1,
        )
        != base_sig
    )

    # Changing InvId changes signature
    assert (
        calculate_payment_signature(
            merchant_login=merchant_login,
            out_sum=out_sum,
            inv_id=43,
            password_1=pwd_1,
            receipt=receipt_1,
        )
        != base_sig
    )

    # Changing password changes signature
    assert (
        calculate_payment_signature(
            merchant_login=merchant_login,
            out_sum=out_sum,
            inv_id=inv_id,
            password_1="different_pwd",
            receipt=receipt_1,
        )
        != base_sig
    )


@pytest.mark.django_db
def test_build_payment_url_get_flow_and_signature_verification(user, plan, settings):
    payment = Payment.objects.create(
        user=user,
        plan=plan,
        amount=plan.price_rub,
        status=Payment.Status.PENDING,
    )

    url = build_payment_url(payment)
    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "auth.robokassa.ru"
    assert parsed.path == "/Merchant/Index.aspx"

    raw_query = parsed.query
    # In GET-flow, receipt_encoded (%7B...) is transport-encoded in query string,
    # so raw_query legitimately contains %257B and %2522.
    assert "%257B" in raw_query
    assert "%2522" in raw_query

    params = parse_qs(raw_query)
    for expected_key in (
        "MerchantLogin",
        "OutSum",
        "InvId",
        "Description",
        "Receipt",
        "SignatureValue",
        "IsTest",
    ):
        assert expected_key in params

    # After standard URL-decoding by parse_qs (just like Robokassa does on GET),
    # params["Receipt"][0] remains percent-encoded matching the value used in signature
    # calculation.
    receipt_param = params["Receipt"][0]
    assert receipt_param.startswith("%7B%22")
    assert "%22items%22" in receipt_param

    # Recalculate signature directly from the parsed parameters received by Robokassa:
    recalculated_sig = calculate_payment_signature(
        merchant_login=params["MerchantLogin"][0],
        out_sum=params["OutSum"][0],
        inv_id=params["InvId"][0],
        password_1=settings.ROBOKASSA_TEST_PASSWORD_1,
        receipt=receipt_param,
        hash_algorithm=settings.ROBOKASSA_HASH_ALGORITHM,
    )
    assert params["SignatureValue"][0] == recalculated_sig

    # Unquoting the percent-encoded parameter yields valid JSON with preserved Cyrillic
    decoded_json = urllib.parse.unquote(receipt_param)
    data = json.loads(decoded_json)
    assert (
        data["items"][0]["name"]
        == f"Доступ к образовательной платформе Medcore — {plan.duration_days} дней"
    )
    assert data["items"][0]["quantity"] == 1
    assert data["items"][0]["sum"] == 990.00
    assert data["items"][0]["tax"] == "none"
    assert data["items"][0]["payment_method"] == "full_payment"
    assert data["items"][0]["payment_object"] == "service"


@pytest.mark.django_db
def test_build_payment_url_live_vs_test_mode(user, plan, settings):
    payment = Payment.objects.create(
        user=user,
        plan=plan,
        amount=plan.price_rub,
        status=Payment.Status.PENDING,
    )

    # Test mode
    settings.ROBOKASSA_TEST_MODE = True
    test_url = build_payment_url(payment)
    test_params = parse_qs(urlparse(test_url).query)
    assert test_params["IsTest"] == ["1"]
    assert "Receipt" in test_params

    # Live mode
    settings.ROBOKASSA_TEST_MODE = False
    live_url = build_payment_url(payment)
    live_params = parse_qs(urlparse(live_url).query)
    assert "IsTest" not in live_params
    assert "Receipt" in live_params


@pytest.mark.django_db
def test_build_payment_url_without_user_email(plan):
    payment = Payment.objects.create(
        user=None,
        plan=plan,
        amount=plan.price_rub,
        status=Payment.Status.PENDING,
    )
    url = build_payment_url(payment)
    params = parse_qs(urlparse(url).query)
    assert "Email" not in params
    assert "Receipt" in params
    assert "SignatureValue" in params
