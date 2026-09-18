<!--
Sync Impact Report
- Version change: placeholder -> 1.0.0
- Modified principles: replaced the generic Spec Kit scaffold with MedCore
  source-of-truth, modular ownership, contract-first security, MVP simplicity,
  verification and documentation principles.
- Added sections: engineering constraints, workflow and governance.
- Removed sections: generic library/CLI examples that did not describe MedCore.
- Follow-up TODOs: subscription/payment semantics remain explicitly TBD in the
  feature specifications and must not be invented during implementation.
-->

# MedCore Backend Constitution

## Core Principles

### I. Decisions and Specifications Are the Source of Truth

Accepted decisions in `medcore-docs`, followed by backend architecture and an
approved feature specification, define the product and technical contract.
`TBD` means unresolved and MUST NOT be silently converted into an
implementation choice. If code, docs and a spec conflict, stop the affected
change and report the conflict.

### II. Domain Ownership and Modular Monolith

Each Django app owns its domain entities and use cases: `users` owns identity
and sessions, `content` owns authoring entities, `learning` owns user learning
state, `subscriptions` owns entitlement policy, `media` owns files, and
`common` owns only domain-agnostic primitives. Cross-domain behavior MUST use
explicit service or policy boundaries. Signals, generic repositories and
future-facing abstraction layers MUST NOT contain core business logic.

### III. Contract-First and Secure Boundaries

Public API contracts MUST be specified before implementation. Every external
input is validated at the API boundary; business invariants are enforced in
services and database constraints. Authentication, role permissions, Topic
access and media access are backend security boundaries. Secrets, JWTs,
refresh-cookie values and Telegram verification data MUST NOT appear in logs,
fixtures or source.

### IV. MVP Simplicity

The implementation MUST use the smallest design that satisfies the approved
contract. PostgreSQL, Django/DRF and Redis cache are the current baseline.
Celery, Kafka/RabbitMQ, Elasticsearch/OpenSearch, Kubernetes, microservices,
FSRS and new external providers MUST NOT be added without an explicit decision
and a concrete feature need.

### V. Tests and Operational Evidence

Every behavior change MUST have tests for the happy path, permissions,
validation/errors and relevant boundaries. Schema changes MUST include
migrations. Verification MUST report exact commands and results, including
formatting, lint, tests, Django checks and migration checks where applicable.
Health endpoints, safe structured logs and backup/restore considerations are
part of production readiness for infrastructure features.

### VI. Documentation and Agent Workflow

Feature work follows `SPECIFY -> PLAN -> TASKS -> IMPLEMENT`. A human MUST
review and approve the relevant spec, plan and task list before implementation.
Significant data-model, auth, API, access or infrastructure decisions require
an ADR or an update to the central project docs. Specs and ADRs MUST explain
scope, exclusions, risks, acceptance criteria and unresolved decisions.

## Engineering Constraints

- Python 3.12, `uv`, Django, DRF, PostgreSQL and Redis cache are the baseline.
- API URLs use `/api/v1/`; REST and OpenAPI are required for public contracts.
- API errors use the stable backend envelope with `code`, `detail` and optional
  `fields`; HTTP status semantics remain consistent.
- User-facing content access is enforced by Topic-level `demo/free/paid`
  policy; frontend visibility is never a permission boundary.
- Content is physically deleted in MVP only where the relevant spec explicitly
  defines cascade behavior.
- Frontend prototype behavior is a visual reference only and is not a backend
  contract.

## Development Workflow

1. Read repository rules, central decisions, architecture and the relevant
   feature spec.
2. Resolve blocking questions before creating a plan.
3. Create a reviewable plan and dependency-ordered tasks.
4. Implement incrementally with tests and migrations.
5. Run the project quality gates and review the resulting diff.
6. Update specs/ADRs when the approved contract changes.

## Governance

This constitution governs Spec Kit artifacts and backend implementation work.
Amendments require a documented reason, a semantic version increment and review
of affected specs/ADRs. A later accepted ADR may refine or supersede an earlier
decision, but it MUST state the scope of the override. Every implementation
review MUST check compliance with this constitution and the applicable spec.

**Version**: 1.0.0 | **Ratified**: 2026-09-18 | **Last Amended**: 2026-09-18
