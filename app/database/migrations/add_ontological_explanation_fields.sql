-- Add explanation fields to model_bias_arena_results table
ALTER TABLE model_bias_arena_results ADD COLUMN sentiment_explanation TEXT;
ALTER TABLE model_bias_arena_results ADD COLUMN future_signal_explanation TEXT;
ALTER TABLE model_bias_arena_results ADD COLUMN time_to_impact_explanation TEXT;  
ALTER TABLE model_bias_arena_results ADD COLUMN driver_type_explanation TEXT;
ALTER TABLE model_bias_arena_results ADD COLUMN category_explanation TEXT; 