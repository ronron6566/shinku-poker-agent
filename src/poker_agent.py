import random
from typing import Protocol

from models import ActRequest, GameServiceResponse


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
