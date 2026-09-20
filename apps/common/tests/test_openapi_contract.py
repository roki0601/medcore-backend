"""Public OpenAPI contracts shared by the backend and frontend clients."""

from __future__ import annotations

import pytest
from drf_spectacular.generators import SchemaGenerator


@pytest.fixture
def schema():
    return SchemaGenerator().get_schema(request=None, public=True)


def _operation(schema, path: str, method: str) -> dict:
    return schema["paths"][path][method]


def _response_schema(operation: dict, status: str) -> dict:
    return operation["responses"][status]["content"]["application/json"]["schema"]


def test_error_responses_use_the_shared_envelope(schema):
    error_ref = "#/components/schemas/APIErrorResponse"

    error_schema = schema["components"]["schemas"]["APIErrorResponse"]
    assert error_schema["required"] == ["code", "detail", "fields"]
    assert error_schema["properties"]["fields"]["type"] == "object"

    assert (
        _response_schema(
            _operation(schema, "/api/v1/topics/{topic_id}/progress/", "get"),
            "401",
        )["$ref"]
        == error_ref
    )
    assert (
        _response_schema(
            _operation(schema, "/api/v1/auth/token/refresh/", "post"), "401"
        )["$ref"]
        == error_ref
    )
    assert (
        _response_schema(_operation(schema, "/api/v1/content/blocks/", "post"), "400")[
            "$ref"
        ]
        == error_ref
    )
    assert (
        _response_schema(
            _operation(schema, "/api/v1/topics/{topic_id}/progress/", "patch"),
            "400",
        )["$ref"]
        == error_ref
    )
    assert (
        _response_schema(_operation(schema, "/api/v1/media/", "post"), "400")["$ref"]
        == error_ref
    )
    assert (
        _response_schema(
            _operation(schema, "/api/v1/media/{id}/access-url/", "get"), "403"
        )["$ref"]
        == error_ref
    )


def test_learning_attempt_schema_describes_json_payloads(schema):
    attempt = schema["components"]["schemas"]["QuizAttempt"]

    assert attempt["properties"]["question_ids"] == {
        "type": "array",
        "items": {"type": "integer"},
        "readOnly": True,
    }
    assert attempt["properties"]["results"]["type"] == "array"
    assert attempt["properties"]["results"]["nullable"] is True
    result = attempt["properties"]["results"]["items"]
    assert result["$ref"] == "#/components/schemas/QuizAttemptResult"


def test_auth_content_and_media_schemas_are_typed(schema):
    auth_response = schema["components"]["schemas"]["AuthTokenResponse"]
    assert "user" in auth_response["required"]

    block = schema["components"]["schemas"]["ContentBlock"]
    media_schema = block["properties"]["media"]
    media_ref = media_schema.get("$ref") or media_schema["allOf"][0]["$ref"]
    assert media_ref == "#/components/schemas/MediaReference"
    assert media_schema["nullable"] is True


def test_security_contracts_include_integration_key_and_optional_bearer(schema):
    security_schemes = schema["components"]["securitySchemes"]
    assert security_schemes["integrationKeyAuth"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-MedCore-Integration-Key",
    }

    authoring_security = _operation(schema, "/api/v1/content/subjects/", "post")[
        "security"
    ]
    assert {"integrationKeyAuth": []} in authoring_security
    assert {"bearerAuth": []} in authoring_security

    assert _operation(schema, "/api/v1/media/{id}/access-url/", "get")["security"] == [
        {},
        {"bearerAuth": []},
    ]
