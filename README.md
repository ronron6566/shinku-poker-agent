# GTO Wizard AI Researcher API Client
Despite the growing interest in applying generalist AI agents and LLMs to games, a standardized platform for benchmarking their performance in poker has been lacking. We introduce GTO Wizard Research API: a public API that provides a standardized environment for benchmarking AI agents in No-Limit Texas Hold'em, the most popular variant of poker.

This API enables researchers to test their agents against [GTO Wizard AI](https://blog.gtowizard.com/introducing-gto-wizard-ai/), a proprietary state-of-the-art poker agent that demonstrated superior performance against [Slumbot](https://slumbot.com/), the past winner of the Annual Computer Poker Competition. Our system evaluates agents using [AIVAT](https://arxiv.org/abs/1612.06915), a provably unbiased low-variance technique for evaluating performance in imperfect information games, reducing the standard deviation by almost 10x in practice. We make the evaluation results publicly available through a free website and a real-time leaderboard.

## Documentation
To dive deeper on how to benchmark your agent against GTO Wizard AI, check out the [API documentation](https://researcher.gtowizard.com/docs).

## Technical Paper
Learn more about the benchmark and the methodology by checking out our technical paper:
[GTO Wizard Benchmark](https://arxiv.org/abs/2603.23660)

## Obtaining an API key
Visit https://benchmark.gtowizard.com/ and fill the form to request an API key. 

We will review your request, and if approved, you will receive your key via email. **Note that the API only gives access to playing hands and observing the result of the hand (chips won/lost)**. It doesn't give access to any of our solver capabilities and any requests for such features will be automatically refused. We also reserve the right to revoke your access at any time if we suspect that the API is being misused.

## Installation
**Prerequisites:**
- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager

**Setup:**
```bash
# Install dependencies
uv sync
```

## Usage

This repository provides skeleton agents to benchmark against GTO Wizard AI:
- **allin**: Always goes all-in when possible, otherwise calls
- **check_call** / **checkcall**: Always checks when possible, otherwise calls
- **random**: Samples uniformly from legal actions
- **fold**: Folds when possible, otherwise checks

**Run an agent:**
```bash
cd src && uv run python -m main --key YOUR_API_KEY --agent-type allin --num-hands 10
```
### Developing your own agent
To create a custom agent, add a new class in `src/poker_agent.py` that implements the `PokerAgent` protocol.
