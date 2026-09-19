# Research: Learning state

Feature: `003-learning-state`. Every decision below is source-backed; the
authoritative resolution record is
[`.omp/decisions/2026-09-19-003-learning-state-review.md`](../../.omp/decisions/2026-09-19-003-learning-state-review.md),
which also carries the Luna watchdog verdicts.

## 1. Theory unit: `ContentBlock`, not `Section`

**Decision**: the spec's "theory section" is the Topic's published
`ContentBlock`; the learning row is `UserTopicBlockProgress` and the route is
`POST /api/v1/topics/{topic_id}/blocks/{block_id}/complete/`.

**Rationale**: the accepted content model has no Section inside a Topic —
`Subject → Section → Topic`, with `Topic.section` a required `PROTECT` FK
(`apps/content/models.py:87-89`) and theory units as optional `ContentBlock` rows
(`../medcore-docs/content/structure.md:5-6,16-23`;
`../medcore-docs/architecture/database.md:9-20`). The literal reading makes "Topic
has zero sections" unreachable and "Section must belong to the requested Topic"
unsatisfiable.

**Alternatives rejected**: literal Section FK (degenerate 0/100 percentage,
unreachable edge case); a new Topic→Section content entity (new domain model and
migration, not authorized).

## 2. `answers_state` stays answer-ID-only; the extra state gets its own fields

**Decision**: `QuizAttempt` persists `answers_state`
(`{"selected_answer_ids": [...]}`), `question_ids` (frozen at start) and
`results` (graded breakdown, null while active) as three separate values; the wire
contract exposes `selected_answer_ids`, `question_ids`, `questions` and `results`.

**Rationale**: the spec requires the shape to be fixed in the plan/OpenAPI and
restricts `answers_state` to answer IDs
(`specs/003-learning-state/spec.md:195-196`). Luna's round-1 verdict was `BLOCKED`
on putting question IDs and numeric scores inside `answers_state`; the remedy it
named — separate persisted fields plus an explicit spec amendment — is what this
plan does.

**Alternatives rejected**: a richer `answers_state` (violates the literal
contract); recomputing results at read time (loses reproducibility).

## 3. Frozen question set, current correctness at submit, persisted result

**Decision**: freeze `question_ids` at attempt start; grade at submit using the
current `QuizAnswer.is_correct` values; persist `results` and `score_percent`.
Do not block content edits; do not snapshot correctness while active.

**Rationale**: 004 guarantees stable, never-deleted quiz child identity
(`specs/004-content-api-media/spec.md:501-502`), so a selected ID cannot dangle;
the spec demands stable IDs for an attempt and delegates the policy to plan time
(`specs/003-learning-state/spec.md:295-301,366-368`). Luna round 1 rated this
`RESOLVED` and accepted the residual risk that an `is_correct` edit changes an
attempt that is still active.

**Alternatives rejected**: snapshotting correctness at start (leaks correctness
into an active attempt's row and freezes stale truth); blocking content writes
while an attempt exists (couples `content` to `learning`, unsupported by any
source).

## 4. Progress transitions

**Decision**: the first learning action creates the progress row with
`status=learning`; `learned` is reached only through the explicit
`PATCH {"status": "learned"}` transition, which never regresses and is not gated
by the theory percentage. `theory_percent` and the block counts are derived
(`ROUND_HALF_UP`, `0` for zero published blocks). `GET` never creates a row.

**Rationale**: the register accepts the manual button and states it works when
there are no quizzes (items 66, 69); spec rule 5 gives the automatic
`not_started → learning` transition and rule 21 keeps a quiz pass from completing
the topic.

**Alternatives rejected**: auto-`learned` when all blocks are complete (makes the
spec's explicit manual transition unreachable and gates manual completion on
content completeness); requiring 100% theory for manual `learned` (not required
by any source).

## 5. Pass threshold and score-based automatic completion stay deferred

**Decision**: no `passed` flag, no pass-threshold setting and no score-based
automatic completion in this feature; the spec records the deferral in
`Out of scope` and business rule 21, and the decision record carries the open
owner decision.

**Rationale**: register item 65 says "Проходной процент глобально пока не
вводить" (`../medcore-docs/decisions/0004-mvp-decision-register.md:90`),
`../medcore-docs/architecture/database.md:125` and `../medcore-docs/ai/context.md:132`
state that no global pass threshold exists, `docs/architecture/open-questions.md:116-118`
records that the backend source of truth for the threshold is unchosen, and the
prototype's 80% is explicitly not a contract (`specs/003-learning-state/spec.md:367`).
Items 67-68 accept auto-completion **and** leave the threshold TBD. Inventing the
value is forbidden; one owner decision now covers both the pass/fail display and
the auto-completion transition. Luna round 1 returned `BLOCKED` on the earlier
manual-only proposal and named an explicit recorded deferral as the acceptable
remedy; the pre-implementation consistency analysis then returned `BLOCKER` on the
80% flag itself, which is corrected here.

**Alternatives rejected**: implementing pass/fail at 80% (invents a value the
accepted sources forbid); silently dropping the deferral (it must be recorded and
surfaced).

## 6. Flashcard schedule and due selector

**Decision**: intervals from `LEARNING_FLASHCARD_INTERVALS` (default
`(1, 3, 7, 14, 30)`); `know` advances one interval, `repeat` resets to the first;
one current row per user/card; due = existing rows with `next_review_at <= now`
on published, accessible topics ordered by `(next_review_at, id)`.

**Rationale**: spec rules 11-12 and the accepted card-state fields
(`../medcore-docs/decisions/0008-...md:57-65`); never-reviewed cards have no row,
so they are not "due" (the spec's due route is about scheduled reviews).

**Alternatives rejected**: scanning every accessible flashcard for never-reviewed
cards (no topic scope in the route, unbounded query, not requested by the spec);
a separate `due` flag (derived value).

## 7. One active attempt: partial unique constraint + locked start

**Decision**: `UniqueConstraint(fields=["user","quiz"], condition=status="active")`
plus a locked read in the start service; normal start returns the existing
attempt with 200, creation 201, and the racing loser 409 `ACTIVE_ATTEMPT_EXISTS`.
Submit locks the row and the loser gets 409 `ATTEMPT_ALREADY_SUBMITTED`.

**Rationale**: spec invariants and edge cases (`spec.md:109-112,293-294,315-320`),
architecture "DB constraints are the second line of defence" and "row locks only
where the invariant requires it" (`docs/architecture/target-architecture.md:198-205`).

**Alternatives rejected**: an application-only check (loses the race); a global
lock (unnecessary contention).

## 8. Best score is derived

**Decision**: `Max(score_percent)` over the current user's submitted attempts,
exposed as `best_score_percent` on quiz detail and the topic quiz list; `null`
without a submitted attempt.

**Rationale**: spec rule 22 and `docs/architecture/domain-model.md:119-120` forbid
storing it; the spec's route list names no separate endpoint.

**Alternatives rejected**: a stored column (contradicts the sources); a new
`/progress/` summary endpoint (not in the spec's route list).

## 9. Access, ownership and errors

**Decision**: `IsAuthenticated` on every route; per-request published-topic
resolution plus `evaluate_topic_access`; 404 for missing/unpublished/another
user's object; 403 `TOPIC_ENTITLEMENT_REQUIRED` for paid denial; the stale
`TOPIC_ACCESS_DENIED` code is dropped.

**Rationale**: the real access seam emits `AUTHENTICATION_REQUIRED` /
`TOPIC_ENTITLEMENT_REQUIRED` (`apps/content/access.py:25-47`), the 002 contract
uses `RESOURCE_NOT_FOUND` for policy-hidden resources, and hiding another user's
object behind 404 is the accepted security policy.

**Alternatives rejected**: 403 for another user's attempt (leaks existence);
keeping the stale code (no producer).

## 10. Deletion

**Decision**: every learning FK is `ON DELETE CASCADE` (User, Topic,
ContentBlock, Flashcard, Quiz); no retention or tombstone.

**Rationale**: the 001 User cascade contract, the 002/004 learning cascade
carry-forward, MVP physical deletion (`docs/architecture/conventions.md:132-156`).
Luna round 1 rated it `RESOLVED`.

**Alternatives rejected**: soft delete/retention (not accepted for MVP);
application-level cleanup (would need `content` to call `learning`).

## 11. Module layout and shared write primitives

**Decision**: `apps/learning` becomes a package: app-level `models.py`,
`scheduling.py`, `scoring.py`, `access.py`, `serializers.py`, `services.py`,
`urls.py`, plus the `progress/`, `flashcards/` and `quizzes/` sub-packages and
`tests/`. `apps/learning/services.py` owns the progress-row lifecycle primitives
(`ensure_topic_progress`, `touch_topic_learning`) shared by all three use-case
areas.

**Rationale**: the three areas have disjoint services/serializers/views, so
sub-packages keep the writable files of the parallel implementation zones
disjoint; the shared progress-row primitive has one owner instead of three copies
or a cross-zone import chain. `apps/learning/serializers.py` holds the app's
strict-serializer mixin so the unknown-field contract is written once (mirroring
`apps/content/serializers.py`).

**Alternatives rejected**: flat `services.py`/`views.py`/`serializers.py` (forces
the three areas to serialize on shared files); importing content's strict mixin
(couples learning to another app's serializer internals); copying the mixin three
times.

## 12. The block-progress row stores no topic

**Decision**: `UserTopicBlockProgress` references only the block; the topic is
derived (`block__topic`, `block__status=published`) in every read, and the route
validates the URL topic against `block.topic_id` (404 otherwise).

**Rationale**: the content API can re-parent a block to another Topic
(`apps/content/services.py:495-496`, `apps/content/views.py:744-747`), so a stored
`(topic, block)` pair could silently disagree with the content hierarchy. Deriving
the topic keeps the learning row consistent under a content move without a
cross-domain cleanup, which the dependency direction forbids. The consistency
analysis raised this as a `HIGH` finding.

**Alternatives rejected**: keeping `topic` and documenting the staleness (leaves a
wrong derived percentage after a move); a `content`-side hook that rewrites
learning rows (reverse dependency, forbidden).

## 13. URL aggregation and the zone handover

**Decision**: `Z1-foundation` writes `apps/learning/urls.py` with three
`include()`s and creates each sub-package with an empty `urlpatterns`; each feature
zone fills only its own `urls.py` and modules.

**Rationale**: the foundation checkpoint (`manage.py check`, migration apply,
helper imports) must be reachable before the feature zones exist, and each zone's
API tests need a loadable URLconf that already aggregates the other sub-packages.
The consistency analysis flagged the earlier single-file URL task as an
unreachable checkpoint and an ownership conflict.
