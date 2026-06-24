import Link from "next/link";
import { getRuns } from "@/lib/db";
import { fmtBB, fmtPct, fmtDate, winColor } from "@/lib/poker";

export const dynamic = "force-dynamic";

export default async function Home() {
  const runs = await getRuns();

  return (
    <main className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Shinku Poker — Benchmark Runs</h1>
        <p className="text-sm text-slate-400">Results vs GTO Wizard AI, scored with AIVAT (luck-adjusted).</p>
      </header>

      {runs.length === 0 ? (
        <p className="text-slate-400">No runs yet. Run a benchmark with a DATABASE_URL set.</p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-900 text-slate-400">
              <tr>
                <th className="px-3 py-2 text-left">Date</th>
                <th className="px-3 py-2 text-left">Agent</th>
                <th className="px-3 py-2 text-right">Hands</th>
                <th className="px-3 py-2 text-right">Winrate</th>
                <th className="px-3 py-2 text-right">AIVAT</th>
                <th className="px-3 py-2 text-right">GTO fold</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className="border-t border-slate-800 hover:bg-slate-900/50">
                  <td className="px-3 py-2">
                    <Link href={`/runs/${r.id}`} className="text-sky-400 hover:underline">
                      {fmtDate(r.created_at)}
                    </Link>
                  </td>
                  <td className="px-3 py-2 font-medium">{r.agent_type}</td>
                  <td className="px-3 py-2 text-right">{r.successful_hands}</td>
                  <td className={`px-3 py-2 text-right ${winColor(r.winrate_bb100)}`}>{fmtBB(r.winrate_bb100)}</td>
                  <td className={`px-3 py-2 text-right ${winColor(r.aivat_bb100)}`}>{fmtBB(r.aivat_bb100)}</td>
                  <td className="px-3 py-2 text-right text-slate-300">{fmtPct(r.opponent_fold_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
