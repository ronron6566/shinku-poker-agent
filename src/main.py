import asyncio
import json
import logging
import math
import os
import statistics
import time

import httpx
import structlog
from dotenv import load_dotenv
from fire import Fire
from tenacity import RetryCallState, retry, retry_if_exception, stop_after_attempt, wait_exponential
from tqdm.asyncio import tqdm

from models import GameServiceResponse, NewHandRequest
from poker_agent import (
    AllinAgent,
    AlwaysFoldAgent,
    CheckCallAgent,
    HandStrengthAgent,
    PokerAgent,
    RandomUniformAgent,
)
from utils import is_engine_busy_exception

load_dotenv()

_DEFAULT_GAME_NAME = "HUNL 200BB"
_DEFAULT_API_URL = "https://researcher.gtowizard.com"
# Number of hands to play concurrently. Max number of allowed concurrent hands as of 2026-04-09 is 20
# but it's recommended to set a smaller number so the script continues even if some hands fail.
# It's also possible to retrieve active hands, in order to continue a hand that failed, using one of the API endpoint (see API documentation).
_DEFAULT_NUM_CONCURRENT_HANDS = 5
_NUM_HANDS = 100
# Name of the opponent agent on the server side; every other player is the hero (our agent).
_OPPONENT_NAME = "GTO Wizard"
_SUPPORTED_AGENTS = {
    "allin": AllinAgent,
    "check_call": CheckCallAgent,
    "checkcall": CheckCallAgent,
    "random": RandomUniformAgent,
    "fold": AlwaysFoldAgent,
    "strength": HandStrengthAgent,
}
logger = structlog.get_logger(__name__)
logging.getLogger("httpx").disabled = True


def _format_http_error(exception: httpx.HTTPStatusError) -> str:
    status_code = exception.response.status_code
    error_message = exception.response.text.strip() or exception.response.reason_phrase
    return f"{status_code} {error_message}" if error_message else str(status_code)


def _hero_player(players: list) -> object | None:
    """Return the hero (our agent): the first player that is not the known opponent."""
    for player in players:
        if player.name != _OPPONENT_NAME:
            return player
    return None


def _format_winrate(label: str, values: list[float], big_blind: float) -> str:
    """Format a list of per-hand chip results as a bb/100 winrate with a 95% confidence interval."""
    n = len(values)
    bb_values = [v / big_blind for v in values]
    bb_per_100 = (sum(bb_values) / n) * 100
    if n > 1:
        sem = statistics.stdev(bb_values) / math.sqrt(n)
        return f"{label}: {bb_per_100:+.1f} bb/100 (95% CI ±{1.96 * sem * 100:.1f})"
    return f"{label}: {bb_per_100:+.1f} bb/100"


def _winrate_bb100(values: list[float], big_blind: float) -> float | None:
    """Numeric bb/100 win rate (no confidence interval), or None if there is no data."""
    if not values:
        return None
    return (sum(v / big_blind for v in values) / len(values)) * 100


def _hand_record(response: GameServiceResponse) -> dict:
    """Flatten a finished hand into a plain dict for JSONL logging and DB persistence."""
    game_state = response.game_state
    return {
        "hand_id": response.hand_id,
        "street": game_state.street,
        "board_cards": game_state.board_cards,
        "action_history": game_state.action_history,
        "total_pot": game_state.total_pot,
        "winnings": game_state.winnings,
        "aivat_score": game_state.aivat_score,
        "has_gto_wizard_folded": game_state.has_gto_wizard_folded,
        "players": [
            {"name": p.name, "position": p.position, "hole_cards": p.hole_cards, "stack": p.stack}
            for p in game_state.players
        ],
    }


def log_retry_attempt(retry_state: RetryCallState) -> None:
    exception = retry_state.outcome.exception()
    wait_time = retry_state.next_action.sleep
    hand_id = retry_state.kwargs.get("hand_id")
    if isinstance(exception, httpx.HTTPStatusError):
        error_msg = _format_http_error(exception)
    else:
        error_msg = str(exception)
    logger.info(
        f"{error_msg}. Retrying in {wait_time:.2f}s",
        extra={"hand_id": hand_id, "attempt": retry_state.attempt_number, "error": error_msg},
    )


class BenchmarkRunner:
    def __init__(
        self,
        client: httpx.AsyncClient,
        agent: PokerAgent,
        num_concurrent_hands: int,
        game_name: str,
        hand_log_path: str | None = None,
        agent_type: str = "",
    ):
        self._client = client
        self._agent = agent
        self._game_name = game_name
        self._agent_type = agent_type
        self._semaphore = asyncio.Semaphore(num_concurrent_hands)
        self._hand_log_path = hand_log_path
        self._hand_log_file = open(hand_log_path, "a") if hand_log_path else None
        self._hand_log_lock = asyncio.Lock()

    @classmethod
    def from_config(
        cls,
        agent: PokerAgent,
        api_url: str,
        key: str,
        num_concurrent_hands: int,
        game_name: str,
        hand_log_path: str | None = None,
        agent_type: str = "",
    ) -> "BenchmarkRunner":
        limits = httpx.Limits(max_keepalive_connections=num_concurrent_hands, max_connections=num_concurrent_hands * 2)
        client = httpx.AsyncClient(
            base_url=api_url,
            headers={"X-API-Key": key},
            timeout=180,
            limits=limits,
        )
        return cls(client, agent, num_concurrent_hands, game_name, hand_log_path, agent_type)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._client.aclose()
        if self._hand_log_file is not None:
            self._hand_log_file.close()

    async def _log_hand(self, response: GameServiceResponse) -> None:
        if self._hand_log_file is None:
            return
        line = json.dumps(_hand_record(response)) + "\n"
        async with self._hand_log_lock:
            self._hand_log_file.write(line)
            self._hand_log_file.flush()

    @retry(
        retry=retry_if_exception(is_engine_busy_exception),
        stop=stop_after_attempt(32),
        wait=wait_exponential(multiplier=2, min=2, max=32),
        before_sleep=log_retry_attempt,
        reraise=True,
    )
    async def _post(
        self,
        url: str,
        json_data: dict[str, object],
        hand_id: int | None = None,
        game_state: GameServiceResponse | None = None,
    ) -> httpx.Response:
        response = await self._client.post(url, json=json_data)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exception:
            if not is_engine_busy_exception(exception):
                logger.error(
                    "Non-retryable API request failed",
                    extra={
                        "hand_id": hand_id,
                        "url": url,
                        "status_code": exception.response.status_code,
                        "reason_phrase": exception.response.reason_phrase,
                        "response_text": exception.response.text,
                        "request_payload": json_data,
                        "hand_state": game_state.model_dump(mode="json") if game_state is not None else None,
                    },
                )
            raise
        return response

    async def _create_new_hand(self) -> GameServiceResponse:
        request = NewHandRequest(game_name=self._game_name).model_dump()
        response = await self._post("/hands", json_data=request)
        return GameServiceResponse(**response.json())

    async def _act(self, hand_id: int, game_state: GameServiceResponse) -> GameServiceResponse:
        action_request = await self._agent.act(game_state)
        response = await self._post(
            f"/hands/{hand_id}/act",
            json_data=action_request.model_dump(),
            hand_id=hand_id,
            game_state=game_state,
        )
        return GameServiceResponse(**response.json())

    async def _play_hand(self) -> GameServiceResponse | None:
        hand_id = None
        async with self._semaphore:
            try:
                game_service_response = await self._create_new_hand()
                hand_id = game_service_response.hand_id

                while not game_service_response.game_state.is_hand_over:
                    game_service_response = await self._act(hand_id, game_service_response)
                await self._log_hand(game_service_response)
                return game_service_response
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"{_format_http_error(e)} after exhausting retries",
                    extra={"hand_id": hand_id, "response_text": e.response.text},
                )
                if not is_engine_busy_exception(e):
                    raise
                return None
            except Exception as e:
                logger.error(f"Unexpected error: {e}", extra={"hand_id": hand_id})
                return None

    async def _cancel_pending_hands(self, hands: list[asyncio.Task[GameServiceResponse | None]]) -> None:
        for hand in hands:
            if not hand.done():
                hand.cancel()
        await asyncio.gather(*hands, return_exceptions=True)

    async def run(self, num_hands: int) -> tuple[dict, list[dict]]:
        logger.info(f"Starting benchmark for {num_hands} hands on game '{self._game_name}'")
        start_time = time.time()
        hands = [asyncio.create_task(self._play_hand()) for _ in range(num_hands)]
        results = []
        try:
            for hand in tqdm.as_completed(hands, total=num_hands, desc="Playing hands"):
                result = await hand
                results.append(result)
        except Exception as e:
            if isinstance(e, httpx.HTTPStatusError):
                logger.error(f"Aborting benchmark: {_format_http_error(e)}")
            await self._cancel_pending_hands(hands)
            raise

        end_time = time.time()
        duration = end_time - start_time
        successful = [r for r in results if r is not None]
        successful_hands = len(successful)
        failed_hands = len(results) - successful_hands
        seconds_per_hand = duration / num_hands if num_hands > 0 else 0
        logger.info("Benchmark finished")
        logger.info(
            f"Successful hands: {successful_hands}. Failed hands: {failed_hands}. Average seconds/hand: {seconds_per_hand:.3f}"
        )

        self._log_summary(successful)
        if self._hand_log_path is not None:
            logger.info(f"Hand history written to {self._hand_log_path}")

        summary = self._compute_summary(successful, num_hands, duration, successful_hands, failed_hands)
        return summary, [_hand_record(h) for h in successful]

    def _compute_summary(
        self,
        hands: list[GameServiceResponse],
        num_hands: int,
        duration: float,
        successful_hands: int,
        failed_hands: int,
    ) -> dict:
        blinds = hands[0].game.blinds if hands else None
        big_blind = max(blinds) if blinds else 1.0
        winnings = [h.game_state.winnings for h in hands if h.game_state.winnings is not None]
        aivat = [h.game_state.aivat_score for h in hands if h.game_state.aivat_score is not None]
        folds = sum(1 for h in hands if h.game_state.has_gto_wizard_folded)
        return {
            "agent_type": self._agent_type,
            "game_name": self._game_name,
            "num_hands": num_hands,
            "successful_hands": successful_hands,
            "failed_hands": failed_hands,
            "duration_seconds": duration,
            "big_blind": big_blind,
            "total_winnings": sum(winnings) if winnings else None,
            "winrate_bb100": _winrate_bb100(winnings, big_blind),
            "aivat_bb100": _winrate_bb100(aivat, big_blind),
            "hands_won": sum(1 for w in winnings if w > 0) if winnings else None,
            "opponent_fold_rate": (folds / len(hands)) if hands else None,
        }

    def _log_summary(self, hands: list[GameServiceResponse]) -> None:
        if not hands:
            return
        blinds = hands[0].game.blinds
        big_blind = max(blinds) if blinds else 1.0

        winnings = [h.game_state.winnings for h in hands if h.game_state.winnings is not None]
        aivat_scores = [h.game_state.aivat_score for h in hands if h.game_state.aivat_score is not None]

        if winnings:
            total_winnings = sum(winnings)
            wins = sum(1 for w in winnings if w > 0)
            logger.info(
                f"Total winnings: {total_winnings:.1f} chips. "
                f"Avg winnings/hand: {total_winnings / len(winnings):.2f}. "
                f"{_format_winrate('Winrate', winnings, big_blind)}"
            )
            logger.info(f"Hands won: {wins}/{len(winnings)} ({100 * wins / len(winnings):.1f}%)")
        if aivat_scores:
            logger.info(_format_winrate("AIVAT winrate", aivat_scores, big_blind))

        folds = sum(1 for h in hands if h.game_state.has_gto_wizard_folded)
        logger.info(f"{_OPPONENT_NAME} folded: {folds}/{len(hands)} ({100 * folds / len(hands):.1f}%)")

        by_position: dict[str, list[float]] = {}
        for hand in hands:
            hero = _hero_player(hand.game_state.players)
            if hero is None or hand.game_state.winnings is None:
                continue
            by_position.setdefault(hero.position, []).append(hand.game_state.winnings)
        for position in sorted(by_position):
            values = by_position[position]
            logger.info(f"  Position {position}: {len(values)} hands, {_format_winrate('winrate', values, big_blind)}")


async def main(
    key: str | None = None,
    num_concurrent_hands: int = _DEFAULT_NUM_CONCURRENT_HANDS,
    agent_type: str = "allin",
    num_hands: int = _NUM_HANDS,
    url: str = _DEFAULT_API_URL,
    game: str = _DEFAULT_GAME_NAME,
    log_file: str | None = None,
    db_url: str | None = None,
):
    """
    Runs poker agent benchmark.
    Args:
        key: User API Key to the Researcher API
        num_concurrent_hands: Number of hands to run concurrently
        agent_type: Type of agent to run
        num_hands: Total hands
        url: Researcher API URL
        game: Game name
        log_file: Optional path to write per-hand history as JSONL (one finished hand per line)
        db_url: Optional Postgres connection string to persist the run (defaults to $DATABASE_URL)
    """
    key = key or os.getenv("GTOW_API_KEY")
    if not key:
        raise ValueError("API key not provided. Set GTOW_API_KEY in .env or pass --key.")

    resolved_agent_type = agent_type.lower()
    agent_class = _SUPPORTED_AGENTS.get(resolved_agent_type)
    if agent_class is None:
        supported = ", ".join(_SUPPORTED_AGENTS.keys())
        raise ValueError(f"agent_type must be one of [{supported}], got: {resolved_agent_type}")

    benchmark_agent = agent_class()
    async with BenchmarkRunner.from_config(
        benchmark_agent, url, key, num_concurrent_hands, game, log_file, resolved_agent_type
    ) as runner:
        summary, hand_records = await runner.run(num_hands)

    db_url = db_url or os.getenv("DATABASE_URL")
    if db_url and hand_records:
        from db import save_run

        run_id = await save_run(db_url, summary, hand_records)
        logger.info(f"Saved run {run_id} to database ({len(hand_records)} hands)")


if __name__ == "__main__":
    Fire(lambda **kwargs: asyncio.run(main(**kwargs)))
