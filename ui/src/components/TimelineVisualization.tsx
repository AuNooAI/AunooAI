import React, { useState } from 'react';
import './consensus.css';

interface TimelineConsensus {
  distribution: { [key: string]: number };
  consensus_window: {
    start_year: number;
    end_year: number;
    label: string;
  };
}

interface Outlier {
  scenario: string;
  details: string;
  year: number;
  source_percentage: number;
  reference: string;
}

interface TimelineVisualizationProps {
  timelineConsensus: TimelineConsensus;
  optimisticOutliers: Outlier[];
  pessimisticOutliers: Outlier[];
  color: string;
}

const TimelineVisualization: React.FC<TimelineVisualizationProps> = ({
  timelineConsensus,
  optimisticOutliers,
  pessimisticOutliers,
  color
}) => {
  const [hoveredOutlier, setHoveredOutlier] = useState<Outlier | null>(null);
  const [tooltipPosition, setTooltipPosition] = useState<{ x: number, y: number } | null>(null);

  // Timeline spans 2025 to 2050+
  const TIMELINE_START = 2025;
  const TIMELINE_END = 2050;
  const TIMELINE_SPAN = TIMELINE_END - TIMELINE_START;

  // Calculate position on timeline (percentage)
  const calculatePosition = (year: number): number => {
    return ((year - TIMELINE_START) / TIMELINE_SPAN) * 100;
  };

  const consensusStart = calculatePosition(timelineConsensus.consensus_window.start_year);
  const consensusEnd = calculatePosition(timelineConsensus.consensus_window.end_year);
  const consensusWidth = consensusEnd - consensusStart;

  // Get first outlier of each type for simplified view
  const pessimisticOutlier = pessimisticOutliers[0];
  const optimisticOutlier = optimisticOutliers[0];

  const handleOutlierHover = (outlier: Outlier, event: React.MouseEvent) => {
    setHoveredOutlier(outlier);
    setTooltipPosition({ x: event.clientX, y: event.clientY });
  };

  const handleOutlierLeave = () => {
    setHoveredOutlier(null);
    setTooltipPosition(null);
  };

  return (
    <div className="timeline-section">
      {/* Consensus button wrapper with purple background */}
      <div className="consensus-button-wrapper">
        {/* Consensus button bar - positioned based on consensus window */}
        <div
          className="consensus-button"
          style={{
            left: `${consensusStart}%`,
            width: `${consensusWidth}%`,
            backgroundColor: color
          }}
        >
          Consensus
        </div>

        {/* Thin timeline line below consensus bar */}
        <div className="timeline-thin-line">
          {/* Outlier dots on thin timeline line */}
          {pessimisticOutlier && (
            <div
              className="thumb thumb-red"
              style={{ left: `${calculatePosition(pessimisticOutlier.year)}%` }}
              onMouseEnter={(e) => handleOutlierHover(pessimisticOutlier, e)}
              onMouseLeave={handleOutlierLeave}
            />
          )}

          {optimisticOutlier && (
            <div
              className="thumb thumb-green"
              style={{ left: `${calculatePosition(optimisticOutlier.year)}%` }}
              onMouseEnter={(e) => handleOutlierHover(optimisticOutlier, e)}
              onMouseLeave={handleOutlierLeave}
            />
          )}
        </div>
      </div>

      {/* Year labels - dynamic */}
      <div className="timeline-labels">
        <div className="year-label">{TIMELINE_START}</div>
        <div className="year-label">2030</div>
        <div className="year-label">2040</div>
        <div className="year-label">{TIMELINE_END}+</div>
      </div>

      {/* Outlier Tooltip with high z-index */}
      {hoveredOutlier && tooltipPosition && (
        <div
          className="outlier-tooltip-fixed"
          style={{
            left: `${tooltipPosition.x}px`,
            top: `${tooltipPosition.y - 60}px`,
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: '4px' }}>
            {hoveredOutlier.scenario} ({hoveredOutlier.year})
          </div>
          <div style={{ fontSize: '11px', opacity: 0.9 }}>
            {hoveredOutlier.source_percentage}% of sources
          </div>
        </div>
      )}
    </div>
  );
};

export default TimelineVisualization;
