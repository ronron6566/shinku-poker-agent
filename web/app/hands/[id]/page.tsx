import Link from "next/link";
import { notFound } from "next/navigation";
import { getHand, getRun } from "@/lib/db";
import { HandReplay } from "@/components/HandReplay";

export const dynamic = "force-dynamic";

export default async function HandPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const hand = await getHand(Number(id));
  if (!hand) notFound();
  const run = await getRun(hand.run_id);
  const bigBlind = run?.big_blind ?? 100;

  return (
    <main className="space-y-6">
      <Link href={`/runs/${hand.run_id}`} className="text-sm text-sky-400 hover:underline">
        ← Back to run #{hand.run_id}
      </Link>

      <header>
        <h1 className="text-2xl font-bold">Hand replay</h1>
        <p className="text-sm text-slate-400">
          API hand id {hand.hand_id ?? "—"} · {run?.agent_type ?? ""} vs GTO Wizard
        </p>
      </header>

      <HandReplay hand={hand} bigBlind={bigBlind} />
    </main>
  );
}
