# Profile and Study Preferences API Contract

## Endpoints

### 1. Get Current Profile
- **Path**: `GET /api/v1/profile/`
- **Authentication**: `Bearer <access_token>` (Required, `IsAuthenticated`)
- **Throttle**: Default rate limits
- **Responses**:
  - `200 OK`: `UserProfile` object. If profile row does not exist yet, creates it and returns canonical empty profile.
  - `401 Unauthorized`: Credentials missing or invalid (`AUTHENTICATION_REQUIRED`).

### 2. Update Profile
- **Path**: `PATCH /api/v1/profile/`
- **Authentication**: `Bearer <access_token>` (Required, `IsAuthenticated`)
- **Throttle**: `account_mutation` (10/min)
- **Responses**:
  - `200 OK`: Updated `UserProfile` object.
  - `400 Bad Request`: Validation error or disallowed field (`INVALID_REQUEST`).
  - `401 Unauthorized`: Credentials missing or invalid (`AUTHENTICATION_REQUIRED`).
  - `429 Too Many Requests`: Throttle limit exceeded (`THROTTLED`).

## Request Contract (PATCH)

```json
{
  "university": "БашГМУ",
  "course": 4,
  "semester_goal": "Закрыть микробиологию и патфиз",
  "daily_study_minutes": 60,
  "selected_subject_ids": [1, 3]
}
```

- All fields are optional in PATCH payload.
- `university`: String up to 255 chars, blank or null allowed.
- `course`: Integer in range 1..6, or null.
- `semester_goal`: String up to 255 chars, blank or null allowed.
- `daily_study_minutes`: Integer in range 1..1440, or null.
- `selected_subject_ids` (or `selected_subjects`): List of positive integer subject IDs. Replaces entire set. Unknown IDs result in 400.
- Any other field (e.g., `telegram_id`, `username`, `role`) is rejected with 400 `INVALID_REQUEST`.

## Response Contract (200 OK)

```json
{
  "university": "БашГМУ",
  "course": 4,
  "semester_goal": "Закрыть микробиологию и патфиз",
  "daily_study_minutes": 60,
  "selected_subjects": [
    {
      "id": 1,
      "title": "Микробиология",
      "slug": "microbiology"
    },
    {
      "id": 3,
      "title": "Патофизиология",
      "slug": "pathophysiology"
    }
  ]
}
```

Canonical empty response:
```json
{
  "university": "",
  "course": null,
  "semester_goal": "",
  "daily_study_minutes": null,
  "selected_subjects": []
}
```

## Error Envelope Responses

### 400 Bad Request (`INVALID_REQUEST`)
```json
{
  "code": "INVALID_REQUEST",
  "detail": "Request validation failed.",
  "fields": {
    "course": ["Ensure this value is less than or equal to 6."]
  }
}
```

### 401 Unauthorized (`AUTHENTICATION_REQUIRED`)
```json
{
  "code": "AUTHENTICATION_REQUIRED",
  "detail": "Authentication credentials were not provided.",
  "fields": {}
}
```
