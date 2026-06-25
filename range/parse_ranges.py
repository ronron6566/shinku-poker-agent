"""GTO Wizard のレンジ画像(13x13グリッド)を JSON のレンジ表に変換するスクリプト.

各画像のグリッド枠を自動検出し、169マスそれぞれについて色(赤/緑/青)の面積比から
アクション頻度を読み取る。色とアクションの対応はノードごとに異なるため NODES で指定する。

使い方:
    uv run --with pillow --with numpy python range/parse_ranges.py
出力:
    range/preflop/<node>.json  (例: {"AA": {"raise": 1.0}, "AKs": {"raise": 0.96, "call": 0.04}, ...})
"""

import json
from pathlib import Path

import numpy as np
from PIL import Image

RANKS = "AKQJT98765432"
HERE = Path(__file__).parent

# ノードごとの: 入力画像, 色->アクション対応, 検証用の凡例頻度(任意).
NODES = {
    "sb_open": {
        "image": "preflop/sb_open.png",
        "colors": {"red": "raise", "green": "limp", "blue": "fold"},
        "legend": {"raise": 64.9, "limp": 28.7, "fold": 6.5},
    },
    "bb_vs_raise": {
        "image": "preflop/bb_vs_raise.png",
        "colors": {"red": "3bet", "green": "call", "blue": "fold"},
        "legend": {"3bet": 18.6, "call": 53.2, "fold": 28.2},
    },
    "bb_vs_limp": {
        "image": "preflop/bb_vs_limp.png",
        "colors": {"red": "raise", "green": "check", "blue": "fold"},
        "legend": {"raise": 31.7, "check": 68.3},
    },
    "sb_vs_3bet": {
        "image": "preflop/sb_vs_3bet.png",
        "colors": {"red": "4bet", "green": "call", "blue": "fold"},
        "legend": {"4bet": 8.7, "call": 42.2, "fold": 49.1},
    },
    "sb_vs_raise": {
        "image": "preflop/sb_vs_raise.png",
        "colors": {"red": "raise", "green": "call", "blue": "fold"},
        "legend": {"raise": 5.8, "call": 31.0, "fold": 63.2},
    },
}


def detect_bbox(vivid: np.ndarray) -> tuple[int, int, int, int]:
    """13x13グリッドの外枠を検出する(罫線の細い隙間は無視し、右パネルとの広い隙間で切る)."""
    colden = vivid.sum(0)
    width = len(colden)
    left = next(x for x in range(width) if colden[x] > 300)
    x = left
    right = left
    gap = 0
    while x < width:
        if colden[x] < 100:
            gap += 1
            if gap >= 8:  # 行列と右パネルの間の広い隙間
                break
        else:
            gap = 0
            right = x
        x += 1
    band = vivid[:, left : right + 1]
    rowden = band.sum(1)
    bw = band.shape[1]
    top = next(y for y in range(len(rowden)) if rowden[y] > bw * 0.3)
    bottom = max(y for y in range(len(rowden)) if rowden[y] > bw * 0.3)
    return left, right, top, bottom


def classify(sub: np.ndarray) -> np.ndarray:
    r, g, b = sub[..., 0], sub[..., 1], sub[..., 2]
    out = np.zeros(r.shape, dtype="U5")
    # 本物のアクション色は明るい(max>=180)。暗い画素(罫線/黒との境界のアンチエイリアス)は
    # 除外しないと、色付きが極端に細い低到達セルで偽の色が混じる。
    bright = np.maximum(np.maximum(r, g), b) > 120
    out[bright & ((r - np.maximum(g, b)) > 50)] = "red"
    out[bright & ((g - np.maximum(r, b)) > 25)] = "green"
    out[bright & ((b - np.maximum(r, g)) > 25)] = "blue"
    return out


def hand_name(r: int, c: int) -> str:
    if r == c:
        return RANKS[r] * 2
    if c > r:
        return RANKS[r] + RANKS[c] + "s"
    return RANKS[c] + RANKS[r] + "o"


def combos(name: str) -> int:
    return 6 if name[0] == name[1] else (4 if name.endswith("s") else 12)


def load_content(path: Path) -> np.ndarray:
    """画像と「内容マスク」を返す。内容 = 色付き or 白いラベル文字。

    黒セル(そのラインに到達しないコンボ)でもラベル文字はあるので、黒が多い画像でも
    グリッド枠を検出できるようにラベル文字を含める。
    """
    a = np.asarray(Image.open(path).convert("RGB")).astype(int)
    vivid = ((a.max(2) - a.min(2)) > 60) & (a.max(2) > 80)
    bright = a.min(2) > 170  # 白っぽいラベル文字
    return a, (vivid | bright)


def parse_image(
    path: Path, color_map: dict[str, str], bbox: tuple[int, int, int, int]
) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """各マスのアクション頻度(到達時の条件付き)と、到達率(色付き割合)を返す.

    黒 = そのラインに到達しないコンボを表すので、アクション頻度は色付き画素のみで正規化する
    (= この局面に来たとき、その手で各アクションを取る確率)。reach はそのマスのうち色が付い
    ている割合 = この局面に到達する割合で、検証(凡例との突き合わせ)の重み付けに使う。
    """
    a, _ = load_content(path)
    left, right, top, bottom = bbox
    cw = (right - left + 1) / 13
    ch = (bottom - top + 1) / 13

    ranges: dict[str, dict[str, float]] = {}
    reach: dict[str, float] = {}
    for r in range(13):
        for c in range(13):
            # 上のラベル文字だけ避け、セル下部まで含める。
            cx0 = int(left + c * cw) + 6
            cx1 = int(left + (c + 1) * cw) - 6
            cy0 = int(top + r * ch) + 24  # ラベル文字(上部)を完全に避ける
            cy1 = int(top + (r + 1) * ch) - 2
            block = a[cy0:cy1, cx0:cx1]
            cls = classify(block).ravel()
            colored = int((cls != "").sum())
            name = hand_name(r, c)
            # 到達率 = 色付き / (色付き + 黒). 白いラベル文字は分母から除く。
            R, G, B = block[..., 0].ravel(), block[..., 1].ravel(), block[..., 2].ravel()
            black = int(((R < 60) & (G < 60) & (B < 60)).sum())
            reach[name] = round(colored / (colored + black), 3) if (colored + black) else 0.0
            if colored == 0:
                continue
            fr = {}
            for color, action in color_map.items():
                cnt = int((cls == color).sum())
                if cnt:
                    fr[action] = round(cnt / colored, 3)
            ranges[name] = fr
    return ranges, reach


def _valid_bbox(bb: tuple[int, int, int, int]) -> bool:
    """セルサイズが想定(~84x53)に近いかで、検出成功/失敗を判定する。"""
    cw = (bb[1] - bb[0] + 1) / 13
    ch = (bb[3] - bb[2] + 1) / 13
    return 78 <= cw <= 92 and 48 <= ch <= 58


def main() -> None:
    # 全画像は同じウィンドウのスクショ。各画像で枠を検出し、妥当な検出値の中央値を合議枠とする。
    # 黒が多くて検出に失敗した画像(例: sb_vs_raise)には合議枠を流用する。
    detected = {}
    for node, cfg in NODES.items():
        _, content = load_content(HERE / cfg["image"])
        detected[node] = detect_bbox(content)
    valid = [bb for bb in detected.values() if _valid_bbox(bb)]
    consensus = tuple(int(np.median([bb[i] for bb in valid])) for i in range(4))
    print(f"合議枠: x{consensus[0]}-{consensus[1]} y{consensus[2]}-{consensus[3]}")

    for node, cfg in NODES.items():
        path = HERE / cfg["image"]
        ok_bbox = _valid_bbox(detected[node])
        bbox = detected[node] if ok_bbox else consensus
        if not ok_bbox:
            print(f"  [{node}] 枠検出失敗 → 合議枠を使用")
        ranges, reach = parse_image(path, cfg["colors"], bbox)
        out = HERE / "preflop" / f"{node}.json"
        out.write_text(json.dumps(ranges, indent=0, sort_keys=True))

        # 検証: 凡例は「到達したコンボの中での」アクション割合なので、各マスを
        # combos × 到達率(reach) で重み付けして突き合わせる。
        tot: dict[str, float] = {}
        weight = 0.0
        for name, fr in ranges.items():
            w = combos(name) * reach.get(name, 1.0)
            weight += w
            for action, freq in fr.items():
                tot[action] = tot.get(action, 0) + freq * w
        got = {a: round(v / weight * 100, 1) for a, v in tot.items()}
        legend = cfg.get("legend", {})
        ok = all(abs(got.get(a, 0) - p) <= 3 for a, p in legend.items())
        print(f"[{node}] 解析={got}  凡例={legend}  {'OK' if ok else '要確認'} -> {out.name}")


if __name__ == "__main__":
    main()
