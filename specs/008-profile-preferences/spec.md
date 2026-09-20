# Feature 008 — Profile and study preferences

- Status: IMPLEMENTED (READY_FOR_REVIEW)
- Date: 2026-09-20
- Owning Django app: `apps.users`
- Consumers: Authenticated own-user profile clients (web/mobile)

## 1. Summary and Business Goal

MedCore MVP allows users to authenticate and study medical subjects and topics. To personalize the study experience, users can specify their university, study year/course, semester goals, daily study target in minutes, and preferred subjects of interest.

Feature BE-008 introduces:
1. Persistent `UserProfile` model in `apps.users` with 1-to-1 relationship to `User` and M2M relationship to `Subject`.
2. Self-profile endpoints:
   - `GET /api/v1/profile/`
   - `PATCH /api/v1/profile/`
3. Privacy guarantees: strictly private to the authenticated user. No public profiles or cross-user access.
4. Non-intrusive onboarding: profile is completely optional and never blocks access to free/demo content or login.
5. Independent access control: selected subjects reflect user study preferences, not permissions or subscription paywalls.

## 2. Architecture and Domain Boundaries

1. **Owning App**: `apps.users`
   - `UserProfile` model resides in `apps/users/models.py`.
   - Admin registration in `apps/users/admin.py`.
   - Serializers in `apps/users/serializers.py`.
   - Service operations in `apps/users/services.py` (`get_or_create_profile`, `update_profile`).
   - Views in `apps/users/views.py` (`ProfileView`).
   - URL routing in `apps/users/urls.py` (`/api/v1/profile/`).

2. **Data Model**:
   - `user`: `OneToOneField(settings.AUTH_USER_MODEL, on_delete=CASCADE, related_name="profile")`
   - `university`: `CharField(max_length=255, blank=True, default="")` (free text).
   - `course`: `PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(6)])` with DB check constraint `course IS NULL OR (course >= 1 AND course <= 6)`.
   - `semester_goal`: `CharField(max_length=255, blank=True, default="")`.
   - `daily_study_minutes`: `PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(1440)])` with DB check constraint `daily_study_minutes IS NULL OR (daily_study_minutes >= 1 AND daily_study_minutes <= 1440)`.
   - `selected_subjects`: `ManyToManyField("content.Subject", blank=True, related_name="user_profiles")`.
   - `created_at`: `DateTimeField(auto_now_add=True)`.
   - `updated_at`: `DateTimeField(auto_now=True)`.

3. **Endpoints & Permissions**:
   - `GET /api/v1/profile/`: `IsAuthenticated` only. Returns canonical empty profile (or safely creates profile row via `get_or_create`) if not existing.
   - `PATCH /api/v1/profile/`: `IsAuthenticated` only. Partial update of allowed profile fields (`university`, `course`, `semester_goal`, `daily_study_minutes`, `selected_subject_ids` / `selected_subjects`).
   - Throttling: `AccountMutationThrottle` applied to `PATCH /api/v1/profile/`.
   - Anonymous access receives `401 AUTHENTICATION_REQUIRED`.
   - No path parameterized by user id (`/users/{id}/profile/` is forbidden).

4. **Validation & Security**:
   - Only allowed profile fields can be modified. Attempts to modify `telegram_id`, `username`, `role`, `is_staff`, `auth_version`, `subscription`, etc., are rejected with `400 INVALID_REQUEST`.
   - `course` must be between 1 and 6 (or null).
   - `daily_study_minutes` must be between 1 and 1440 (or null).
   - `selected_subject_ids` / `selected_subjects` must only reference existing `Subject` IDs. Unknown IDs are rejected with `400 INVALID_REQUEST`.
   - Partial updates preserve omitted fields.
   - Sending `selected_subject_ids` replaces the entire current set; sending empty list `[]` clears the set.

5. **Lifecycle & Deletion**:
   - Deleting a `User` cascades to `UserProfile` and clears the M2M associations automatically.
   - The underlying `Subject` records remain unaffected.

6. **Decoupled Access Control**:
   - Preferences in `selected_subjects` do not influence topic demo/free/paid access evaluation in `apps.content.access`.

## 3. Testing and Verification

Covered across 16 test cases in `apps/users/tests/test_profile_api.py` and `apps/common/tests/test_openapi_contract.py`:
1. Anonymous `GET` -> 401.
2. Anonymous `PATCH` -> 401.
3. Authenticated user without profile gets canonical empty profile.
4. `PATCH` creates/updates profile fields.
5. Partial `PATCH` preserves other fields.
6. `course < 1` rejected with 400.
7. `course > 6` rejected with 400.
8. Invalid `daily_study_minutes` (< 1 or > 1440) rejected with 400.
9. `selected_subjects` persisted and returned.
10. Repeated `PATCH` replaces full set of selected subjects; `[]` clears it.
11. Unknown `Subject` id rejected with canonical validation error.
12. Private access: user B cannot read or modify user A's profile.
13. User deletion cascades to `UserProfile`, leaving `Subject` untouched.
14. `selected_subjects` has no effect on topic content access.
15. Telegram and auth identity fields cannot be modified via profile endpoint.
16. OpenAPI contract documents `GET` and `PATCH /api/v1/profile/` with request/response schemas and error envelopes.
