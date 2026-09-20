"""OpenAPI coverage of the eleven learning routes (feature 003).

The contract requires ``drf-spectacular`` to expose every learning path with its
methods and response schemas, and to never expose answer correctness: no active
attempt payload and no quiz detail payload may contain ``is_correct``.
"""

from __future__ import annotations

import pytest
from drf_spectacular.generators import SchemaGenerator

LEARNING_SCHEMA_PATHS = {
    "/api/v1/dashboard/": {"get"},
    "/api/v1/topics/{topic_id}/progress/": {"get", "patch"},
    "/api/v1/topics/{topic_id}/blocks/{block_id}/complete/": {"post"},
    "/api/v1/topics/{topic_id}/flashcards/": {"get"},
    "/api/v1/flashcards/review-due/": {"get"},
    "/api/v1/flashcards/{id}/": {"get"},
    "/api/v1/flashcards/{id}/review/": {"post"},
    "/api/v1/topics/{topic_id}/quizzes/": {"get"},
    "/api/v1/quizzes/{id}/": {"get"},
    "/api/v1/quizzes/{id}/attempts/": {"post"},
    "/api/v1/quiz-attempts/{id}/": {"get", "patch"},
    "/api/v1/quiz-attempts/{id}/submit/": {"post"},
}

#: The learning components that carry questions/answers, the current review state
#: or the derived progress. They must be reachable from the learning paths,
#: otherwise the correctness assertion below would only walk opaque (untyped)
#: payloads. ``TopicQuizDetail`` also pins the learning quiz-detail schema: without
#: its explicit component name the route resolves to the ``content`` authoring
#: ``QuizDetail`` component instead.
EXPECTED_COMPONENTS = (
    "QuizAnswerRead",
    "QuizQuestionRead",
    "FlashcardReviewState",
    "TopicProgress",
    "QuizAttempt",
    "TopicQuiz",
    "TopicQuizDetail",
    "DashboardResponse",
)

_REF_PREFIX = "#/components/schemas/"

#: Schema keys whose values are prose or literals, not nested schemas.
_NON_SCHEMA_KEYS = frozenset(
    {"description", "title", "example", "examples", "default", "enum"}
)


def _component_names(node) -> set[str]:
    """Every ``components/schemas`` name referenced anywhere inside ``node``."""

    if isinstance(node, dict):
        names = set()
        for key, value in node.items():
            if (
                key == "$ref"
                and isinstance(value, str)
                and value.startswith(_REF_PREFIX)
            ):
                names.add(value[len(_REF_PREFIX) :])
            else:
                names |= _component_names(value)
        return names
    if isinstance(node, list):
        names = set()
        for item in node:
            names |= _component_names(item)
        return names
    return set()


def _reachable_components(node, components: dict) -> set[str]:
    """The transitive closure of the component references reachable from ``node``."""

    names = _component_names(node)
    pending = set(names)
    while pending:
        for nested in _component_names(components.get(pending.pop(), {})):
            if nested not in names:
                names.add(nested)
                pending.add(nested)
    return names


def _declared_properties(node) -> set[str]:
    """Every JSON property name declared anywhere inside a schema node.

    Only declared fields matter: a component description may *say* that
    correctness is never exposed, but no schema may declare an ``is_correct``
    field.
    """

    if isinstance(node, dict):
        names = set()
        properties = node.get("properties")
        if isinstance(properties, dict):
            names |= set(properties)
        for key, value in node.items():
            if key not in _NON_SCHEMA_KEYS:
                names |= _declared_properties(value)
        return names
    if isinstance(node, list):
        names = set()
        for item in node:
            names |= _declared_properties(item)
        return names
    return set()


@pytest.mark.django_db
def test_openapi_contains_every_learning_path_and_method():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    paths = schema["paths"]

    assert len(LEARNING_SCHEMA_PATHS) == 12
    for path, methods in LEARNING_SCHEMA_PATHS.items():
        assert path in paths, f"{path} is missing from the schema"
        assert methods <= set(paths[path]), f"{path} lacks {methods - set(paths[path])}"


@pytest.mark.django_db
def test_openapi_learning_payloads_never_expose_answer_correctness():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    paths = schema["paths"]
    components = schema["components"]["schemas"]

    referenced: set[str] = set()
    leaked: set[str] = set()
    for path, methods in LEARNING_SCHEMA_PATHS.items():
        for method in methods:
            operation = paths[path][method]
            if "is_correct" in _declared_properties(operation):
                leaked.add(f"{method.upper()} {path}")
            referenced |= _reachable_components(operation, components)

    assert set(EXPECTED_COMPONENTS) <= referenced
    leaked |= {
        name
        for name in referenced
        if "is_correct" in _declared_properties(components[name])
    }
    assert leaked == set()
