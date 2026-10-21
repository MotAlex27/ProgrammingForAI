# API contract

## Semantic post search

`GET /search?q=<non-empty query>&limit=<1..20>`

### Request

- `q` is required and must contain at least one non-whitespace character. The original query is returned unchanged.
- `limit` is required and must be an integer from 1 through 20.

Example:

```http
GET /search?q=cosine%20similarity&limit=5
```

### Successful response

`200 OK` returns up to `limit` posts ranked by descending cosine similarity. Equal scores are ordered by ascending `post_id`.

```json
{
  "query": "cosine similarity",
  "results": [
    {
      "post_id": 3,
      "user_id": 2,
      "content": "just shipped a cosine similarity search, feels great",
      "score": 0.78
    }
  ]
}
```

An empty index returns `200 OK` with an empty `results` list.

### Validation errors

- `422 Unprocessable Entity` when `q` is missing or blank, or when `limit` is missing, not an integer, or outside 1–20.

## Future endpoint: retrieve a user's post

`GET /users/{user_id}/posts/{post_id}`

### Request

Both path parameters are positive integers. The request has no body.

Example:

```http
GET /users/12/posts/34
```

### Successful response

When implemented, `200 OK` will return the post when it exists and belongs to the requested user:

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

Expected errors are `422 Unprocessable Entity` for invalid path parameters and `404 Not Found` when the user or post does not exist, or when the post belongs to a different user. Using the same `404` response avoids revealing posts through a nested URL. This endpoint is not implemented.
