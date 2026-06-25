import type { Hand } from "./types";

export const SUITS: Record<string, { symbol: string; color: string }> = {
  s: { symbol: "♠", color: "text-slate-200" },
  h: { symbol: "♥", color: "text-rose-400" },
  d: { symbol: "♦", color: "text-sky-400" },
  c: { symbol: "♣", color: "text-emerald-400" },
};

export type ParsedCard = { rank: string; suit: string };

export function parseCards(cards: string | null | undefined): ParsedCard[] {
  if (!cards) return [];
  const out: ParsedCard[] = [];
  for (let i = 0; i + 1 < cards.length; i += 2) {
    out.push({ rank: cards[i], suit: cards[i + 1] });
  }
  return out;
}

export function fmtBB(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)} bb/100`;
}

export function fmtChips(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `${n >= 0 ? "+" : ""}${Math.round(n).toLocaleString()}`;
}

export function fmtPct(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

export function fmtDate(s: string): string {
  return new Date(s).toLocaleString();
}

export function winColor(n: number | null | undefined): string {
  if (n === null || n === undefined) return "text-slate-400";
  return n > 0 ? "text-emerald-400" : n < 0 ? "text-rose-400" : "text-slate-400";
}

const STREETS = ["preflop", "flop", "turn", "river"];
const BOARD_BY_STREET: Record<string, number> = { preflop: 0, flop: 3, turn: 4, river: 5 };

export type ActionType = "fold" | "check" | "call" | "bet";

export type Frame = {
  street: string;
  boardCount: number;
  pot: number; // raw chips
  actorPosition: string;
  actorSide: "hero" | "villain";
  type: ActionType;
  amount: number | null; // bet-to / call-to amount, raw chips
  committed: { hero: number; villain: number }; // chips in front this street
  stack: { hero: number; villain: number }; // remaining stack, raw chips
};

/**
 * Reconstruct a step-by-step replay from the flat action history. In heads-up the two players
 * alternate within a street (SB acts first preflop, BB first postflop), so we can derive who acted,
 * a running pot, each player's committed chips and stack, and how much of the board is revealed.
 */
export function buildFrames(hand: Hand, bigBlind: number, startingStack = bigBlind * 200): Frame[] {
  const sb = bigBlind / 2;
  const heroPos = hand.hero_position ?? "SB";
  const villPos = heroPos === "SB" ? "BB" : "SB";
  const other = (pos: string) => (pos === "SB" ? "BB" : "SB");

  const frames: Frame[] = [];
  const prev: Record<string, number> = { SB: 0, BB: 0 }; // contributed in finished streets
  let committed: Record<string, number> = { SB: sb, BB: bigBlind };
  let streetIdx = 0;
  let actor = "SB";

  const push = (type: ActionType, amount: number | null) => {
    const street = STREETS[streetIdx];
    frames.push({
      street,
      boardCount: BOARD_BY_STREET[street],
      pot: prev.SB + prev.BB + committed.SB + committed.BB,
      actorPosition: actor,
      actorSide: actor === heroPos ? "hero" : "villain",
      type,
      amount,
      committed: { hero: committed[heroPos], villain: committed[villPos] },
      stack: {
        hero: startingStack - prev[heroPos] - committed[heroPos],
        villain: startingStack - prev[villPos] - committed[villPos],
      },
    });
  };

  for (const tok of hand.action_history) {
    if (tok === "_") {
      prev.SB += committed.SB;
      prev.BB += committed.BB;
      committed = { SB: 0, BB: 0 };
      streetIdx = Math.min(streetIdx + 1, STREETS.length - 1);
      actor = "BB";
      continue;
    }

    if (tok === "f") push("fold", null);
    else if (tok === "k") push("check", null);
    else if (tok === "c") {
      committed[actor] = committed[other(actor)];
      push("call", committed[actor]);
    } else if (tok[0] === "b") {
      committed[actor] = parseInt(tok.slice(1), 10) || 0;
      push("bet", committed[actor]);
    }

    if (tok !== "f") actor = other(actor);
  }

  return frames;
}
