-- Schema for storing benchmark runs and per-hand history.
-- Apply with: psql "$DATABASE_URL" -f db/schema.sql

create table if not exists runs (
    id                    bigserial primary key,
    agent_type            text not null,
    game_name             text,
    num_hands             int not null,
    successful_hands      int not null,
    failed_hands          int not null,
    duration_seconds      double precision,
    big_blind             double precision,
    total_winnings        double precision,
    winrate_bb100         double precision,
    aivat_bb100           double precision,
    hands_won             int,
    opponent_fold_rate    double precision,
    created_at            timestamptz not null default now()
);

create table if not exists hands (
    id                    bigserial primary key,
    run_id                bigint not null references runs(id) on delete cascade,
    hand_id               bigint,
    street                text,
    board_cards           text,
    action_history        jsonb,
    total_pot             double precision,
    winnings              double precision,
    aivat_score           double precision,
    has_gto_wizard_folded boolean,
    hero_position         text,
    hero_hole_cards       text,
    villain_hole_cards    text,
    players               jsonb,
    created_at            timestamptz not null default now()
);

create index if not exists hands_run_id_idx on hands (run_id);
create index if not exists runs_created_at_idx on runs (created_at desc);
