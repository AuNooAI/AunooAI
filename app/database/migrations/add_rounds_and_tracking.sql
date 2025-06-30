-- Add rounds support and model tracking
ALTER TABLE model_bias_arena_runs ADD COLUMN rounds INTEGER DEFAULT 1;
ALTER TABLE model_bias_arena_runs ADD COLUMN current_round INTEGER DEFAULT 1;

-- Add round tracking to results
ALTER TABLE model_bias_arena_results ADD COLUMN round_number INTEGER DEFAULT 1;

-- Create index for round-based queries
CREATE INDEX IF NOT EXISTS idx_bias_arena_results_round ON model_bias_arena_results(run_id, round_number);
CREATE INDEX IF NOT EXISTS idx_bias_arena_runs_rounds ON model_bias_arena_runs(rounds, current_round); 