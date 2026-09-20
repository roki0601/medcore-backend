from __future__ import annotations

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    OpenApiTypes,
    extend_schema,
)
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import APIError
from apps.common.serializers import APIErrorResponseSerializer

from .serializers import (
    AuthTokenResponseSerializer,
    DeleteAccountSerializer,
    RefreshTokenResponseSerializer,
    TelegramLoginRequestSerializer,
    UserProfileSerializer,
    UserProfileUpdateSerializer,
    UserSummarySerializer,
    UserUpdateSerializer,
)
from .services import (
    authenticate_telegram,
    delete_account,
    get_or_create_profile,
    refresh_access_token,
    revoke_all_sessions,
    revoke_refresh_session,
    update_profile,
    update_username,
)
from .throttles import (
    AccountMutationThrottle,
    RefreshIPThrottle,
    RefreshSessionThrottle,
    TelegramLoginClaimThrottle,
    TelegramLoginIPThrottle,
)

ERROR_RESPONSES = {
    400: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Invalid request."
    ),
    401: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Authentication failed."
    ),
    403: OpenApiResponse(
        response=APIErrorResponseSerializer, description="CSRF or permission failure."
    ),
    409: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Username conflict."
    ),
    422: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Validation failure."
    ),
    429: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Too many requests."
    ),
}

CSRF_HEADER_PARAMETER = OpenApiParameter(
    name="X-CSRFToken",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.HEADER,
    required=True,
    description="Django CSRF token returned by GET /api/v1/auth/csrf/.",
)
REFRESH_COOKIE_PARAMETER = OpenApiParameter(
    name=settings.AUTH_REFRESH_COOKIE_NAME,
    type=OpenApiTypes.STR,
    location=OpenApiParameter.COOKIE,
    required=True,
    description="HttpOnly refresh cookie set by Telegram login.",
)


def _set_refresh_cookie(response: Response, value: str) -> None:
    response.set_cookie(
        key=settings.AUTH_REFRESH_COOKIE_NAME,
        value=value,
        max_age=settings.AUTH_REFRESH_COOKIE_MAX_AGE,
        httponly=True,
        secure=settings.AUTH_REFRESH_COOKIE_SECURE,
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.AUTH_REFRESH_COOKIE_NAME,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
    )


@method_decorator(csrf_protect, name="dispatch")
class TelegramLoginView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (TelegramLoginIPThrottle, TelegramLoginClaimThrottle)

    @extend_schema(
        request=TelegramLoginRequestSerializer,
        responses={200: AuthTokenResponseSerializer, **ERROR_RESPONSES},
        parameters=[CSRF_HEADER_PARAMETER],
        description=(
            "Verify a legacy Telegram Login Widget payload and issue access "
            "plus HttpOnly refresh credentials. Requires CSRF bootstrap."
        ),
    )
    def post(self, request):
        serializer = TelegramLoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, token_pair = authenticate_telegram(serializer.validated_data)
        response = Response(
            {
                "access_token": token_pair.access_token,
                "expires_in": token_pair.access_expires_in,
                "user": UserSummarySerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )
        _set_refresh_cookie(response, token_pair.refresh_token)
        return response


@method_decorator(csrf_protect, name="dispatch")
class RefreshTokenView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (RefreshIPThrottle, RefreshSessionThrottle)

    @extend_schema(
        request=None,
        parameters=[REFRESH_COOKIE_PARAMETER, CSRF_HEADER_PARAMETER],
        responses={200: RefreshTokenResponseSerializer, **ERROR_RESPONSES},
        description=(
            "Refresh the access JWT using the non-rotating HttpOnly cookie and "
            "CSRF header."
        ),
    )
    def post(self, request):
        raw_refresh_token = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME)
        if not raw_refresh_token:
            raise APIError(
                "Refresh cookie is required.",
                code="AUTHENTICATION_REQUIRED",
                status_code=401,
            )
        try:
            access_token, expires_in = refresh_access_token(raw_refresh_token)
        except APIError as exc:
            if exc.default_code != "AUTH_REFRESH_REVOKED":
                raise
            response = Response(
                {
                    "code": exc.default_code,
                    "detail": str(exc.detail),
                    "fields": exc.fields,
                },
                status=exc.status_code,
            )
            _clear_refresh_cookie(response)
            return response
        return Response(
            {"access_token": access_token, "expires_in": expires_in},
            status=status.HTTP_200_OK,
        )


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (AccountMutationThrottle,)

    @extend_schema(
        request=None,
        parameters=[REFRESH_COOKIE_PARAMETER, CSRF_HEADER_PARAMETER],
        responses={204: None, **ERROR_RESPONSES},
        description="Revoke the current refresh session and clear its cookie.",
    )
    def post(self, request):
        revoke_refresh_session(request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME))
        response = Response(status=status.HTTP_204_NO_CONTENT)
        _clear_refresh_cookie(response)
        return response


class LogoutAllView(APIView):
    permission_classes = (IsAuthenticated,)
    throttle_classes = (AccountMutationThrottle,)

    @extend_schema(
        request=None,
        responses={204: None, **ERROR_RESPONSES},
        description="Revoke every refresh session owned by the current User.",
    )
    def post(self, request):
        revoke_all_sessions(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = (IsAuthenticated,)

    def get_throttles(self):
        if self.request.method in {"PATCH", "DELETE"}:
            return [AccountMutationThrottle()]
        return []

    @extend_schema(
        responses={200: UserSummarySerializer, **ERROR_RESPONSES},
        description="Return the current authenticated User summary.",
    )
    def get(self, request):
        return Response(UserSummarySerializer(request.user).data)

    @extend_schema(
        request=UserUpdateSerializer,
        responses={200: UserSummarySerializer, **ERROR_RESPONSES},
        description="Change only the current User's application username.",
    )
    def patch(self, request):
        serializer = UserUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = update_username(request.user, serializer.validated_data["username"])
        return Response(UserSummarySerializer(user).data)

    @extend_schema(
        request=DeleteAccountSerializer,
        responses={204: None, **ERROR_RESPONSES},
        description=(
            "Delete the current account after explicit confirmation. A stale "
            "credential after hard deletion receives 401."
        ),
    )
    def delete(self, request):
        serializer = DeleteAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        delete_account(request.user)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        _clear_refresh_cookie(response)
        return response


class ProfileView(APIView):
    permission_classes = (IsAuthenticated,)

    def get_throttles(self):
        if self.request.method == "PATCH":
            return [AccountMutationThrottle()]
        return []

    @extend_schema(
        responses={200: UserProfileSerializer, **ERROR_RESPONSES},
        description=(
            "Retrieve the current authenticated user's profile and study preferences."
        ),
    )
    def get(self, request):
        profile = get_or_create_profile(request.user)
        return Response(UserProfileSerializer(profile).data)

    @extend_schema(
        request=UserProfileUpdateSerializer,
        responses={200: UserProfileSerializer, **ERROR_RESPONSES},
        description=(
            "Partially update the current authenticated user's profile and "
            "study preferences."
        ),
    )
    def patch(self, request):
        serializer = UserProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        kwargs = {}
        if "university" in data:
            kwargs["university"] = data["university"]
        if "course" in data:
            kwargs["course"] = data["course"]
        if "semester_goal" in data:
            kwargs["semester_goal"] = data["semester_goal"]
        if "daily_study_minutes" in data:
            kwargs["daily_study_minutes"] = data["daily_study_minutes"]
        if "validated_subject_ids" in data:
            kwargs["subject_ids"] = data["validated_subject_ids"]

        profile = update_profile(request.user, **kwargs)
        return Response(UserProfileSerializer(profile).data)
