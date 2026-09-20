# BE-007 — Progress/dashboard aggregate API

Status: READY_FOR_REVIEW

## Why this exists

Current learning API intentionally exposes per-topic progress only:

`GET /api/v1/topics/{topic_id}/progress/`.

The frontend can therefore create many reads for a large catalog. This is a
known scalability risk, but the merged learning contract explicitly did not add
a user-wide bulk/aggregate progress endpoint.

Do not solve this by silently adding one.

## Start condition

Needs an explicit product/API decision that a user-wide dashboard/aggregate API
is part of MVP.

The owner must decide:

- what the dashboard must show;
- whether it lists every accessible Topic or only started Topics;
- subject/section aggregation requirements;
- whether flashcard/quiz metrics belong in the same response;
- pagination;
- whether "weak topics" or activity history are required;
- freshness/caching expectations.

## Fixed constraints if approved

- authenticated own-user data only;
- Topic access rechecked before exposing learning state;
- no anonymous personal progress;
- no invented overall progress formula across theory/cards/quizzes;
- no pass/fail without an accepted threshold;
- use selectors/aggregates rather than N+1 service calls;
- do not expose another user's state;
- keep the current per-topic API stable.

## Non-goals until accepted

No endpoint path, response schema, activity model or aggregate formula is fixed
by this brief. Agents must not invent them.
