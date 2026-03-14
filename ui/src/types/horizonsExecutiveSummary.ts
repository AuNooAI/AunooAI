/**
 * TypeScript interfaces for Future Horizons Executive Summary
 * Horizon-anchored executive summaries with counter-signals and decision forks
 */

export type HorizonType = 'h1' | 'h2' | 'h3';

export interface HorizonCounterSignal {
  horizon: HorizonType;
  horizon_label: string;                  // "H2 Counter-signal" or "H3 Counter-signal"
  signal: string;                         // What this horizon suggests could happen
}

export interface HorizonTransitionOutcome {
  horizon_persists: HorizonType;          // Which horizon state persists
  label: string;                          // "H1 persists" or "H2 executes"
  outcome: string;                        // Consequences
  affected_parties: string[];             // Named companies, sectors, geographies
}

export interface TopicExecutiveSummary {
  topic_title: string;                    // CAPS title (e.g., "PATENT CLIFFS & BRANDED MARGIN PRESSURE")
  primary_horizon: HorizonType;           // Which horizon this topic anchors to
  horizon_label: string;                  // "Declining System" | "Transition/Innovation" | "Future Vision"
  opening_statement: string;              // Opening context with consensus % embedded (e.g., "Patent cliffs will reshape pharma competitive dynamics 2026-2030, with 85% of sources expecting...")
  consensus_percentage: number;           // e.g., 85
  minority_view: {
    percentage_range: string;             // e.g., "7-12%"
    statement: string;                    // e.g., "Incumbent innovation or regulatory shifts could preserve branded margins"
  };
  primary_signal: string;                 // "Primary Signal (X% consensus): ..." - the main takeaway
  counter_signals?: HorizonCounterSignal[]; // Optional counter-signals from other horizons
  decision_fork: {
    condition_a: {
      condition: string;                  // e.g., "If incumbents execute well"
      outcome: string;                    // e.g., "Novo Nordisk/Lilly retain dominance through oral formulations and pipeline depth"
    };
    condition_b: {
      condition: string;                  // e.g., "If disruption accelerates"
      outcome: string;                    // e.g., "Branded revenue erosion outpaces mitigation; biosimilar players gain structural advantage"
    };
  };
  action_window: {
    assessment: { timeframe: string; action: string };   // e.g., "0-6 months to assess exposure"
    positioning: { timeframe: string; action: string };  // e.g., "6-18 months to position"
  };
  source_scenarios: (string | SourceScenario)[];  // Underlying scenarios - supports both old string[] and new object format
}

export interface SourceScenario {
  title: string;
  horizon: HorizonType;
}

export interface FutureHorizonsExecutiveSummary {
  generated_at: string;
  topic: string;
  summaries: TopicExecutiveSummary[];     // One per major thematic grouping
}

export interface FutureHorizonsExportOptions {
  includeChart: boolean;
  includeExecutiveSummary: boolean;
  includeDetailedCards: boolean;
  format: 'pdf' | 'image';
}

// Horizon metadata for display
export const HORIZON_CONFIG: Record<HorizonType, {
  label: string;
  subtitle: string;
  color: string;
  bgClass: string;
  textClass: string;
  borderClass: string;
}> = {
  h1: {
    label: 'H1',
    subtitle: 'Declining System',
    color: 'blue',
    bgClass: 'bg-blue-600',
    textClass: 'text-blue-600',
    borderClass: 'border-blue-600'
  },
  h2: {
    label: 'H2',
    subtitle: 'Transition/Innovation',
    color: 'purple',
    bgClass: 'bg-purple-600',
    textClass: 'text-purple-600',
    borderClass: 'border-purple-600'
  },
  h3: {
    label: 'H3',
    subtitle: 'Future Vision',
    color: 'green',
    bgClass: 'bg-green-600',
    textClass: 'text-green-600',
    borderClass: 'border-green-600'
  }
};
