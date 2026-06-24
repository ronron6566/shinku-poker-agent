import { SUITS } from "@/lib/poker";

const RANK_LABEL: Record<string, string> = { T: "10" };

export function Card({
  card,
  hidden = false,
  size = "md",
}: {
  card?: { rank: string; suit: string } | null;
  hidden?: boolean;
  size?: "sm" | "md" | "lg";
}) {
  const dims =
    size === "lg"
      ? "w-14 h-20 text-2xl"
      : size === "sm"
        ? "w-8 h-12 text-sm"
        : "w-11 h-16 text-lg";

  if (hidden || !card) {
    return (
      <div
        className={`${dims} rounded-md border border-slate-700 bg-gradient-to-br from-slate-700 to-slate-800 shadow-inner`}
      />
    );
  }

  const suit = SUITS[card.suit] ?? { symbol: card.suit, color: "text-slate-200" };
  const rank = RANK_LABEL[card.rank] ?? card.rank;

  return (
    <div
      className={`${dims} flex flex-col items-center justify-center rounded-md border border-slate-300 bg-slate-900 font-bold shadow ${suit.color}`}
    >
      <span className="leading-none">{rank}</span>
      <span className="leading-none">{suit.symbol}</span>
    </div>
  );
}
