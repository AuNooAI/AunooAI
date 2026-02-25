/**
 * ThreatMapLegend Component
 * Legend for the threat intelligence map
 */

import { SEVERITY_LEVELS, SEVERITY_LABELS, SEVERITY_COLORS } from '../../../services/threatIntelligenceApi';

export function ThreatMapLegend() {
  return (
    <div className="absolute bottom-4 left-4 bg-gray-900/90 backdrop-blur-sm rounded-lg p-3 z-[1000]">
      <h4 className="text-xs font-semibold text-gray-300 mb-2">Severity Level</h4>
      <div className="space-y-1.5">
        {SEVERITY_LEVELS.map((level) => (
          <div key={level} className="flex items-center gap-2">
            <div
              className="w-3 h-3 rounded-full border border-white/30"
              style={{ backgroundColor: SEVERITY_COLORS[level] }}
            />
            <span className="text-xs text-gray-300">{SEVERITY_LABELS[level]}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
