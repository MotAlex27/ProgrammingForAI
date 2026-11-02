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

## User feed

`GET /feed?user_id=<int>&limit=<1..50>&strategy=for_you|chronological`

### Request

- `user_id` is required and identifies an existing user.
- `limit` is optional, defaults to 20, and must be an integer from 1 through 50.
- `strategy` is optional, defaults to `for_you`, and must be `for_you` or `chronological`.

### Successful response

`200 OK` returns up to `limit` posts. `for_you` results include a numeric `score` and
are ordered by descending score, then ascending `post_id`. Chronological results are
ordered by newest `created_at`, then ascending `post_id`; they omit `score`.

```json
{
  "user_id": 1,
  "strategy": "for_you",
  "posts": [
    {
      "post_id": 3,
      "user_id": 2,
      "content": "just shipped a cosine similarity search, feels great",
      "created_at": "2026-11-02T10:00:00+00:00",
      "score": 0.72
    }
  ]
}
```

Candidates are all existing posts because this starter has no post visibility
field. The requesting user's own posts and posts they have already liked are
excluded. A user who follows nobody can still receive other eligible posts; they
receive no affinity boost.

The `for_you` score is:

```text
0.4 * exp(-age_hours / 72)
+ 0.4 * followed_author
+ 0.2 * log(1 + post_like_count) / log(1 + max_like_count)
```

Here `followed_author` is 1 when the author is followed and 0 otherwise; the
popularity term is 0 when there are no likes. The top-*k* ranker takes
`O(C log k)` time and `O(k)` heap space for `C` candidates and requested limit
`k`, after database reads and signal aggregation. The first derived value to
precompute for larger datasets would be per-post like counts, avoiding a full
like-table aggregation on every request.

### Validation and error cases

- `422 Unprocessable Entity` when `user_id` is missing or not an integer, when
  `limit` is outside 1–50 or not an integer, or when `strategy` is unknown.
- `404 Not Found` when `user_id` does not identify an existing user.

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
