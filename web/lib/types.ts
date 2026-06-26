export type Player = {
  name: string;
  position: string;
  hole_cards: string | null;
  stack: number;
};

export type Run = {
  id: number;
  agent_type: string;
  game_name: string | null;
  num_hands: number;
  successful_hands: number;
  failed_hands: number;
  duration_seconds: number | null;
  big_blind: number | null;
  total_winnings: number | null;
  winrate_bb100: number | null;
  aivat_bb100: number | null;
  hands_won: number | null;
  opponent_fold_rate: number | null;
  created_at: string;
};

export type Decision = {
  street: string;
  board_cards: string;
  action: string;
  amount: number | null;
  reason: string | null;
};

export type Hand = {
  id: number;
  run_id: number;
  hand_id: number | null;
  street: string | null;
  board_cards: string | null;
  action_history: string[];
  total_pot: number | null;
  winnings: number | null;
  aivat_score: number | null;
  has_gto_wizard_folded: boolean | null;
  hero_position: string | null;
  hero_hole_cards: string | null;
  villain_hole_cards: string | null;
  players: Player[];
  decisions: Decision[];
  created_at: string;
};
