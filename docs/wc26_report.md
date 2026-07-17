# World Cup 2026 — real-tournament evaluation

Training: 8946 internationals (2016–May 2026), strictly before 2026-06-01 — zero tournament leakage. Scored: 102 played WC26 matches through the semifinals. Source: martj42/international_results (free). No odds exist for internationals here, so the model runs WITHOUT its market anchor; goals stand in for xG; no player/news layers.

## Model vs baselines on the real bracket

|                              |   logloss |   brier |    rps |   accuracy |
|:-----------------------------|----------:|--------:|-------:|-----------:|
| model (pre-tournament train) |    0.9013 |  0.5331 | 0.1773 |     0.6275 |
| train-frequency prior        |    1.0552 |  0.6367 | 0.2284 |     0.4706 |
| uniform                      |    1.0986 |  0.6667 | 0.2386 |     0.4706 |

Conformal: empirical coverage 0.951 vs target 0.90, mean set size 2.45.

## Group stage vs knockout

|          |   n |   logloss |   accuracy |
|:---------|----:|----------:|-----------:|
| group    |  72 |    0.9117 |     0.5972 |
| knockout |  30 |    0.8764 |     0.7    |

## Forward forecasts (unplayed at report time)

### France vs England
- expected goals: 1.61 – 0.96
- 90-minute outcome: {'home': 0.522, 'draw': 0.257, 'away': 0.221}
- to lift/advance (incl. extra time & penalties): {'home': 0.67, 'away': 0.33}
- most likely scores: 1-1 (12%), 1-0 (12%), 2-0 (10%), 2-1 (10%)
- first goal: {'home_first': 0.577, 'away_first': 0.343, 'no_goals': 0.08}

### Spain vs Argentina
- expected goals: 1.27 – 1.04
- 90-minute outcome: {'home': 0.412, 'draw': 0.289, 'away': 0.299}
- to lift/advance (incl. extra time & penalties): {'home': 0.565, 'away': 0.435}
- most likely scores: 1-1 (14%), 1-0 (12%), 0-0 (10%), 0-1 (10%)
- first goal: {'home_first': 0.493, 'away_first': 0.403, 'no_goals': 0.104}

## Ablations (same protocol per variant)

| variant                |   n_features |   logloss |   brier |   accuracy |
|:-----------------------|-------------:|----------:|--------:|-----------:|
| full (w10, hl5)        |            9 |    0.9013 |  0.5331 |     0.6275 |
| no team form           |            5 |    1.0522 |  0.634  |     0.4706 |
| no neutral-venue flag  |            8 |    0.8989 |  0.5343 |     0.598  |
| no rest days           |            7 |    0.8956 |  0.5276 |     0.6078 |
| short window (w5, hl3) |            9 |    0.9315 |  0.5544 |     0.5686 |
| no recency decay       |            9 |    0.9228 |  0.5476 |     0.5882 |

Sources not ablatable here because they do not exist for free international data: betting-odds anchor (largest gap — see the EPL backtest where the market-anchored model gains ~0.03 log loss), news/availability, and true xG. The agent-level source ablation (kill a server, re-run) is exercised in evals/ via InProcessRunner(disabled=...).
