import { neon } from "@neondatabase/serverless";
import type { Run, Hand } from "./types";

const sql = neon(process.env.DATABASE_URL!);

export async function getRuns(): Promise<Run[]> {
  return (await sql`
    select id::int, agent_type, game_name, num_hands, successful_hands, failed_hands,
           duration_seconds, big_blind, total_winnings, winrate_bb100, aivat_bb100,
           hands_won, opponent_fold_rate, created_at
    from runs order by created_at desc
  `) as Run[];
}

export async function getRun(id: number): Promise<Run | null> {
  const rows = (await sql`
    select id::int, agent_type, game_name, num_hands, successful_hands, failed_hands,
           duration_seconds, big_blind, total_winnings, winrate_bb100, aivat_bb100,
           hands_won, opponent_fold_rate, created_at
    from runs where id = ${id}
  `) as Run[];
  return rows[0] ?? null;
}

export async function getHands(runId: number): Promise<Hand[]> {
  return (await sql`
    select id::int, run_id::int, hand_id::int, street, board_cards, action_history, total_pot,
           winnings, aivat_score, has_gto_wizard_folded, hero_position, hero_hole_cards,
           villain_hole_cards, players, created_at
    from hands where run_id = ${runId} order by id
  `) as Hand[];
}

export async function getHand(id: number): Promise<Hand | null> {
  const rows = (await sql`
    select id::int, run_id::int, hand_id::int, street, board_cards, action_history, total_pot,
           winnings, aivat_score, has_gto_wizard_folded, hero_position, hero_hole_cards,
           villain_hole_cards, players, created_at
    from hands where id = ${id}
  `) as Hand[];
  return rows[0] ?? null;
}
