import Link from "next/link";
import { notFound } from "next/navigation";
import { getRun, getHands } from "@/lib/db";
import { fmtBB, fmtChips, fmtPct, fmtDate, winColor } from "@/lib/poker";
import { Board } from "@/components/Board";

export const dynamic = "force-dynamic";

export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const runId = Number(id);
  const run = await getRun(runId);
  if (!run) notFound();
  const hands = await getHands(runId);

  const Stat = ({ label, value, cls }: { label: string; value: string; cls?: string }) => (
    <div className="rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-3">
      <div className="text-xs text-slate-400">{label}</div>
      <div className={`text-lg font-bold ${cls ?? ""}`}>{value}</div>
    </div>
  );

  return (
    <main className="space-y-6">
      <Link href="/" className="text-sm text-sky-400 hover:underline">
        ← All runs
      </Link>

      <header>
        <h1 className="text-2xl font-bold">
          {run.agent_type} <span className="text-slate-500">#{run.id}</span>
        </h1>
        <p className="text-sm text-slate-400">{fmtDate(run.created_at)}</p>
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Hands" value={`${run.successful_hands}`} />
        <Stat label="Winrate" value={fmtBB(run.winrate_bb100)} cls={winColor(run.winrate_bb100)} />
        <Stat label="AIVAT" value={fmtBB(run.aivat_bb100)} cls={winColor(run.aivat_bb100)} />
        <Stat label="GTO fold rate" value={fmtPct(run.opponent_fold_rate)} />
      </div>

      <h2 className="pt-2 text-lg font-semibold">Hands</h2>
      <div className="overflow-hidden rounded-xl border border-slate-800">
        <table className="w-full text-sm">
          <thead className="bg-slate-900 text-slate-400">
            <tr>
              <th className="px-3 py-2 text-left">#</th>
              <th className="px-3 py-2 text-left">Pos</th>
              <th className="px-3 py-2 text-left">Hole</th>
              <th className="px-3 py-2 text-left">Board</th>
              <th className="px-3 py-2 text-right">Chips</th>
              <th className="px-3 py-2 text-right">AIVAT</th>
            </tr>
          </thead>
          <tbody>
            {hands.map((h, i) => (
              <tr key={h.id} className="border-t border-slate-800 hover:bg-slate-900/50">
                <td className="px-3 py-2">
                  <Link href={`/hands/${h.id}`} className="text-sky-400 hover:underline">
                    {i + 1}
                  </Link>
                </td>
                <td className="px-3 py-2">{h.hero_position ?? "—"}</td>
                <td className="px-3 py-2 font-mono">{h.hero_hole_cards ?? "—"}</td>
                <td className="px-3 py-2">
                  <Board board={h.board_cards} size="sm" />
                </td>
                <td className={`px-3 py-2 text-right ${winColor(h.winnings)}`}>{fmtChips(h.winnings)}</td>
                <td className={`px-3 py-2 text-right ${winColor(h.aivat_score)}`}>{fmtChips(h.aivat_score)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
