"use client";

import { useState } from "react";
import type { Hand } from "@/lib/types";
import { buildFrames, parseCards, winColor, fmtChips } from "@/lib/poker";
import { Card } from "./Card";
import { Board } from "./Board";

const OPPONENT = "GTO Wizard";

export function HandReplay({ hand, bigBlind }: { hand: Hand; bigBlind: number }) {
  const frames = buildFrames(hand, bigBlind);
  const [step, setStep] = useState(frames.length); // start at the end (full hand shown)

  const current = step > 0 ? frames[step - 1] : null;
  const boardReveal = current ? current.boardCount : parseCards(hand.board_cards).length;
  const pot = current ? current.pot : (hand.total_pot ?? 0);

  const hero = hand.players.find((p) => p.name !== OPPONENT);
  const villain = hand.players.find((p) => p.name === OPPONENT);

  const Seat = ({
    label,
    cards,
    position,
    active,
    you,
  }: {
    label: string;
    cards: string | null;
    position: string | null;
    active: boolean;
    you?: boolean;
  }) => (
    <div
      className={`flex items-center gap-3 rounded-lg border px-4 py-3 transition ${
        active ? "border-amber-400 bg-amber-400/10" : "border-slate-700 bg-slate-800/50"
      }`}
    >
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
      <div>
        <div className="font-semibold text-slate-100">
          {label} {you && <span className="text-xs text-amber-300">(you)</span>}
        </div>
        <div className="text-xs text-slate-400">{position ?? "—"}</div>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      {/* Table */}
      <div className="rounded-2xl border border-emerald-900 bg-gradient-to-b from-emerald-950 to-slate-950 p-6">
        <div className="flex items-center justify-between gap-4">
          <Seat
            label={villain?.name ?? OPPONENT}
            cards={hand.villain_hole_cards}
            position={villain?.position ?? null}
            active={current?.actorSide === "villain"}
          />
          <div className="text-right text-sm text-slate-400">
            <div>Pot</div>
            <div className="text-xl font-bold text-slate-100">{Math.round(pot).toLocaleString()}</div>
          </div>
        </div>

        <div className="my-6 flex flex-col items-center gap-2">
          <Board board={hand.board_cards} reveal={boardReveal} size="lg" />
          <div className="text-xs uppercase tracking-wide text-slate-500">
            {current ? current.street : hand.street}
          </div>
        </div>

        <Seat
          label={hero?.name ?? "Hero"}
          cards={hand.hero_hole_cards}
          position={hero?.position ?? null}
          active={current?.actorSide === "hero"}
          you
        />
      </div>

      {/* Current action */}
      <div className="flex items-center justify-center gap-2 text-sm">
        {current ? (
          <span className="text-slate-200">
            <span className={current.actorSide === "hero" ? "text-amber-300" : "text-sky-300"}>
              {current.actorPosition}
            </span>{" "}
            ({current.actorSide === "hero" ? "you" : OPPONENT}): <b>{current.label}</b>
          </span>
        ) : (
          <span className="text-slate-500">Start — blinds posted</span>
        )}
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3">
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

      {/* Action timeline */}
      <div className="flex flex-wrap gap-1.5">
        {frames.map((f, i) => (
          <button
            key={i}
            onClick={() => setStep(i + 1)}
            className={`rounded px-2 py-1 text-xs ${
              step === i + 1
                ? "bg-amber-400 text-slate-900"
                : f.actorSide === "hero"
                  ? "bg-amber-400/15 text-amber-200"
                  : "bg-sky-400/15 text-sky-200"
            }`}
          >
            {f.actorPosition} {f.label}
          </button>
        ))}
      </div>

      {/* Result */}
      <div className="flex justify-center gap-8 border-t border-slate-800 pt-4 text-sm">
        <div className="text-center">
          <div className="text-slate-400">Result (chips)</div>
          <div className={`text-lg font-bold ${winColor(hand.winnings)}`}>{fmtChips(hand.winnings)}</div>
        </div>
        <div className="text-center">
          <div className="text-slate-400">AIVAT (luck-adjusted)</div>
          <div className={`text-lg font-bold ${winColor(hand.aivat_score)}`}>{fmtChips(hand.aivat_score)}</div>
        </div>
      </div>
    </div>
  );
}
