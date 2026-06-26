import json
import random
from collections import Counter
from pathlib import Path
from typing import Protocol

from models import ActRequest, GameServiceResponse

# Card ranks from weakest to strongest; the index doubles as a numeric strength value.
_RANKS = "23456789TJQKA"


def _parse_cards(cards: str) -> list[tuple[int, str]]:
    """Parse a card string like "As6d" into [(rank_value, suit), ...]."""
    return [(_RANKS.index(cards[i]), cards[i + 1]) for i in range(0, len(cards), 2)]


def _hole_to_key(hole: str) -> str:
    """Convert hole cards like "As6d" into a range-grid key like "A6s"/"A6o"/"AA"."""
    (v1, s1), (v2, s2) = _parse_cards(hole)
    if v1 == v2:
        return _RANKS[v1] * 2
    hi, lo = (v1, v2) if v1 > v2 else (v2, v1)
    return _RANKS[hi] + _RANKS[lo] + ("s" if s1 == s2 else "o")


class PokerAgent(Protocol):
    async def act(self, game_state: GameServiceResponse) -> ActRequest: ...


class CheckCallAgent:
    async def act(self, game_state: GameServiceResponse) -> ActRequest:
        legal_actions = game_state.game_state.legal_actions
        action = "k" if "k" in legal_actions else "c"
        return ActRequest(action=action)


class AllinAgent:
    async def act(self, game_state: GameServiceResponse) -> ActRequest:
        legal_actions = game_state.game_state.legal_actions
        if "b" in legal_actions:
            action = "b"
            amount = game_state.game_state.raise_range.max
        else:
            action = "c"
            amount = None
        return ActRequest(action=action, amount=amount)


class RandomUniformAgent:
    async def act(self, game_state: GameServiceResponse) -> ActRequest:
        legal_actions = game_state.game_state.legal_actions
        sampled_action = random.choice(legal_actions)
        amount = None
        if sampled_action == "b":
            amount = int(random.uniform(game_state.game_state.raise_range.min, game_state.game_state.raise_range.max))
        return ActRequest(action=sampled_action, amount=amount)


class AlwaysFoldAgent:
    async def act(self, game_state: GameServiceResponse) -> ActRequest:
        legal_actions = game_state.game_state.legal_actions
        if "f" in legal_actions:
            action = "f"
        else:
            action = "k"
        return ActRequest(action=action)


class HandStrengthAgent:
    """A simple tight-aggressive agent that bets/calls strong hands and folds weak ones.

    Hand strength is bucketed into three levels (0 weak, 1 medium, 2 strong):
      - Strong: bet ~3/4 pot if we can open, otherwise call.
      - Medium: check when free, call a bet, but never build the pot ourselves.
      - Weak: check if free, otherwise fold.
    This is deliberately basic; it is meant as a baseline to improve on, not a solver.
    """

    async def act(self, game_state: GameServiceResponse) -> ActRequest:
        gs = game_state.game_state
        legal = gs.legal_actions

        hero = next((p for p in gs.players if p.hole_cards is not None), None)
        hole = _parse_cards(hero.hole_cards) if hero and hero.hole_cards else []
        board = _parse_cards(gs.board_cards) if gs.board_cards else []
        strength = self._strength(hole, board)

        can_bet = "b" in legal and gs.raise_range is not None
        if strength == 2:
            if can_bet:
                return ActRequest(action="b", amount=self._bet_amount(gs, 0.75))
            if "c" in legal:
                return ActRequest(action="c")
        elif strength == 1:
            if "k" in legal:
                return ActRequest(action="k")
            if "c" in legal:
                return ActRequest(action="c")

        if "k" in legal:
            return ActRequest(action="k")
        if "f" in legal:
            return ActRequest(action="f")
        return ActRequest(action="c")

    def _bet_amount(self, gs, pot_fraction: float) -> int:
        """A pot-fraction-sized bet, clamped to the legal raise range."""
        target = int(gs.total_pot * pot_fraction)
        return max(int(gs.raise_range.min), min(target, int(gs.raise_range.max)))

    def _strength(self, hole: list[tuple[int, str]], board: list[tuple[int, str]]) -> int:
        if len(hole) < 2:
            return 0
        rank_a, rank_b = hole[0][0], hole[1][0]
        suited = hole[0][1] == hole[1][1]
        ten, queen, ace = _RANKS.index("T"), _RANKS.index("Q"), _RANKS.index("A")

        if not board:  # preflop: judge from hole cards alone
            if rank_a == rank_b:
                return 2 if rank_a >= ten else 1  # TT+ strong, smaller pairs medium
            high, low = max(rank_a, rank_b), min(rank_a, rank_b)
            if high == ace and low >= queen:
                return 2  # AK, AQ
            if high >= queen:
                return 1  # a high card
            if suited and abs(rank_a - rank_b) <= 2:
                return 1  # suited connector-ish
            return 0

        # postflop: completed flush/straight beat everything else we track
        flush = self._flush_count(hole, board)
        straight = self._straight_count(hole, board)
        if flush >= 5 or straight >= 5:
            return 2

        # did we make a pair (or better) with the board?
        board_ranks = [card[0] for card in board]
        top_board = max(board_ranks)
        if rank_a == rank_b:  # pocket pair
            return 2 if rank_a > top_board else 1  # overpair strong, underpair medium
        matches = [rank for rank in (rank_a, rank_b) if rank in board_ranks]
        if len(matches) == 2:
            return 2  # two pair
        if matches:
            return 2 if matches[0] == top_board else 1  # top pair strong, weaker pair medium

        # no made hand, but a flush or straight draw is worth continuing with
        if flush == 4 or straight == 4:
            return 1
        return 0

    def _flush_count(self, hole, board) -> int:
        """Largest count of same-suit cards in a suit we actually hold (4 = draw, 5+ = made flush)."""
        hole_suits = {suit for _, suit in hole}
        counts = Counter(suit for _, suit in hole + board)
        relevant = [count for suit, count in counts.items() if suit in hole_suits]
        return max(relevant) if relevant else 0

    def _straight_count(self, hole, board) -> int:
        """Best number of distinct ranks in a 5-rank window that includes one of our hole cards.

        4 means an open-ended or gutshot straight draw, 5 means a completed straight.
        """
        ace = _RANKS.index("A")
        ranks = {rank for rank, _ in hole + board}
        hole_ranks = {rank for rank, _ in hole}
        if ace in ranks:  # an ace can also play as the low end of A-2-3-4-5
            ranks.add(-1)
        if ace in hole_ranks:
            hole_ranks.add(-1)
        best = 0
        for low in range(-1, 9):
            window = set(range(low, low + 5))
            if window & hole_ranks:  # the draw must use one of our cards
                best = max(best, len(ranks & window))
        return best


# Preflop range tables (generated by range/parse_ranges.py) and the raise size (in bb) per node.
_RANGE_DIR = Path(__file__).parent.parent / "range" / "preflop"
_RAISE_SIZE_BB = {
    "sb_open": 2.5,
    "bb_vs_raise": 8.0,
    "bb_vs_limp": 5.0,
    "sb_vs_3bet": 27.0,
    "sb_vs_raise": 15.0,
}


def _split_cards(s: str | None) -> list[str]:
    return [s[i : i + 2] for i in range(0, len(s), 2)] if s else []


class GtoAgent:
    """Preflop: sample GTO Wizard's range tables (mixed). Postflop: reconstruct the opponent's range
    from the preflop line, narrow it street-by-street under the assumption the opponent plays this
    same strategy, then act on equity vs that range and pot odds. Every action carries a reason
    string explaining the decision (captured for the DB / replay UI)."""

    def __init__(self):
        self._ranges: dict[str, dict] = {}
        for node in _RAISE_SIZE_BB:
            path = _RANGE_DIR / f"{node}.json"
            self._ranges[node] = json.loads(path.read_text()) if path.exists() else {}
        self._postflop = HandStrengthAgent()

    async def act(self, game_state: GameServiceResponse) -> ActRequest:
        gs = game_state.game_state
        big_blind = max(game_state.game.blinds) if game_state.game.blinds else 100
        hero = next((p for p in gs.players if p.hole_cards is not None), None)
        if hero is None or hero.hole_cards is None:
            return ActRequest(action="k" if "k" in gs.legal_actions else "c", reason="no hole cards")

        if gs.street == "preflop":
            return self._preflop(gs, hero, big_blind)
        return self._postflop_decision(gs, hero, big_blind)

    # ----- preflop -----
    def _preflop(self, gs, hero, big_blind: int) -> ActRequest:
        node = self._node(gs, hero)
        table = self._ranges.get(node, {}) if node else {}
        key = _hole_to_key(hero.hole_cards)
        freqs = table.get(key)
        if not freqs:
            req = self._postflop_fallback(gs, "preflop spot not in tables")
            return req
        action = random.choices(list(freqs), weights=list(freqs.values()), k=1)[0]
        mix = ", ".join(f"{a} {p:.0%}" for a, p in freqs.items())
        reason = f"preflop {node}: {key} [{mix}] → sampled {action}"
        return self._to_request(action, gs, node, big_blind, reason)

    def _node(self, gs, hero) -> str | None:
        preflop = []
        for a in gs.action_history:
            if a == "_":
                break
            preflop.append(a)
        is_bet = lambda a: a.startswith("b")  # noqa: E731
        if hero.position == "SB":
            if len(preflop) == 0:
                return "sb_open"
            if len(preflop) == 2:
                if preflop[0] == "c" and is_bet(preflop[1]):
                    return "sb_vs_raise"
                if is_bet(preflop[0]) and is_bet(preflop[1]):
                    return "sb_vs_3bet"
        elif hero.position == "BB":
            if len(preflop) == 1:
                if preflop[0] == "c":
                    return "bb_vs_limp"
                if is_bet(preflop[0]):
                    return "bb_vs_raise"
        return None

    def _to_request(self, action: str, gs, node: str, big_blind: int, reason: str) -> ActRequest:
        legal = gs.legal_actions
        if action in ("raise", "3bet", "4bet"):
            if "b" in legal and gs.raise_range is not None:
                target = int(_RAISE_SIZE_BB[node] * big_blind)
                amount = max(int(gs.raise_range.min), min(target, int(gs.raise_range.max)))
                return ActRequest(action="b", amount=amount, reason=reason)
            return ActRequest(action="c" if "c" in legal else "k", reason=reason + " (can't raise)")
        if action == "check":
            return ActRequest(action="k" if "k" in legal else "c", reason=reason)
        if action == "fold":
            if "f" in legal:
                return ActRequest(action="f", reason=reason)
            return ActRequest(action="k" if "k" in legal else "c", reason=reason + " (can't fold)")
        return ActRequest(action="c" if "c" in legal else "k", reason=reason)  # limp / call

    # ----- postflop -----
    def _postflop_fallback(self, gs, why: str) -> ActRequest:
        legal = gs.legal_actions
        if "k" in legal:
            return ActRequest(action="k", reason=f"fallback ({why}): check")
        if "c" in legal:
            return ActRequest(action="c", reason=f"fallback ({why}): call")
        return ActRequest(action="f", reason=f"fallback ({why}): fold")

    def _postflop_decision(self, gs, hero, big_blind: int) -> ActRequest:
        import postflop as pf

        hole = _split_cards(hero.hole_cards)
        board = _split_cards(gs.board_cards)
        preflop = pf._split_streets(gs.action_history)[0]
        vnode = pf.villain_preflop_node(hero.position, preflop)
        if vnode is None:
            return self._postflop_fallback(gs, "deep preflop line")

        dead = set(hole) | set(board)
        vrange = pf.reconstruct_range(vnode[0], vnode[1], dead)
        vrange = pf.narrow_villain_range(vrange, gs.action_history, hero.position, board)
        equity = pf.equity_vs_range(hole, board, vrange)
        to_call = pf.to_call_postflop(gs.action_history, hero.position)
        pot = gs.total_pot
        legal = gs.legal_actions
        can_bet = "b" in legal and gs.raise_range is not None

        def clamp(x):
            return max(int(gs.raise_range.min), min(int(x), int(gs.raise_range.max)))

        head = f"{gs.street}: eq {equity:.0%} vs villain({len(vrange)})"

        if to_call > 0 and "c" in legal:  # facing a bet
            req = to_call / (pot + to_call)
            if equity >= 0.80 and can_bet:
                return ActRequest(action="b", amount=clamp(pot), reason=f"{head} | strong, raise for value")
            if equity >= req:
                return ActRequest(action="c", reason=f"{head} | potodds {req:.0%} → call")
            if "f" in legal:
                return ActRequest(action="f", reason=f"{head} | potodds {req:.0%} → fold")
            return ActRequest(action="c", reason=f"{head} | can't fold → call")

        # no bet to face: bet for value, occasionally bluff, else check
        if equity >= 0.62 and can_bet:
            return ActRequest(action="b", amount=clamp(0.66 * pot), reason=f"{head} | value bet 0.66 pot")
        if equity <= 0.35 and can_bet and random.random() < 0.3:
            return ActRequest(action="b", amount=clamp(0.5 * pot), reason=f"{head} | bluff 0.5 pot")
        if "k" in legal:
            return ActRequest(action="k", reason=f"{head} | check")
        return ActRequest(action="c" if "c" in legal else "f", reason=f"{head} | no check → call/fold")
