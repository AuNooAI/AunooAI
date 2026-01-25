/**
 * MapLegend Component
 * Displays risk level legend for the hotspot map
 */

import { RISK_COLORS, RISK_LEVELS, type RiskLevel } from '../../../services/geopoliticalHotspotsApi';

interface MapLegendProps {
  className?: string;
}

export function MapLegend({ className = '' }: MapLegendProps) {
  const labels: Record<RiskLevel, string> = {
    critical: 'Critical',
    high: 'High',
    medium: 'Medium',
    low: 'Low',
    info: 'Info',
  };

  return (
    <div
      className={`absolute bottom-4 left-4 bg-gray-900/90 backdrop-blur-sm rounded-lg p-3 z-[1000] ${className}`}
    >
      <h4 className="text-xs font-medium text-gray-300 mb-2">Risk Level</h4>
      <div className="space-y-1.5">
        {RISK_LEVELS.map((level) => (
          <div key={level} className="flex items-center gap-2">
            <div
              className="w-3 h-3 rounded-full border border-white/50"
              style={{ backgroundColor: RISK_COLORS[level] }}
            />
            <span className="text-xs text-gray-300">{labels[level]}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
