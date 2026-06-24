import { Card } from "./Card";
import { parseCards } from "@/lib/poker";

export function Board({
  board,
  reveal,
  size = "md",
}: {
  board: string | null;
  reveal?: number;
  size?: "sm" | "md" | "lg";
}) {
  const cards = parseCards(board);
  const shown = reveal === undefined ? cards.length : reveal;
  const slots = Math.max(cards.length, shown, 0);

  if (slots === 0) {
    return <span className="text-sm text-slate-500">(preflop — no board)</span>;
  }

  return (
    <div className="flex gap-1.5">
      {Array.from({ length: slots }).map((_, i) =>
        i < shown && cards[i] ? (
          <Card key={i} card={cards[i]} size={size} />
        ) : (
          <Card key={i} hidden size={size} />
        ),
      )}
    </div>
  );
}
