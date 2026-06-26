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


def _strength(board_ints: list[int], hole_ints: list[int]) -> float:
    """現時点の役の強さ(0..1, 高いほど強い). 相手モデルの高速な強さ指標に使う(将来カードは見ない)."""
    rank = _EVAL.evaluate(board_ints, hole_ints)  # 1=最強, 7462=最弱
    return (7462 - rank) / 7461


# 相手モデル(対称戦略の仮定): 現時点の役の強さ s から各アクションの確率。
# ベットはポラライズ(強い手+一部ブラフ)、チェックは中間中心、コール/レイズは強さで継続。
def _p_bet(s: float) -> float:
    return 0.85 if s > 0.66 else (0.30 if s < 0.33 else 0.20)


def _p_raise(s: float) -> float:
    return 0.85 if s > 0.85 else (0.25 if s > 0.6 else 0.03)


def _p_call(s: float) -> float:
    return 0.9 if s > 0.45 else (0.3 if s > 0.3 else 0.05)


_P_ACTION = {
    "bet": _p_bet,
    "raise": _p_raise,
    "call": _p_call,
    "check": lambda s: 1.0 - _p_bet(s),
}


def _split_streets(action_history: list[str]) -> list[list[str]]:
    streets: list[list[str]] = [[]]
    for a in action_history:
        if a == "_":
            streets.append([])
        else:
            streets[-1].append(a)
    return streets


def narrow_villain_range(
    villain_range: list[tuple[tuple[int, int], float]],
    action_history: list[str],
    hero_position: str,
    full_board: list[str],
) -> list[tuple[tuple[int, int], float]]:
    """ポストフロップの相手アクションごとに、相手モデルでレンジの重みを更新(ベイズ狭め込み)."""
    other = {"SB": "BB", "BB": "SB"}
    villain = other[hero_position]
    streets = _split_streets(action_history)
    board_count = {1: 3, 2: 4, 3: 5}  # streets index -> 見えているボード枚数
    r = villain_range
    for si in range(1, len(streets)):  # 1=flop, 2=turn, 3=river
        bc = board_count.get(si, 5)
        if len(full_board) < bc:
            break
        board_ints = [Card.new(c) for c in full_board[:bc]]
        actor = "BB"  # ポストフロップは BB(アウトオブポジション)が先
        bet_seen = False
        for a in streets[si]:
            if actor == villain and a != "f":
                if a == "k":
                    ctx = "check"
                elif a == "c":
                    ctx = "call"
                elif a.startswith("b"):
                    ctx = "raise" if bet_seen else "bet"
                else:
                    ctx = None
                if ctx:
                    fn = _P_ACTION[ctx]
                    r = [(cc, w * fn(_strength(board_ints, list(cc)))) for cc, w in r]
                    r = [(cc, w) for cc, w in r if w > 1e-6]
            if a.startswith("b"):
                bet_seen = True
            if a != "f":
                actor = other[actor]
    return r


# プリフロップのラインから相手の(ノード, アクション)を求めるためのマップ。
# キー = (preflopアクションのタプル), 値 = {"SB": (node, action), "BB": (node, action)}
def villain_preflop_node(hero_position: str, preflop: list[str]) -> tuple[str, str] | None:
    pf = [a for a in preflop if a]
    is_bet = lambda a: a.startswith("b")  # noqa: E731
    sb = bb = None
    if len(pf) == 2 and is_bet(pf[0]) and pf[1] == "c":
        sb, bb = ("sb_open", "raise"), ("bb_vs_raise", "call")
    elif len(pf) == 2 and pf[0] == "c" and pf[1] == "k":
        sb, bb = ("sb_open", "limp"), ("bb_vs_limp", "check")
    elif len(pf) == 3 and pf[0] == "c" and is_bet(pf[1]) and pf[2] == "c":
        sb, bb = ("sb_vs_raise", "call"), ("bb_vs_limp", "raise")
    elif len(pf) == 3 and is_bet(pf[0]) and is_bet(pf[1]) and pf[2] == "c":
        sb, bb = ("sb_vs_3bet", "call"), ("bb_vs_raise", "3bet")
    else:
        return None
    return bb if hero_position == "SB" else sb


def to_call_postflop(action_history: list[str], hero_position: str) -> int:
    """ポストフロップの現ストリートで、自分が続けるために必要なコール額(チップ)."""
    other = {"SB": "BB", "BB": "SB"}
    street = _split_streets(action_history)[-1]
    committed = {"SB": 0, "BB": 0}
    actor = "BB"
    for a in street:
        if a == "c":
            committed[actor] = committed[other[actor]]
        elif a.startswith("b"):
            committed[actor] = int(a[1:])
        if a != "f":
            actor = other[actor]
    return committed[other[hero_position]] - committed[hero_position]


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
