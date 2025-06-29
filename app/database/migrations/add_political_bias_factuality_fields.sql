-- Add political bias and factuality analysis fields to model bias arena results
ALTER TABLE model_bias_arena_results ADD COLUMN political_bias TEXT;
ALTER TABLE model_bias_arena_results ADD COLUMN political_bias_explanation TEXT;
ALTER TABLE model_bias_arena_results ADD COLUMN factuality TEXT;
ALTER TABLE model_bias_arena_results ADD COLUMN factuality_explanation TEXT;

-- Create indexes for the new fields for better performance
CREATE INDEX IF NOT EXISTS idx_bias_arena_results_political_bias ON model_bias_arena_results(political_bias);
CREATE INDEX IF NOT EXISTS idx_bias_arena_results_factuality ON model_bias_arena_results(factuality); 