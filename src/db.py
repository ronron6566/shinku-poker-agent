"""Persistence of benchmark runs to Postgres (e.g. Neon).

A run is written once, after the benchmark finishes: one row in `runs` plus one row per hand in
`hands`. The hand records are the plain dicts produced by `main._hand_record`.
"""

import json

import psycopg

_OPPONENT_NAME = "GTO Wizard"


def _hero_villain(players: list[dict]) -> tuple[dict | None, dict | None]:
    hero = next((p for p in players if p["name"] != _OPPONENT_NAME), None)
    villain = next((p for p in players if p["name"] == _OPPONENT_NAME), None)
    return hero, villain


async def save_run(db_url: str, summary: dict, hands: list[dict]) -> int:
    """Insert one run and its hands in a single transaction; return the new run id."""
    async with await psycopg.AsyncConnection.connect(db_url) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                insert into runs (
                    agent_type, game_name, num_hands, successful_hands, failed_hands,
                    duration_seconds, big_blind, total_winnings, winrate_bb100, aivat_bb100,
                    hands_won, opponent_fold_rate
                ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning id
                """,
                (
                    summary["agent_type"],
                    summary["game_name"],
                    summary["num_hands"],
                    summary["successful_hands"],
                    summary["failed_hands"],
                    summary["duration_seconds"],
                    summary["big_blind"],
                    summary["total_winnings"],
                    summary["winrate_bb100"],
                    summary["aivat_bb100"],
                    summary["hands_won"],
                    summary["opponent_fold_rate"],
                ),
            )
            run_id = (await cur.fetchone())[0]

            for hand in hands:
                hero, villain = _hero_villain(hand["players"])
                await cur.execute(
                    """
                    insert into hands (
                        run_id, hand_id, street, board_cards, action_history, total_pot,
                        winnings, aivat_score, has_gto_wizard_folded, hero_position,
                        hero_hole_cards, villain_hole_cards, players, decisions
                    ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        hand["hand_id"],
                        hand["street"],
                        hand["board_cards"],
                        json.dumps(hand["action_history"]),
                        hand["total_pot"],
                        hand["winnings"],
                        hand["aivat_score"],
                        hand["has_gto_wizard_folded"],
                        hero["position"] if hero else None,
                        hero["hole_cards"] if hero else None,
                        villain["hole_cards"] if villain else None,
                        json.dumps(hand["players"]),
                        json.dumps(hand.get("decisions", [])),
                    ),
                )
        await conn.commit()
    return run_id
