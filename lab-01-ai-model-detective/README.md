# Lab 01 — AI Model Detective

## The problem

> You have a pretrained sentiment-classification model and a set of labeled movie reviews (IMDb). Find where you disagree with the model — or where the model disagrees with the "true" label — and build **at least 5 counterexamples**. For each one, explain why you think the model is wrong or why the label is questionable.

You are not required to train anything this week. The goal is to learn to **run, inspect, and question** a model already trained by someone else — that's the first competency in the course.

## What you have available

Everything is in `starter.ipynb` — setup, data download, pretrained model loading, `TODO` cells, an inline acceptance check, and the `RESULTS` block. No other files, no separate scripts. Just upload the notebook to Google Colab (File > Upload notebook) and run it top to bottom.

## Acceptance criteria

1. The notebook runs top to bottom, on CPU, with no errors, starting from a clean runtime.
2. At least **5 documented counterexamples** in the `disagreements` list: the review text, the dataset label, the model's prediction, and a short explanation.
3. The acceptance-check cell in the notebook passes (checks structure, not accuracy).
4. The notebook ends with the standard block:

```text
RESULTS
baseline:
solution:
runtime:
memory / model size:
3 failure cases:
what I would try next:
```

## Resources

- **R1** — [Google Colab](https://colab.research.google.com/)
- **R2** — [HF Text Classification Colab](https://colab.research.google.com/github/huggingface/notebooks/blob/main/examples/text_classification.ipynb) (starting reference, not to copy 1:1)
- Dataset: [IMDb Large Movie Review Dataset](https://ai.stanford.edu/~amaas/data/sentiment/), loaded via `datasets.load_dataset("imdb")`. Note: the Stanford page doesn't state an explicit license — fine for classroom/educational use, but don't redistribute the raw data commercially. (UCI SMS Spam, CC BY 4.0, is reserved for the Week 8 "Beat the Dummy" challenge — using a different dataset here avoids repeating it.)

## What you do NOT need to do

- Don't train/fine-tune a model (that comes in weeks 8-9).
- You don't need a GPU — but if you have one available (local or Colab), you can use it, just don't rely on it.
