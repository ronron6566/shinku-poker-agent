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


class GtoPreflopAgent:
    """Plays preflop by sampling GTO Wizard's range tables (mixed strategy), and defers postflop
    decisions to HandStrengthAgent until the postflop ranges are also encoded."""

    def __init__(self):
        self._ranges: dict[str, dict] = {}
        for node in _RAISE_SIZE_BB:
            path = _RANGE_DIR / f"{node}.json"
            self._ranges[node] = json.loads(path.read_text()) if path.exists() else {}
        self._postflop = HandStrengthAgent()

    async def act(self, game_state: GameServiceResponse) -> ActRequest:
        gs = game_state.game_state
        if gs.street != "preflop":
            return await self._postflop.act(game_state)

        hero = next((p for p in gs.players if p.hole_cards is not None), None)
        node = self._node(gs, hero) if hero else None
        table = self._ranges.get(node, {}) if node else {}
        freqs = table.get(_hole_to_key(hero.hole_cards)) if hero and hero.hole_cards else None
        if not freqs:  # spot not covered by the tables (deeper bet trees, etc.) -> fall back
            return await self._postflop.act(game_state)

        action = random.choices(list(freqs), weights=list(freqs.values()), k=1)[0]
        big_blind = max(game_state.game.blinds) if game_state.game.blinds else 100
        return self._to_request(action, gs, node, big_blind)

    def _node(self, gs, hero) -> str | None:
        """Identify the preflop decision node from the hero's position and the action so far."""
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
                    return "sb_vs_raise"  # SB limped, BB raised
                if is_bet(preflop[0]) and is_bet(preflop[1]):
                    return "sb_vs_3bet"  # SB raised, BB 3bet
        elif hero.position == "BB":
            if len(preflop) == 1:
                if preflop[0] == "c":
                    return "bb_vs_limp"
                if is_bet(preflop[0]):
                    return "bb_vs_raise"
        return None

    def _to_request(self, action: str, gs, node: str, big_blind: int) -> ActRequest:
        legal = gs.legal_actions
        if action in ("raise", "3bet", "4bet"):
            if "b" in legal and gs.raise_range is not None:
                target = int(_RAISE_SIZE_BB[node] * big_blind)
                amount = max(int(gs.raise_range.min), min(target, int(gs.raise_range.max)))
                return ActRequest(action="b", amount=amount)
            return ActRequest(action="c" if "c" in legal else "k")
        if action == "check":
            return ActRequest(action="k" if "k" in legal else "c")
        if action == "fold":
            if "f" in legal:
                return ActRequest(action="f")
            return ActRequest(action="k" if "k" in legal else "c")
        # limp / call
        return ActRequest(action="c" if "c" in legal else "k")
