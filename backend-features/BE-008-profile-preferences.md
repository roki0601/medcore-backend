# BE-008 — Profile and study preferences

Status: MERGED (PR #16)

## Implementation Summary

Owner decisions for MVP were accepted and implemented:
- Study preferences are in MVP under `apps.users`.
- Persistent `UserProfile` model created with OneToOne relation to `User`.
- Telegram auth identity fields remain untouched on `User`.
- Fields: `university` (free text), `course` (1..6, nullable), `semester_goal` (short text), `daily_study_minutes` (1..1440, nullable), `selected_subjects` (M2M to `Subject`).
- Self-service endpoints: `GET /api/v1/profile/`, `PATCH /api/v1/profile/`.
- Privacy: private to current user; no public profile or listing.
- Deletion: `CASCADE` on `UserProfile` when `User` is deleted.
- Non-blocking: profile is optional and does not block login or access.
- Decoupled: `selected_subjects` does not impact access control or paywall entitlement.
- Spec: `specs/008-profile-preferences/spec.md`.
- Contract: `specs/008-profile-preferences/contracts/profile-api.md`.
