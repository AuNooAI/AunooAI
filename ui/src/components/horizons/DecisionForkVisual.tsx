/**
 * DecisionForkVisual Component
 * CSS-based visualization of conditional decision forks
 * Displays "If X → Y" format for decision outcomes
 */

import React from 'react';

interface DecisionCondition {
  condition: string;  // e.g., "If incumbents execute well"
  outcome: string;    // e.g., "Novo Nordisk/Lilly retain dominance through oral formulations"
}

interface DecisionForkVisualProps {
  conditionA: DecisionCondition;
  conditionB: DecisionCondition;
}

const DecisionForkVisual: React.FC<DecisionForkVisualProps> = ({ conditionA, conditionB }) => {
  return (
    <div className="decision-fork-visual space-y-3">
      {/* Condition A */}
      <div className="flex items-start gap-2">
        <span className="text-muted-foreground mt-0.5">-</span>
        <div className="flex-1">
          <span className="text-sm font-medium text-foreground">
            {conditionA.condition}
          </span>
          <span className="text-muted-foreground mx-1.5">&rarr;</span>
          <span className="text-sm text-foreground">
            {conditionA.outcome}
          </span>
        </div>
      </div>

      {/* Condition B */}
      <div className="flex items-start gap-2">
        <span className="text-muted-foreground mt-0.5">-</span>
        <div className="flex-1">
          <span className="text-sm font-medium text-foreground">
            {conditionB.condition}
          </span>
          <span className="text-muted-foreground mx-1.5">&rarr;</span>
          <span className="text-sm text-foreground">
            {conditionB.outcome}
          </span>
        </div>
      </div>
    </div>
  );
};

export default DecisionForkVisual;
