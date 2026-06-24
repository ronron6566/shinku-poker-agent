# CLAUDE.md

Guidance for working in this repository. Keep this file short; put user-facing usage in `README.md`.

## Overview

A client for the **GTO Wizard Researcher API**. It plays heads-up No-Limit Hold'em hands of your
poker agent against GTO Wizard AI (the opponent runs server-side) and benchmarks the result, scored
with AIVAT (a luck-adjusted win rate). Everything here is client-side; we only send actions over HTTP.

## Commands

```bash
uv sync                                                              # install deps
cd src && uv run python -m main --agent-type strength --num-hands 10 # run a benchmark
cd src && uv run python -m main --agent-type strength --log-file hands.jsonl  # + per-hand JSONL
```

- The API key comes from `--key`, or `GTOW_API_KEY` in a project-root `.env` when `--key` is omitted.
- `agent_type` is one of the keys in `_SUPPORTED_AGENTS` (main.py): `allin`, `check_call`, `random`,
  `fold`, `strength`.

## Architecture

- `src/main.py` — `BenchmarkRunner` orchestrates concurrent hands (semaphore), retries, and the
  end-of-run summary; `_SUPPORTED_AGENTS` maps `agent_type` → class; `main` is the Fire entrypoint.
- `src/poker_agent.py` — the `PokerAgent` protocol (one `async act()` method) and all agent classes.
- `src/models.py` — Pydantic models for the API request/response schemas. Read this for field meanings.
- `src/utils.py` — `is_engine_busy_exception` (which HTTP statuses are retried).

## Adding an agent (the main extension point)

1. Add a class in `poker_agent.py` with `async def act(self, game_state) -> ActRequest`.
2. Register it in `_SUPPORTED_AGENTS` in `main.py`.

Use `HandStrengthAgent` as the reference implementation. The runner handles looping, concurrency, and
retries — an agent only decides one action at a time.

## The `act()` contract

Input is a `GameServiceResponse`; the live state is in `game_state.game_state` (a `GameState`):
- `players` — your own `hole_cards` are set; **the opponent's are `None` during play**, so identify
  the hero with `next(p for p in players if p.hole_cards is not None)`.
- `legal_actions` — subset of `{"f","c","k","b"}` that is legal right now.
- `raise_range` — `.min`/`.max` for bet sizing (`None` when you cannot bet).
- `total_pot` — use this for pot-fraction bet sizing and pot odds (not `common_pot`; see below).
- `action_history` — e.g. `["b225","c","_","b900","f"]`: `bX`=bet to cumulative X this round,
  `c`=call, `k`=check, `f`=fold, `_`=end of a betting round.

Output is an `ActRequest`. Rules (otherwise the server rejects it):
- `action` must be in `legal_actions`.
- `action="b"` requires `amount` (int) within `raise_range.min..max`; other actions take no amount.

Cards are strings like `"As6d"`; rank strength order is `23456789TJQKA`.

## Domain notes (not obvious from code)

- `winnings` = actual chips won/lost. `aivat_score` = luck-adjusted expectation (the leaderboard's
  "luck-adjusted win rate"); a hand can lose chips but score positive AIVAT if the decision was good.
- Win rates are reported in **bb/100** (big blinds per 100 hands) — a normalized rate, not a hand count.
- `total_pot = common_pot + bets still outstanding this round`; they differ only mid-round. Strategy
  code should use `total_pot`.

## Gotchas

- A newly issued API key can take **up to 24h to activate**; a `401 "Invalid API Key"` before then is
  expected — wait, don't assume the key is wrong.
- `.env` must be `GTOW_API_KEY=<value>` (a bare value on its own line is silently ignored).
- `503`/`502`/`504` mean the engine is busy and are **auto-retried** (logged at info level); this is
  normal, not a failure.
