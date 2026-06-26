"""ポストフロップの基盤: 相手レンジの復元とエクイティ計算.

前提(ユーザー合意): 相手も自分と同じ戦略を取ると仮定する。これにより相手のポストフロップの
打ち方が自己無撞着に決まり、相手のレンジをアクションごとに狭め込める。このモジュールは下回り
(レンジ復元・エクイティ)を提供し、意思決定とレンジ狭め込みは別途その上に実装する。
"""

import json
import random
from pathlib import Path

from treys import Card, Evaluator

_RANKS = "AKQJT98765432"
_SUITS = "shdc"
_RANGE_DIR = Path(__file__).parent.parent / "range" / "preflop"
_EVAL = Evaluator()


def _load_ranges() -> dict[str, dict]:
    out = {}
    for node in ("sb_open", "bb_vs_raise", "bb_vs_limp", "sb_vs_3bet", "sb_vs_raise"):
        path = _RANGE_DIR / f"{node}.json"
        out[node] = json.loads(path.read_text()) if path.exists() else {}
    return out


_RANGES = _load_ranges()


def combos_for_key(key: str) -> list[tuple[str, str]]:
    """"AKs"/"AKo"/"AA" を具体的な2枚の組(例 ("Ah","Kh"))のリストに展開する."""
    r1, r2 = key[0], key[1]
    if r1 == r2:  # pair
        return [(r1 + _SUITS[i], r2 + _SUITS[j]) for i in range(4) for j in range(i + 1, 4)]
    if key.endswith("s"):
        return [(r1 + s, r2 + s) for s in _SUITS]
    return [(r1 + s1, r2 + s2) for s1 in _SUITS for s2 in _SUITS if s1 != s2]


def reconstruct_range(node: str, action: str, dead: set[str]) -> list[tuple[tuple[int, int], float]]:
    """(ノード, アクション) を取った相手のレンジを (treysカードの組, 重み) のリストで返す.

    dead は既知のカード(自分のホール+ボード)で、それを含むコンボは除外(カードリムーバル)。
    重み = そのハンドが当該アクションを取る頻度。
    """
    table = _RANGES.get(node, {})
    out = []
    for key, freqs in table.items():
        w = freqs.get(action)
        if not w:
            continue
        for c1, c2 in combos_for_key(key):
            if c1 in dead or c2 in dead:
                continue
            out.append(((Card.new(c1), Card.new(c2)), w))
    return out


def equity_vs_range(
    hero: list[str],
    board: list[str],
    villain_range: list[tuple[tuple[int, int], float]],
    iters: int = 600,
) -> float:
    """自分の手(hero)が相手レンジに対して持つエクイティ(勝ち+引き分け/2)をモンテカルロで推定."""
    if not villain_range:
        return 0.5
    hero_c = [Card.new(c) for c in hero]
    board_c = [Card.new(c) for c in board]
    used = set(hero_c) | set(board_c)
    weights = [w for _, w in villain_range]
    deck_full = [Card.new(r + s) for r in _RANKS for s in _SUITS]
    need = 5 - len(board_c)

    won = 0.0
    total = 0.0
    for _ in range(iters):
        (v1, v2) = random.choices(villain_range, weights=weights, k=1)[0][0]
        if v1 in used or v2 in used:
            continue  # 相手の手が自分/ボードと衝突(カードリムーバルの取りこぼし)
        blocked = used | {v1, v2}
        deck = [c for c in deck_full if c not in blocked]
        runout = random.sample(deck, need) if need else []
        full_board = board_c + runout
        hs = _EVAL.evaluate(full_board, hero_c)
        vs = _EVAL.evaluate(full_board, [v1, v2])
        if hs < vs:
            won += 1.0
        elif hs == vs:
            won += 0.5
        total += 1.0
    return won / total if total else 0.5
