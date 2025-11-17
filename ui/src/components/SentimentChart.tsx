import React from 'react';
import './consensus.css';

interface SentimentDistribution {
  positive: number;
  neutral: number;
  critical: number;
}

interface SentimentChartProps {
  distribution: SentimentDistribution;
}

const SentimentChart: React.FC<SentimentChartProps> = ({ distribution }) => {
  return (
    <div className="sentiment-chart-thin">
      <div style={{ fontSize: '11px', fontWeight: 600, marginBottom: '6px', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
        Sentiment Distribution
      </div>
      {/* Thin sentiment line */}
      <div className="sentiment-line-container">
        {distribution.positive > 0 && (
          <div
            className="sentiment-segment sentiment-positive"
            style={{ width: `${distribution.positive}%` }}
            title={`Positive: ${distribution.positive}%`}
          />
        )}
        {distribution.neutral > 0 && (
          <div
            className="sentiment-segment sentiment-neutral"
            style={{ width: `${distribution.neutral}%` }}
            title={`Neutral: ${distribution.neutral}%`}
          />
        )}
        {distribution.critical > 0 && (
          <div
            className="sentiment-segment sentiment-critical"
            style={{ width: `${distribution.critical}%` }}
            title={`Critical: ${distribution.critical}%`}
          />
        )}
      </div>
      {/* Labels below */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '6px', fontSize: '11px', color: '#9ca3af' }}>
        <span style={{ color: '#10b981' }}>✓ {distribution.positive}%</span>
        <span style={{ color: '#6b7280' }}>⊙ {distribution.neutral}%</span>
        <span style={{ color: '#ef4444' }}>✗ {distribution.critical}%</span>
      </div>
    </div>
  );
};

export default SentimentChart;
