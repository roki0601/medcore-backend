# Dashboard Aggregate API Contract

## Endpoint
- **Path**: `GET /api/v1/dashboard/`
- **Authentication**: `Bearer <access_token>` (Required, `IsAuthenticated`)
- **Throttle Scope**: `learning_read`
- **Pagination**: None (returns all started topics)

## Response Contract (200 OK)

```json
{
  "summary": {
    "started_topics_count": 4,
    "completed_theory_topics_count": 2,
    "flashcards_due_count": 13,
    "quizzes_attempted_count": 3
  },
  "topics": [
    {
      "id": 15,
      "title": "Стафилококки",
      "subject": {
        "id": 1,
        "title": "Микробиология"
      },
      "section": {
        "id": 4,
        "title": "Грамположительные кокки"
      },
      "theory": {
        "status": "learning",
        "progress_percent": 60
      },
      "flashcards": {
        "due_count": 4
      },
      "quiz": {
        "attempted": true,
        "best_score_percent": 75
      },
      "last_activity_at": "2026-09-20T12:00:00Z"
    }
  ]
}
```

## Error Envelope Responses

### 401 Unauthorized (`AUTHENTICATION_REQUIRED`)
```json
{
  "code": "AUTHENTICATION_REQUIRED",
  "detail": "Authentication credentials were not provided.",
  "fields": {}
}
```

### 429 Too Many Requests (`THROTTLED`)
```json
{
  "code": "THROTTLED",
  "detail": "Request was throttled. Expected available in ... seconds.",
  "fields": {}
}
```
