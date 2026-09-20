# BE-010 — Slug-based public URLs

Status: BLOCKED

## Existing behavior

Subject/Section/Topic have slugs, but the public API contract uses numeric IDs.
Slugs are currently an auxiliary representation.

Do not replace numeric-ID routes while URL policy is unresolved.

## Owner decisions required

Before a spec:

- uniqueness scope for each slug;
- collision handling;
- case/Unicode normalization rules if different from current generation;
- manual override validation;
- what happens when a published slug changes;
- whether old slugs redirect;
- redirect/history retention;
- whether API routes become slug-only, ID-or-slug, or frontend-only slugs.

## Compatibility constraints

If approved later:

- existing numeric API clients must not break silently;
- redirects/history belong to an explicit URL contract, not model magic;
- content access rules remain unchanged;
- slug changes must not expose unpublished/paid content.

No implementation while BLOCKED.
