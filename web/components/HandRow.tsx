"use client";

import { useRouter } from "next/navigation";
import type { Hand } from "@/lib/types";
import { fmtChips, winColor } from "@/lib/poker";
import { Board } from "./Board";

export function HandRow({ hand, index }: { hand: Hand; index: number }) {
  const router = useRouter();
  return (
    <tr
      onClick={() => router.push(`/hands/${hand.id}`)}
      className="cursor-pointer border-t border-slate-800 hover:bg-slate-900/50"
    >
      <td className="px-3 py-2 text-sky-400">{index + 1}</td>
      <td className="px-3 py-2">{hand.hero_position ?? "—"}</td>
      <td className="px-3 py-2 font-mono">{hand.hero_hole_cards ?? "—"}</td>
      <td className="px-3 py-2">
        <Board board={hand.board_cards} size="sm" />
      </td>
      <td className={`px-3 py-2 text-right ${winColor(hand.winnings)}`}>{fmtChips(hand.winnings)}</td>
      <td className={`px-3 py-2 text-right ${winColor(hand.aivat_score)}`}>{fmtChips(hand.aivat_score)}</td>
    </tr>
  );
}
