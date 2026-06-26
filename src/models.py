from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GameModel(BaseModel):
    game_id: int
    game_name: str
    game_format: str
    starting_stack: float
    blinds: list[float]
    stack_reset_per_hand: bool


class ActionRange(BaseModel):
    min: float
    max: float


class Player(BaseModel):
    name: str
    stack: float
    position: str
    hole_cards: str | None


class GameState(BaseModel):
    street: Literal["preflop", "flop", "turn", "river"]
    common_pot: float
    total_pot: float
    board_cards: str
    is_hand_over: bool
    players: list[Player]
    legal_actions: list[str] = Field(
        description="""
        *Base* actions that are *legal* at this node, based on the rules of the game.
        Possible values are {"f", "c", "k", "b"}
        """
    )
    raise_range: ActionRange | None
    action_history: list[str] = Field(
        description="""
        List of actions that happened in the hand:
        '_': end of round
        'f': Fold
        'c': Call
        'k': Check
        'bX' bet X (cumulative bet on round)
        """
    )
    has_gto_wizard_folded: bool
    winnings: float | None = Field(description="Chips won/lost from the user perspective. None if hand is not over.")
    aivat_score: float | None = Field(
        description="""
        How many of the villain's chips the hero was expected to win this hand, adjusted for luck.
        Based on the researcher paper `AIVAT: A New Variance Reduction Technique for Agent Evaluation in Imperfect Information Games`
        Neil Burch, Martin Schmid, Matej Moravčík, Michael Bowling
        None if hand is not over.
        """
    )


class GameServiceResponse(BaseModel):
    hand_id: int
    game: GameModel
    game_state: GameState


class ActRequest(BaseModel):
    action: Literal["f", "k", "c", "b"] = Field(
        ...,
        description="""'f': Fold
        'c': Call
        'k': Check
        'b': Bet""",
    )
    amount: int | None = Field(default=None, description="Amount of the bet action")
    # Human-readable explanation of why the agent chose this action. Excluded from the API payload
    # (the server only wants action/amount); captured by the runner for logging/DB.
    reason: str | None = Field(default=None, exclude=True)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "action": "b",
                "amount": 300,
            }
        }
    )

    @model_validator(mode="after")
    def validate_amount_for_action(self) -> "ActRequest":
        if self.action == "b" and self.amount is None:
            raise ValueError(f"Amount is required for action '{self.action}'")
        return self


class NewHandRequest(BaseModel):
    game_name: Literal["HUNL 200BB"]
