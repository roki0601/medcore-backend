# BE-009 — Content bulk/import extensions

Status: BLOCKED

## Existing contract — do not rebuild it

The current accepted content integration already supports synchronous REST CRUD
with integration key and `external_id` upsert.

There is intentionally:

- no ImportJob;
- no Celery import worker;
- no "delete missing objects" synchronization;
- no bulk endpoint requirement.

External producers are expected to transform their data and call the existing
REST contract.

## Start condition

Only start this feature when a concrete workflow cannot reasonably use the
existing synchronous API.

Owner/spec must then define:

- exact bulk/import use case;
- payload shape;
- stable identity/upsert rules;
- all-or-nothing vs partial success;
- error reporting;
- removal semantics;
- bulk publish semantics;
- maximum batch size;
- whether processing is synchronous;
- editor/integration permissions;
- media references inside a batch.

## Guardrails

Do not add Celery/Kafka/RabbitMQ solely because the word "import" appears.

Do not create a generic JSON blob/import job. Keep content entities canonical
and validated through the same domain rules.

No implementation while BLOCKED.
