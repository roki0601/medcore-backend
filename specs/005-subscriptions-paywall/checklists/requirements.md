# Feature 005 — Requirements Checklist

- [x] Owner decisions D1–D8 explicitly resolved and accepted via ADR 0009 in `medcore-docs`.
- [x] Topic access `demo | free | paid` contract preserved.
- [x] `premium` is NOT added as a User role.
- [x] Editor/Admin role alone does NOT bypass paid entitlement in user-facing APIs.
- [x] Payment provider integration isolated to BE-006.
- [x] No independent paid flags on ContentBlock, Flashcard, or Quiz.
- [x] User deletion cascades subscriptions cleanly without leaving orphaned records.
- [x] Public seam `apps.subscriptions.policy.has_paid_content_entitlement(user)` remains the single source of truth for paid access across content, learning, and media.
- [x] Multiple/overlapping subscriptions supported without artificial single-subscription limits (D3).
- [x] Stored status EXPIRED omitted in favor of dynamic time calculation (D1).
- [x] Trial omitted from models and API in MVP (D4).
