import asyncio
import logging
import time

import httpx
import structlog
from fire import Fire
from tenacity import RetryCallState, retry, retry_if_exception, stop_after_attempt, wait_exponential
from tqdm.asyncio import tqdm

from models import GameServiceResponse, NewHandRequest
from poker_agent import AllinAgent, AlwaysFoldAgent, CheckCallAgent, PokerAgent, RandomUniformAgent
from utils import is_engine_busy_exception

_DEFAULT_GAME_NAME = "HUNL 200BB"
_DEFAULT_API_URL = "https://researcher.gtowizard.com"
# Number of hands to play concurrently. Max number of allowed concurrent hands as of 2026-04-09 is 20
# but it's recommended to set a smaller number so the script continues even if some hands fail.
# It's possible to retrieve active hands to continue a hand that failed using one of the API endpoint (see documentation).
_DEFAULT_NUM_CONCURRENT_HANDS = 5
_NUM_HANDS = 100
_SUPPORTED_AGENTS = {
    "allin": AllinAgent,
    "check_call": CheckCallAgent,
    "checkcall": CheckCallAgent,
    "random": RandomUniformAgent,
    "fold": AlwaysFoldAgent,
}
logger = structlog.get_logger(__name__)
logging.getLogger("httpx").disabled = True


def _format_http_error(exception: httpx.HTTPStatusError) -> str:
    status_code = exception.response.status_code
    error_message = exception.response.text.strip() or exception.response.reason_phrase
    return f"{status_code} {error_message}" if error_message else str(status_code)


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
    ):
        self._client = client
        self._agent = agent
        self._game_name = game_name
        self._semaphore = asyncio.Semaphore(num_concurrent_hands)

    @classmethod
    def from_config(
        cls,
        agent: PokerAgent,
        api_url: str,
        key: str,
        num_concurrent_hands: int,
        game_name: str,
    ) -> "BenchmarkRunner":
        limits = httpx.Limits(max_keepalive_connections=num_concurrent_hands, max_connections=num_concurrent_hands * 2)
        client = httpx.AsyncClient(
            base_url=api_url,
            headers={"X-API-Key": key},
            timeout=180,
            limits=limits,
        )
        return cls(client, agent, num_concurrent_hands, game_name)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._client.aclose()

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

    async def _play_hand(self) -> bool:
        hand_id = None
        async with self._semaphore:
            try:
                game_service_response = await self._create_new_hand()
                hand_id = game_service_response.hand_id

                while not game_service_response.game_state.is_hand_over:
                    game_service_response = await self._act(hand_id, game_service_response)
                return True
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"{_format_http_error(e)} after exhausting retries",
                    extra={"hand_id": hand_id, "response_text": e.response.text},
                )
                if not is_engine_busy_exception(e):
                    raise
                return False
            except Exception as e:
                logger.error(f"Unexpected error: {e}", extra={"hand_id": hand_id})
                return False

    async def _cancel_pending_hands(self, hands: list[asyncio.Task[bool]]) -> None:
        for hand in hands:
            if not hand.done():
                hand.cancel()
        await asyncio.gather(*hands, return_exceptions=True)

    async def run(self, num_hands: int) -> None:
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
        successful_hands = sum(results)
        failed_hands = len(results) - successful_hands
        seconds_per_hand = duration / num_hands if num_hands > 0 else 0
        logger.info("Benchmark finished")
        logger.info(
            f"Successful hands: {successful_hands}. Failed hands: {failed_hands}. Average seconds/hand: {seconds_per_hand:.3f}"
        )


async def main(
    key: str,
    num_concurrent_hands: int = _DEFAULT_NUM_CONCURRENT_HANDS,
    agent_type: str = "allin",
    num_hands: int = _NUM_HANDS,
    url: str = _DEFAULT_API_URL,
    game: str = _DEFAULT_GAME_NAME,
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
    """
    resolved_agent_type = agent_type.lower()
    agent_class = _SUPPORTED_AGENTS.get(resolved_agent_type)
    if agent_class is None:
        supported = ", ".join(_SUPPORTED_AGENTS.keys())
        raise ValueError(f"agent_type must be one of [{supported}], got: {resolved_agent_type}")

    benchmark_agent = agent_class()
    async with BenchmarkRunner.from_config(benchmark_agent, url, key, num_concurrent_hands, game) as runner:
        await runner.run(num_hands)


if __name__ == "__main__":
    Fire(lambda **kwargs: asyncio.run(main(**kwargs)))
