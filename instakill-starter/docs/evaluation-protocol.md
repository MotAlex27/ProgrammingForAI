# Evaluation protocol

## Question
The evaluation answers one product question: for the users who have enough history before the cutoff and at least one later like, which feed strategy ranks the posts they will like into the top 10 most often, by how much, and how uncertain that result is. We compare the four strategies we actually serve or measure in this lab: chronological, popularity, for_you, and learned.

## Cut-off and snapshot
We choose a single cutoff time T and treat everything before T as the app's knowledge at decision time. We make a temporary snapshot of the database, delete all posts, likes, and follows that are not known before T, and then evaluate the ranking functions on that frozen copy only. This prevents any data that appears after T from influencing candidate generation or scoring.

## Users
We include every user with at least three likes before T and at least one later like on a post that still exists in the snapshot. Each user gets one row per strategy, so we can compare strategies on the same question and compute paired uncertainty with a fixed bootstrap seed.

## Candidates and relevance
For each user, we ask the service function that backs GET /feed for that user's top 10 at time T, and we compare the returned post IDs to the posts they actually liked after T. Those later likes are the relevant items for that user; no separate reimplementation is needed, because the product code is the thing being measured.

## Metric
We score each user with NDCG@10, where the top-10 ranking is evaluated against the set of relevant later liked posts. Our DCG is the sum of 1/log2(i+2) over the first ten positions, and we divide by the DCG of the perfect top-10 ordering; the result stays between 0 and 1, and repeated runs produce the same value for the same snapshot.

## Intervals and slices
The script creates 95% paired bootstrap intervals over users for each strategy's mean and for learned minus the best baseline. We also slice results by user activity before T using the same group bands as the lab: new (<10 likes), casual (10-49), regular (50-199), and power (200+). These slices make it easy to see whether a model wins centrally or fails for a particular population.

## Known limitations
1. The model may have seen the future. The Week 5 network was trained on MovieLens ratings through a validation cutoff, and the seeded database uses the same data; if many of the evaluation likes sit in that training window, learned may look better than it would on truly unseen future behavior.
2. The population is not InstaKill's. MovieLens is dominated by old titles rated years later, while a fresh social feed is dominated by very recent posts. A strategy that wins on an archive of historical ratings can easily lose on a feed of fresh posts, so the slices are useful for diagnosing the mismatch.
