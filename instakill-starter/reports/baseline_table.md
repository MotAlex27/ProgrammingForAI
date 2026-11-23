# Baseline table

- cutoff: 2016-02-04T21:34:50+00:00
- seed: 42
- users: 25
- database: ea32ecbe0d0c
- git commit: 08730d3b2079ab7a5d675edb073b1e99eafe53b6

| Strategy | Mean NDCG@10 | 95% interval | Users |
|---|---:|---:|---:|
| chronological | 0.0000 | [0.0000, 0.0000] | 25 |
| popularity | 0.1128 | [0.0360, 0.2134] | 25 |
| for_you | 0.0188 | [0.0029, 0.0368] | 25 |
| learned | 0.1181 | [0.0392, 0.2193] | 25 |

## learned minus best baseline overall (popularity)

- mean: 0.0054
- 95% interval: [-0.0004, 0.0136]
- verdict: unclear

## learned minus best baseline for new (popularity)

- mean: 0.0318
- 95% interval: [0.0000, 0.0636]
- verdict: unclear

## learned minus best baseline for casual (popularity)

- mean: 0.0086
- 95% interval: [-0.0005, 0.0267]
- verdict: unclear

## learned minus best baseline for regular (popularity)

- mean: 0.0000
- 95% interval: [0.0000, 0.0000]
- verdict: unclear

## learned minus best baseline for power (popularity)

- mean: -0.0010
- 95% interval: [-0.0030, 0.0000]
- verdict: unclear
