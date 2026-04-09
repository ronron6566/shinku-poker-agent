import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import main as main_module
from models import (
    ActionRange,
    ActRequest,
    GameModel,
    GameServiceResponse,
    GameState,
    NewHandRequest,
    Player,
)
from poker_agent import CheckCallAgent


def _build_game_service_response(
    *,
    is_hand_over: bool,
    legal_actions: list[str],
    action_history: list[str] | None = None,
    raise_min: int = 50,
    raise_max: int = 200,
    winnings: float | None = None,
    aivat_score: float | None = None,
) -> GameServiceResponse:
    raise_range = ActionRange(min=raise_min, max=raise_max) if "b" in legal_actions else None
    return GameServiceResponse(
        hand_id=1,
        game=GameModel(
            game_id=1,
            game_name="HUNL 200BB",
            game_format="HUNL",
            starting_stack=200.0,
            blinds=[0.5, 1.0],
            stack_reset_per_hand=True,
        ),
        game_state=GameState(
            street="preflop",
            common_pot=1.5,
            total_pot=1.5,
            board_cards="",
            is_hand_over=is_hand_over,
            players=[
                Player(
                    name="hero",
                    stack=200.0,
                    position="SB",
                    hole_cards="AhAd",
                ),
                Player(
                    name="GTO Wizard",
                    stack=200.0,
                    position="BB",
                    hole_cards=None,
                ),
            ],
            legal_actions=legal_actions,
            raise_range=raise_range,
            action_history=action_history or [],
            has_gto_wizard_folded=False,
            winnings=winnings,
            aivat_score=aivat_score,
        ),
    )


class BenchmarkRunnerE2ETest(unittest.IsolatedAsyncioTestCase):
    async def test_run_plays_single_hand_against_mock_api(self) -> None:
        requests: list[tuple[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/hands":
                payload = NewHandRequest.model_validate_json(request.content)
                requests.append((request.url.path, payload))
                self.assertEqual(payload, NewHandRequest(game_name="HUNL 200BB"))
                return httpx.Response(
                    200,
                    json=_build_game_service_response(
                        is_hand_over=False,
                        legal_actions=["k", "c", "b"],
                    ).model_dump(mode="json"),
                )

            if request.url.path == "/hands/1/act":
                payload = ActRequest.model_validate_json(request.content)
                requests.append((request.url.path, payload))
                self.assertEqual(payload, ActRequest(action="k"))
                return httpx.Response(
                    200,
                    json=_build_game_service_response(is_hand_over=True, legal_actions=["k"], action_history=["k"], winnings=1.0, aivat_score=1.25).model_dump(mode="json"),
                )

            raise AssertionError(f"Unexpected request path: {request.url.path}")

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(
            base_url="https://example.test",
            headers={"X-API-Key": "test-key"},
            transport=transport,
        )

        async with client:
            runner = main_module.BenchmarkRunner(
                client,
                CheckCallAgent(),
                num_concurrent_hands=1,
                game_name="HUNL 200BB",
            )
            await runner.run(1)

        self.assertEqual(requests, [
            ("/hands", NewHandRequest(game_name="HUNL 200BB")),
            ("/hands/1/act", ActRequest(action="k")),
        ])


class MainEntrypointTest(unittest.IsolatedAsyncioTestCase):
    async def test_main_runs_real_benchmark_runner_with_requested_agent(self) -> None:
        requests: list[tuple[str, object]] = []
        client_configs: list[dict] = []
        real_async_client = httpx.AsyncClient

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/hands":
                payload = NewHandRequest.model_validate_json(request.content)
                requests.append((request.url.path, payload))
                self.assertEqual(payload, NewHandRequest(game_name="HUNL 200BB"))
                return httpx.Response(
                    200,
                    json=_build_game_service_response(
                        is_hand_over=False,
                        legal_actions=["f", "c"],
                    ).model_dump(mode="json"),
                )

            if request.url.path == "/hands/1/act":
                payload = ActRequest.model_validate_json(request.content)
                requests.append((request.url.path, payload))
                self.assertEqual(payload, ActRequest(action="f"))
                return httpx.Response(
                    200,
                    json=_build_game_service_response(is_hand_over=True, legal_actions=["k"], action_history=["f"], winnings=-1.0, aivat_score=-0.8).model_dump(mode="json"),
                )

            raise AssertionError(f"Unexpected request path: {request.url.path}")

        def async_client_factory(*args, **kwargs) -> httpx.AsyncClient:
            client_configs.append(kwargs)
            return real_async_client(*args, transport=httpx.MockTransport(handler), **kwargs)

        with patch.object(main_module.httpx, "AsyncClient", side_effect=async_client_factory):
            await main_module.main(
                key="secret-key",
                num_concurrent_hands=4,
                agent_type="fold",
                num_hands=1,
                url="https://example.test",
                game="HUNL 200BB",
            )

        self.assertEqual(len(client_configs), 1)
        self.assertEqual(client_configs[0]["base_url"], "https://example.test")
        self.assertEqual(client_configs[0]["headers"], {"X-API-Key": "secret-key"})
        self.assertEqual(client_configs[0]["limits"].max_keepalive_connections, 4)
        self.assertEqual(client_configs[0]["limits"].max_connections, 8)
        self.assertEqual(requests, [
            ("/hands", NewHandRequest(game_name="HUNL 200BB")),
            ("/hands/1/act", ActRequest(action="f")),
        ])
