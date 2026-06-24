import random
from typing import Protocol

from models import ActRequest, GameServiceResponse

# Card ranks from weakest to strongest; the index doubles as a numeric strength value.
_RANKS = "23456789TJQKA"


def _parse_cards(cards: str) -> list[tuple[int, str]]:
    """Parse a card string like "As6d" into [(rank_value, suit), ...]."""
    return [(_RANKS.index(cards[i]), cards[i + 1]) for i in range(0, len(cards), 2)]


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

        # postflop: did we make a pair (or better) with the board?
        board_ranks = [card[0] for card in board]
        top_board = max(board_ranks)
        if rank_a == rank_b:  # pocket pair
            return 2 if rank_a > top_board else 1  # overpair strong, underpair medium
        matches = [rank for rank in (rank_a, rank_b) if rank in board_ranks]
        if len(matches) == 2:
            return 2  # two pair
        if matches:
            return 2 if matches[0] == top_board else 1  # top pair strong, weaker pair medium
        return 0
