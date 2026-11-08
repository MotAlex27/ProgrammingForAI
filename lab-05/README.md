# Lab 05 — Learn the Scorer

## The problem

In Week 4 you built a feed and set three weights by hand. Build the same kind of scorer **without choosing the weights yourself**: train a small neural network that reads six signals about a user and a post and predicts **how likely the user is to like the post**, then prove on data it has never seen that it beats every simple baseline, including the best straight-line scorer.

The network is a one-hidden-layer MLP written in **plain NumPy**. The piece that makes learning possible, backpropagation, is yours to write; a numerical gradient check tells you whether you got it right.

The data is MovieLens `latest-small`, the same proxy as Week 4: a *like* is a rating of 4 or more and an *item* is a "post" that appears the first time anybody rates it. Every like in the history becomes one **exam question**: the item the user liked is hidden among 99 random items that existed at that moment, and the model must rank it near the top.

## Why this matters for InstaKill

This is the first time a **trained model** can sit inside your feed. The lab teaches the two skills you need for that: *vectorised NumPy* (scoring thousands of posts without a Python loop) and *understanding what a model does inside* (so you can debug it). It ends by saving a small `like_model.npz` file. That file, plus the six signal formulas written in the notebook, is what you plug into `GET /feed?strategy=learned` in this week's project work.

## Available material

- `week05.ipynb` — loads the data, builds the six signals (`LiveSignals`), builds time-split training and exam sets, provides the metrics and the baselines (chronological, popularity, the Week 4 formula, your own Week 4 weights, a least-squares straight line), the forward pass, the training loop, the gradient check, the failure analysis, the export, and the two TODOs.
- A CPU runtime and the MovieLens `latest-small` zip (about 1 MB; not committed to the repository). Download it in your browser from <https://files.grouplens.org/datasets/movielens/ml-latest-small.zip> (you may still have it from Week 4) and upload it when the notebook asks (Colab) or place it next to the notebook (local). An in-notebook download does not work: Python rejects the GroupLens server's certificate chain.
- The required resources listed in the Week 5 assignment overview.

## What you must do

The notebook is a guided walk-through. Read it and run it; make sure you understand why each part exists. There are **two coding tasks**:

1. **Task 1 — `backward`.** Write the gradient of the mean binary cross-entropy loss with respect to `W1`, `b1`, `W2` and `b2`. The stub returns zeros, so the gradient check fails until you implement it. Three collapsible hints are provided; try without them first.
2. **Task 2 — three numbers.** Set `HIDDEN`, `LEARNING_RATE` and `EPOCHS` so that your trained network beats every baseline on `val`. The starting values are deliberately poor. Tune on `val` only.

Then:

- read the failure analysis and write one plain sentence about each of the three worst cases;
- run the final `test` cell once;
- run the export cell and keep `like_model.npz` (you need it for InstaKill);
- fill in the `RESULTS` block.

## Acceptance criteria

- The notebook runs top-to-bottom on CPU in a few minutes.
- All supplied self-checks pass, including the gradient check (every relative error below `1e-6`) and the XOR sanity check.
- Your trained network gets a higher NDCG@10 than **every** baseline, including the linear model, on `val` (checkpoint cell) and on `test` (final cell).
- You tuned only on `val` and ran the final `test` cell once.
- `like_model.npz` is saved and the reload check passes (`predict` reproduces your network).
- `RESULTS` is complete: all baselines, your three numbers and scores, the printed timings with the Big-O of one forward pass in your own words, the parameter count and file size, three failure sentences, and one idea for what to try next.
- You use no machine-learning library and no automatic differentiation.

## Explicit exclusions

- Do not use `sklearn`, `torch`, `tensorflow`, `jax`, `autograd`, or any other library that trains models or computes gradients. NumPy and the standard library only.
- Do not edit the supplied data pipeline, exam, metrics, baselines, `forward`, or `train` (changing the hyper-parameters in Task 2 is the intended way to tune).
- Do not add more layers, more signals, or a different activation in this lab; those are things to try *next*.
- Do not build a web UI or FastAPI endpoint inside the disposable lab.
- The lab's `Like` and `Catalogue` records are not InstaKill's Pydantic domain models.

## Submission

Submit your completed `week05.ipynb` with Task 1 implemented, the Task 2 numbers chosen, and the following exact block filled in at the end:

```text
RESULTS
baseline:
solution:
runtime:
memory / model size:
3 failure cases:
what I would try next:
```
