# Specification Quality Checklist: Learning state

Purpose: Validate requirements quality before planning

Created: 2026-09-18

Feature: ../spec.md

## Content quality

- [x] Theory progress, flashcard review and quiz attempts are separated.
- [x] Anonymous learning state is explicitly forbidden.
- [x] User ownership and Topic access are explicit.
- [x] Frontend prototype scoring is not used as the contract.

## Requirement completeness

- [x] State transitions and invariants are specified.
- [x] Multiple correct answers and partial scoring are defined.
- [x] Resume, retry and concurrency behavior are covered.
- [x] No FSRS or subscription behavior is silently introduced.

## Readiness

- [x] Acceptance criteria are observable.
- [x] API, validation, errors and tests are described.
- [x] Dependencies and unresolved serializer detail are bounded.
- [x] The spec is ready for human review before plan generation.

## Notes

The schedule is intentionally simple and is not an FSRS implementation.

## Delegated review outcome (2026-09-19)

The draft was reviewed under `.omp/AUTONOMOUS_REVIEW.md`; the resolutions are
recorded in `.omp/decisions/2026-09-19-003-learning-state-review.md` and applied
to `spec.md`:

- the theory unit is the Topic's published `ContentBlock`
  (`UserTopicBlockProgress`, `/blocks/{block_id}/complete/`);
- `QuizAttempt` keeps `answers_state` answer-ID-only and stores the frozen
  question set and the graded results in their own fields;
- grading freezes the question set at start and the result at submit;
- manual completion only: score-based automatic completion stays deferred until
  the owner accepts a threshold (decision register items 67-68);
- the stale `TOPIC_ACCESS_DENIED` code is replaced by the codes the access seam
  actually emits.

The spec is approved for implementation; `plan.md`, `tasks.md`, `research.md`,
`data-model.md`, `contracts/learning-api.md` and `quickstart.md` are the
implementation artifacts.

A read-only consistency analysis then ran over all artifacts before
implementation. Its `BLOCKER` (the 80% pass flag, which register item 65 forbids)
and its `HIGH` findings were closed in the artifacts and recorded in the decision
record under "Post-analysis corrections": no `passed` field and no pass threshold,
the flashcard review action moves the Topic to `learning`, anonymous quiz reads are
denied, `UserTopicBlockProgress` stores no redundant `topic`, and the zone tables
plus the URL handover were unified.
