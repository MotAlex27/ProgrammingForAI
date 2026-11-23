# Offline feed evaluation protocol

## Question

On the seeded MovieLens history, which feed strategy ranks the posts a user later likes in its top 10, how large is the difference, which activity groups differ, and how uncertain are the results? We evaluate the same four strategies used for this assignment: `chronological`, `popularity`, `for_you`, and `learned`.

## Input data, cut-off, and snapshot

`scripts/seed_movielens.py` maps MovieLens ratings of at least 4.0 to timestamped likes, creates one timestamped post per movie, and derives follows from liked authors. By default, the evaluator uses the timestamp at which 80% of these likes have occurred as cut-off `T`; all time comparisons use event timestamps. It copies the database, removes likes at or after `T` and posts not yet created at `T`, then derives follows again from only the remaining likes. Invalid or missing post/like timestamps stop the run rather than being guessed.

## Users, candidates, and relevance

We include a user with at least three likes before `T` and one or more likes after `T` on posts that already exist in the snapshot. At time `T`, the evaluator asks the same `FeedService.get_feed` operation used by `GET /feed` for that user's top 10 from the frozen snapshot. `popularity` is implemented only in the evaluation script because it is a required comparison, not an API strategy. Relevant items are the snapshot posts the user liked after `T`.

## Metric, intervals, and slices

Each user and strategy receives binary-gain NDCG@10: a relevant returned post contributes `1 / log2(position + 2)`, divided by the ideal DCG for the user's relevant items, capped at 10. We report each strategy's mean and a 95% user-bootstrap interval with a fixed seed. For `learned` minus the best baseline, we first choose the baseline with the highest mean overall (and separately within each activity group), then bootstrap the paired per-user differences against that same baseline. Activity groups are based on pre-cut-off likes: new (<10), casual (10-49), regular (50-199), and power (200+).

## Known limitations

1. **Potential model-selection leakage.** Week 5 trains the model weights on MovieLens likes before its 70th-percentile timestamp and uses later data for validation and test. In the supplied data there are 48,580 positive likes: the Week 5 train boundary is Unix time `1363686948`, the test boundary is `1468118189`, and the default Week 7 cut-off is `1454621690`. Of the 8,315 post-cut-off likes on posts already in the snapshot, 0 precede the train boundary, 2,310 fall in the validation period, and 6,005 fall in the test period. Thus no evaluation likes were used to fit the model weights, but the model was tuned and its test results inspected on periods that overlap this replay. In the seeded run, `learned` scores 0.1181 versus 0.1128 for the best baseline (`popularity`), with paired mean difference +0.0054 and 95% interval [-0.0004, 0.0136] (`unclear`); treat that small apparent gain as potentially optimistic, not as a clean future holdout.
2. **The population is not InstaKill's.** MovieLens contains mostly older movie items rated over many years, unlike a social feed dominated by fresh posts. `Popularity` is the strongest aggregate baseline here, while subgroup paired intervals include zero; these historical slices cannot establish a winner for fresh social posts. A chronological or freshness-heavy feed is a plausible hypothesis for fresh posts, but this replay does not test it.

These NDCG@10 values are not comparable to the Week 5 lab's: the lab hides one positive among 99 sampled candidates at each event, while this replay ranks the entire eligible post catalogue and can have several relevant posts per user.
