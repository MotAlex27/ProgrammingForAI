# Lab 03 — Search by Meaning, Not Just Words

## The problem

Build a small semantic search engine for short social posts. A pretrained model may turn text into embeddings, but you must implement cosine similarity and deterministic top-*k* retrieval in NumPy.

The supplied notebook creates a deterministic corpus of approximately 1,200 synthetic posts. It deliberately contains paraphrases: for example, a query about a cheap dinner should be able to retrieve a post about a budget-friendly restaurant even when those words do not overlap.

## Available material

- `starter.ipynb` — installs dependencies, creates the corpus, loads a compact pretrained encoder, implements NumPy retrieval, runs acceptance checks, compares three queries, and records `RESULTS`.
- A CPU runtime with internet access for the initial model download.
- The required resources listed in the Week 3 assignment overview.

## What you must implement

1. Create normalized text embeddings for the corpus and a query using the supplied pretrained encoder.
2. Implement cosine similarity in NumPy. It must handle a zero vector safely.
3. Implement top-*k* selection in NumPy. Results must be descending by score, with ascending post ID used when scores tie.
4. Build a `semantic_search` function that returns the selected posts and their scores.
5. Compare semantic search with a simple keyword baseline for at least three queries. Explain one result that is useful and one result that is surprising or weak.

## Acceptance criteria

- The notebook runs top-to-bottom on CPU.
- All supplied acceptance checks pass.
- The corpus contains at least 1,000 posts.
- Your search returns no more than *k* results, scores them with your NumPy cosine implementation, and preserves the specified tie-break rule.
- At least one of your three documented queries contains different words from a relevant returned post.
- You do not use a vector database, hosted embedding API, or library nearest-neighbour/search function.

## Explicit exclusions

- Do not train or fine-tune an embedding model.
- Do not build a web UI or FastAPI endpoint for this disposable lab.
- Do not replace the retrieval code with a vector database or a search framework.
- The lab's synthetic post records are not InstaKill's Pydantic domain models; they are only challenge data.

## Submission

Submit your completed `starter.ipynb` with every TODO implemented and the following exact block filled in at the end:

```text
RESULTS
baseline:
solution:
runtime:
memory / model size:
3 failure cases:
what I would try next:
```
