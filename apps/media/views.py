from __future__ import annotations

from django.conf import settings
from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.common.exceptions import APIError
from apps.common.integration import HasIntegrationKey, IntegrationKeyAuthentication
from apps.common.permissions import IsContentAuthor, IsNotIntegrationClient
from apps.common.serializers import APIErrorResponseSerializer
from apps.media.models import MediaFile
from apps.media.serializers import (
    AccessUrlSerializer,
    MediaSerializer,
    MediaWriteSerializer,
    UploadUrlSerializer,
)
from apps.media.services import (
    accept_controlled_upload,
    create_media_file,
    delete_media_file,
    get_media_file,
    issue_access_url,
    issue_upload_url,
    open_controlled_download,
    validate_upload_token,
)
from apps.users.authentication import VersionedJWTAuthentication

#: Authoring routes accept the integration key or an editor/admin JWT. The
#: integration authenticator runs first so a present-but-wrong key hard-fails
#: instead of falling through to the JWT path.
MEDIA_AUTHORING_AUTHENTICATION = (
    IntegrationKeyAuthentication,
    VersionedJWTAuthentication,
)
MEDIA_AUTHORING_PERMISSIONS = (HasIntegrationKey | IsContentAuthor,)

#: ``access-url`` accepts the same credentials but refuses the integration
#: principal; anonymous actors are allowed so public media stays readable.
MEDIA_ACCESS_PERMISSIONS = (IsNotIntegrationClient,)

#: The two controlled endpoints have no authenticator: the capability token in
#: the URL is the credential.
MEDIA_CONTROLLED_AUTHENTICATION = ()
MEDIA_CONTROLLED_PERMISSIONS = (AllowAny,)

#: Named in every operation description of the authoring surface.
MEDIA_AUTHORING_PERMISSION = "Permission: integration key or editor/admin JWT."

MEDIA_AUTHORING_ERROR_RESPONSES = {
    400: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Invalid request."
    ),
    401: OpenApiResponse(
        response=APIErrorResponseSerializer,
        description="Integration key invalid, or authentication missing.",
    ),
    403: OpenApiResponse(
        response=APIErrorResponseSerializer,
        description="The authenticated user is not an editor or an admin.",
    ),
    404: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Resource not found."
    ),
    409: OpenApiResponse(
        response=APIErrorResponseSerializer,
        description="Media is referenced by published content.",
    ),
    422: OpenApiResponse(
        response=APIErrorResponseSerializer,
        description="Invalid payload, MIME type or size.",
    ),
    429: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Too many requests."
    ),
}

#: The upload contract of one media row refuses a row whose object already
#: exists, so its 409 means "already uploaded" instead of "still referenced".
MEDIA_UPLOAD_URL_ERROR_RESPONSES = {
    **MEDIA_AUTHORING_ERROR_RESPONSES,
    409: OpenApiResponse(
        response=APIErrorResponseSerializer,
        description="The media object is already uploaded.",
    ),
}

MEDIA_ACCESS_ERROR_RESPONSES = {
    401: OpenApiResponse(
        response=APIErrorResponseSerializer,
        description="Authentication required, or the capability token is invalid.",
    ),
    403: OpenApiResponse(
        response=APIErrorResponseSerializer,
        description="Media access denied, or the integration key is out of scope.",
    ),
    404: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Resource not found."
    ),
    422: OpenApiResponse(
        response=APIErrorResponseSerializer,
        description="The stored object is missing or mismatched.",
    ),
    429: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Too many requests."
    ),
}

MEDIA_CONTROLLED_ERROR_RESPONSES = {
    401: OpenApiResponse(
        response=APIErrorResponseSerializer,
        description="The capability token is invalid or expired.",
    ),
    404: OpenApiResponse(
        response=APIErrorResponseSerializer,
        description="Resource not found, or the backend has no controlled contract.",
    ),
    422: OpenApiResponse(
        response=APIErrorResponseSerializer,
        description=(
            "The uploaded body exceeds the configured limit, or the uploaded "
            "bytes do not match the metadata."
        ),
    ),
    429: OpenApiResponse(
        response=APIErrorResponseSerializer, description="Too many requests."
    ),
}

MEDIA_PK_PARAMETER = OpenApiParameter(
    name="id",
    type=int,
    location=OpenApiParameter.PATH,
    description="Numeric identifier of the addressed media row.",
)
MEDIA_TOKEN_PARAMETER = OpenApiParameter(
    name="token",
    type=str,
    location=OpenApiParameter.PATH,
    description="Capability token bound to one operation, media row and expiry.",
)


def _not_found() -> APIError:
    return APIError("Resource not found.", code="RESOURCE_NOT_FOUND", status_code=404)


def _body_too_large(limit: int) -> APIError:
    return APIError(
        "The uploaded body exceeds the configured limit.",
        code="MEDIA_INVALID",
        status_code=422,
        fields={"size_bytes": [f"Ensure this value is at most {limit}."]},
    )


def _declared_content_length(request) -> int | None:
    """The ``Content-Length`` of the request, when the client declared one."""

    raw = request.META.get("CONTENT_LENGTH")
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _get_media_or_404(pk: int) -> MediaFile:
    media = get_media_file(pk)
    if media is None:
        raise _not_found()
    return media


def _base_url(request) -> str:
    """Scheme and host of the request, without its path or trailing slash."""

    return request.build_absolute_uri("/").rstrip("/")


@extend_schema(
    request=MediaWriteSerializer,
    responses={201: MediaSerializer, **MEDIA_AUTHORING_ERROR_RESPONSES},
    description=(
        "Create the metadata row of one media object; the binary is uploaded "
        "afterwards through the upload contract. The object key is generated "
        "server-side and never returned. "
        f"{MEDIA_AUTHORING_PERMISSION}"
    ),
)
class MediaListCreateView(generics.GenericAPIView):
    authentication_classes = MEDIA_AUTHORING_AUTHENTICATION
    permission_classes = MEDIA_AUTHORING_PERMISSIONS
    throttle_scope = "media_upload"
    serializer_class = MediaWriteSerializer

    def post(self, request):
        serializer = MediaWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        media = create_media_file(**serializer.validated_data)
        return Response(MediaSerializer(media).data, status=201)


@extend_schema_view(
    get=extend_schema(
        request=None,
        parameters=[MEDIA_PK_PARAMETER],
        responses={200: MediaSerializer, **MEDIA_AUTHORING_ERROR_RESPONSES},
        description=f"Read the metadata of one media row. {MEDIA_AUTHORING_PERMISSION}",
    ),
    delete=extend_schema(
        request=None,
        parameters=[MEDIA_PK_PARAMETER],
        responses={
            204: OpenApiResponse(
                description="The row was deleted and storage cleanup was scheduled."
            ),
            **MEDIA_AUTHORING_ERROR_RESPONSES,
        },
        description=(
            "Delete one media row; a published content reference refuses the "
            "deletion with 409 CONTENT_CONFLICT and a repeated DELETE is 404 "
            f"RESOURCE_NOT_FOUND. {MEDIA_AUTHORING_PERMISSION}"
        ),
    ),
)
class MediaDetailView(generics.GenericAPIView):
    authentication_classes = MEDIA_AUTHORING_AUTHENTICATION
    permission_classes = MEDIA_AUTHORING_PERMISSIONS
    throttle_scope = "media_metadata"
    serializer_class = MediaSerializer

    def get(self, request, pk: int):
        return Response(MediaSerializer(_get_media_or_404(pk)).data)

    def delete(self, request, pk: int):
        delete_media_file(_get_media_or_404(pk))
        return Response(status=204)


@extend_schema(
    request=None,
    parameters=[MEDIA_PK_PARAMETER],
    responses={200: UploadUrlSerializer, **MEDIA_UPLOAD_URL_ERROR_RESPONSES},
    description=(
        "Issue the upload contract of one media row: a presigned PUT URL for the "
        "S3-compatible backend, or the controlled upload endpoint of the local "
        f"backend. {MEDIA_AUTHORING_PERMISSION}"
    ),
)
class MediaUploadUrlView(generics.GenericAPIView):
    authentication_classes = MEDIA_AUTHORING_AUTHENTICATION
    permission_classes = MEDIA_AUTHORING_PERMISSIONS
    throttle_scope = "media_upload"
    serializer_class = UploadUrlSerializer

    def get(self, request, pk: int):
        media = _get_media_or_404(pk)
        signed = issue_upload_url(media, base_url=_base_url(request))
        return Response(UploadUrlSerializer(signed).data)


@extend_schema(
    request=None,
    parameters=[MEDIA_PK_PARAMETER],
    responses={200: AccessUrlSerializer, **MEDIA_ACCESS_ERROR_RESPONSES},
    auth=[{}, {"bearerAuth": []}],
    description=(
        "Issue a short-lived read URL for one media row. Public media is signed "
        "for every actor; protected media requires the content-owned access "
        "decision, which is evaluated strictly before the object is verified and "
        "signed. Anonymous actors are allowed, the integration key is not."
    ),
)
class MediaAccessUrlView(generics.GenericAPIView):
    authentication_classes = MEDIA_AUTHORING_AUTHENTICATION
    permission_classes = MEDIA_ACCESS_PERMISSIONS
    throttle_scope = "media_access"
    serializer_class = AccessUrlSerializer

    def get(self, request, pk: int):
        media = _get_media_or_404(pk)
        signed = issue_access_url(
            media,
            actor=request.user,
            base_url=_base_url(request),
        )
        return Response(AccessUrlSerializer(signed).data)


@extend_schema(
    request=None,
    parameters=[MEDIA_TOKEN_PARAMETER],
    auth=[],
    responses={
        204: OpenApiResponse(description="The object was stored and verified."),
        **MEDIA_CONTROLLED_ERROR_RESPONSES,
    },
    description=(
        "Store the bytes of one capability-token upload. The token is the "
        "credential: it is bound to the upload operation, one media row, the PUT "
        "method and its expiry. The declared size (and checksum when present) "
        "must match, otherwise nothing is stored."
    ),
)
class MediaUploadReceiverView(generics.GenericAPIView):
    authentication_classes = MEDIA_CONTROLLED_AUTHENTICATION
    permission_classes = MEDIA_CONTROLLED_PERMISSIONS
    throttle_scope = "media_upload"

    def put(self, request, token: str):
        # The credential is checked before the body is buffered: a garbage token
        # with a huge Content-Length never allocates anything.
        validate_upload_token(token)
        declared = _declared_content_length(request)
        if declared is not None and declared > settings.MEDIA_MAX_UPLOAD_BYTES:
            raise _body_too_large(settings.MEDIA_MAX_UPLOAD_BYTES)
        accept_controlled_upload(token, request.body)
        return Response(status=204)


@extend_schema(
    request=None,
    parameters=[MEDIA_TOKEN_PARAMETER],
    auth=[],
    responses={
        200: OpenApiResponse(
            response=OpenApiTypes.BINARY,
            description="The stored object.",
        ),
        **MEDIA_CONTROLLED_ERROR_RESPONSES,
    },
    description=(
        "Read the object of one capability-token download. The token is the "
        "credential: it is bound to the download operation, one media row, the "
        "GET method and its expiry."
    ),
)
class MediaFileDownloadView(generics.GenericAPIView):
    authentication_classes = MEDIA_CONTROLLED_AUTHENTICATION
    permission_classes = MEDIA_CONTROLLED_PERMISSIONS
    throttle_scope = "media_access"

    def get(self, request, token: str):
        media, content = open_controlled_download(token)
        filename = media.original_name or f"media-{media.pk}"
        return FileResponse(
            content,
            content_type=media.mime_type,
            as_attachment=False,
            filename=filename,
        )
