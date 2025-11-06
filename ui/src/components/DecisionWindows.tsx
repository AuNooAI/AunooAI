import React from 'react';
import './consensus.css';

interface DecisionWindow {
  urgency: 'Critical' | 'High' | 'Medium' | 'Low';
  window: string;
  action: string;
  rationale: string;
  owner: string;
  dependencies: string[];
  success_metrics: string[];
}

interface DecisionWindowsProps {
  windows: DecisionWindow[];
}

const DecisionWindows: React.FC<DecisionWindowsProps> = ({ windows }) => {
  const getUrgencyClass = (urgency: string): string => {
    return `decision-window urgency-${urgency.toLowerCase()}`;
  };

  const getUrgencyBadgeClass = (urgency: string): string => {
    return `urgency-badge urgency-${urgency.toLowerCase()}`;
  };

  return (
    <div className="decision-windows">
      <div className="section-title">
        <span>🎯</span>
        <span>Key Decision Windows</span>
      </div>
      {windows.map((window, index) => (
        <div key={index} className={getUrgencyClass(window.urgency)}>
          <div className="decision-header">
            <div className="decision-action">{window.action}</div>
            <div className={getUrgencyBadgeClass(window.urgency)}>
              {window.urgency}
            </div>
          </div>
          <div className="decision-rationale">{window.rationale}</div>
          <div className="decision-meta">
            <div>
              <strong>Timeframe:</strong> {window.window}
            </div>
            <div>
              <strong>Owner:</strong> {window.owner}
            </div>
          </div>
          {window.dependencies && window.dependencies.length > 0 && (
            <div style={{ marginTop: '8px', fontSize: '12px', color: '#6b7280' }}>
              <strong>Dependencies:</strong> {window.dependencies.join(', ')}
            </div>
          )}
          {window.success_metrics && window.success_metrics.length > 0 && (
            <div style={{ marginTop: '4px', fontSize: '12px', color: '#6b7280' }}>
              <strong>Success Metrics:</strong> {window.success_metrics.join(', ')}
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

export default DecisionWindows;
