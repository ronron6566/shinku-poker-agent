"use client";

import { useState } from "react";
import type { Hand } from "@/lib/types";
import { buildFrames, parseCards, winColor, type Frame } from "@/lib/poker";
import { Card } from "./Card";
import { Board } from "./Board";

const OPP = "GTO Wizard";

export function HandReplay({ hand, bigBlind }: { hand: Hand; bigBlind: number }) {
  const startingStack = bigBlind * 200;
  const frames = buildFrames(hand, bigBlind, startingStack);
  const [step, setStep] = useState(0); // 0 = blinds posted, before any action

  const cur: Frame | null = step > 0 ? frames[step - 1] : null;
  const heroIsSB = (hand.hero_position ?? "SB") === "SB";

  const bb = (chips: number | null | undefined) =>
    chips === null || chips === undefined ? "—" : (chips / bigBlind).toFixed(1);

  // State at the current step (pre-action state uses the posted blinds).
  const boardReveal = cur ? cur.boardCount : 0;
  const pot = cur ? cur.pot : bigBlind * 1.5;
  const committed = cur
    ? cur.committed
    : { hero: heroIsSB ? bigBlind / 2 : bigBlind, villain: heroIsSB ? bigBlind : bigBlind / 2 };
  const stack = cur
    ? cur.stack
    : { hero: startingStack - (heroIsSB ? bigBlind / 2 : bigBlind), villain: startingStack - (heroIsSB ? bigBlind : bigBlind / 2) };

  const hero = hand.players.find((p) => p.name !== OPP);
  const villain = hand.players.find((p) => p.name === OPP);

  const actionLabel = (f: Frame) =>
    f.type === "bet"
      ? `B ${bb(f.amount)}`
      : f.type === "call"
        ? "Call"
        : f.type === "check"
          ? "Check"
          : f.type === "runout"
            ? f.street
            : "Fold";

  const isAction = (f: Frame | null): f is Frame => !!f && f.type !== "runout";

  const Bubble = ({ f }: { f: Frame }) => (
    <span
      className={`rounded-md px-2 py-0.5 text-xs font-semibold ${
        f.type === "fold"
          ? "bg-rose-500/20 text-rose-300"
          : f.type === "bet"
            ? "bg-amber-400 text-slate-900"
            : "bg-slate-200 text-slate-900"
      }`}
    >
      {actionLabel(f)}
    </span>
  );

  const Seat = ({
    name,
    you,
    position,
    cards,
    stackChips,
    committedChips,
    button,
    active,
    bubble,
  }: {
    name: string;
    you?: boolean;
    position: string | null;
    cards: string | null;
    stackChips: number;
    committedChips: number;
    button: boolean;
    active: boolean;
    bubble: Frame | null;
  }) => (
    <div className="flex flex-col items-center gap-1.5">
      <div className="flex gap-1.5">
        {parseCards(cards).length ? (
          parseCards(cards).map((c, i) => <Card key={i} card={c} size="md" />)
        ) : (
          <>
            <Card hidden size="md" />
            <Card hidden size="md" />
          </>
        )}
      </div>
      <div
        className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-center transition ${
          active ? "border-amber-400 bg-amber-400/10" : "border-slate-600 bg-slate-800"
        }`}
      >
        {button && (
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-slate-200 text-[10px] font-bold text-slate-900">
            D
          </span>
        )}
        <div className="leading-tight">
          <div className="text-xs font-semibold text-slate-100">
            {name} {you && <span className="text-amber-300">(you)</span>}
          </div>
          <div className="text-[11px] text-slate-400">
            {position} · {bb(stackChips)} BB
          </div>
        </div>
      </div>
      <div className="flex h-6 items-center gap-2">
        {committedChips > 0 && (
          <span className="rounded-full bg-slate-900/80 px-2 py-0.5 text-[11px] text-amber-200 ring-1 ring-amber-500/40">
            {bb(committedChips)} BB
          </span>
        )}
        {bubble && <Bubble f={bubble} />}
      </div>
    </div>
  );

  return (
    <div className="space-y-5">
      {/* Action history ribbon */}
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {frames.map((f, i) => (
          <button
            key={i}
            onClick={() => setStep(i + 1)}
            className={`shrink-0 rounded px-2 py-1 text-xs ${
              step === i + 1
                ? "bg-amber-400 text-slate-900"
                : f.type === "runout"
                  ? "bg-slate-700 text-slate-300"
                  : f.actorSide === "hero"
                    ? "bg-amber-400/15 text-amber-200"
                    : "bg-sky-400/15 text-sky-200"
            }`}
          >
            {f.type === "runout" ? `↳ ${actionLabel(f)}` : `${f.actorPosition} ${actionLabel(f)}`}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="rounded-[40%/22%] border-2 border-emerald-800 bg-gradient-to-b from-emerald-900/70 to-slate-950 px-4 py-8">
        <Seat
          name={villain?.name ?? OPP}
          position={villain?.position ?? null}
          cards={hand.villain_hole_cards}
          stackChips={stack.villain}
          committedChips={committed.villain}
          button={!heroIsSB}
          active={isAction(cur) && cur.actorSide === "villain"}
          bubble={isAction(cur) && cur.actorSide === "villain" ? cur : null}
        />

        <div className="my-5 flex flex-col items-center gap-2">
          <Board board={hand.board_cards} reveal={boardReveal} size="lg" />
          <div className="rounded-full bg-slate-900/70 px-4 py-1 text-sm font-bold text-slate-100">
            {bb(pot)} BB
          </div>
          <div className="text-[11px] uppercase tracking-widest text-slate-500">{cur ? cur.street : "preflop"}</div>
        </div>

        <Seat
          name={hero?.name ?? "Hero"}
          you
          position={hero?.position ?? null}
          cards={hand.hero_hole_cards}
          stackChips={stack.hero}
          committedChips={committed.hero}
          button={heroIsSB}
          active={isAction(cur) && cur.actorSide === "hero"}
          bubble={isAction(cur) && cur.actorSide === "hero" ? cur : null}
        />
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => setStep(0)}
          className="rounded-md bg-slate-700 px-3 py-1.5 text-sm font-medium text-slate-100"
        >
          ↺ Replay
        </button>
        <button
          onClick={() => setStep((s) => Math.max(0, s - 1))}
          disabled={step === 0}
          className="rounded-md bg-slate-700 px-3 py-1.5 text-sm font-medium text-slate-100 disabled:opacity-40"
        >
          ‹ Prev
        </button>
        <input
          type="range"
          min={0}
          max={frames.length}
          value={step}
          onChange={(e) => setStep(Number(e.target.value))}
          className="flex-1 accent-amber-400"
        />
        <button
          onClick={() => setStep((s) => Math.min(frames.length, s + 1))}
          disabled={step === frames.length}
          className="rounded-md bg-slate-700 px-3 py-1.5 text-sm font-medium text-slate-100 disabled:opacity-40"
        >
          Next ›
        </button>
      </div>
      <div className="text-center text-xs text-slate-500">
        step {step} / {frames.length}
      </div>

      {/* Result */}
      <div className="flex justify-center gap-10 border-t border-slate-800 pt-4 text-sm">
        <div className="text-center">
          <div className="text-slate-400">Result</div>
          <div className={`text-lg font-bold ${winColor(hand.winnings)}`}>
            {hand.winnings != null ? `${hand.winnings >= 0 ? "+" : ""}${bb(hand.winnings)} BB` : "—"}
          </div>
        </div>
        <div className="text-center">
          <div className="text-slate-400">AIVAT (luck-adjusted)</div>
          <div className={`text-lg font-bold ${winColor(hand.aivat_score)}`}>
            {hand.aivat_score != null ? `${hand.aivat_score >= 0 ? "+" : ""}${bb(hand.aivat_score)} BB` : "—"}
          </div>
        </div>
      </div>
    </div>
  );
}
