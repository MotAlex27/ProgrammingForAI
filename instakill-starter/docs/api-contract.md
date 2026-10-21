# API contract

This is a contract for a future endpoint. It is not implemented yet.

## Retrieve a user's post

`GET /users/{user_id}/posts/{post_id}`

### Request

Both path parameters are positive integers. The request has no body.

Example:

```http
GET /users/12/posts/34
```

### Successful response

`200 OK` returns the post when it exists and belongs to the requested user:

```json
{
  "id": 34,
  "user_id": 12,
  "content": "A sample post",
  "created_at": "2026-10-21T18:30:00Z"
}
```

`created_at` may be `null` when no timestamp is available.

### Validation and error cases

- `422 Unprocessable Entity` when either path parameter is not a positive integer.
- `404 Not Found` when the user or post does not exist, or when the post belongs to a different user.

Using the same `404` response for a missing post and an ownership mismatch avoids revealing posts through a nested URL.
