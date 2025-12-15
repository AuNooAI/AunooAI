/**
 * ScenarioMiniMatrix - Compact 2x2 scenario matrix
 *
 * Shows all four 2030 scenarios in a scannable grid:
 * - Trusted Ecosystem (high reg, low concentration)
 * - Fragmented Compliance (high reg, high concentration)
 * - Open Chaos (low reg, low concentration)
 * - Behemoth Control (low reg, high concentration)
 *
 * Highlights the "most likely" scenario and shows probability shift.
 */

import React from 'react';
import { TrendingUp, TrendingDown, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import type { ScenarioAnalysis } from '../../hooks/usePAM';

// Scenario definitions with positions in the matrix
const SCENARIO_CONFIG = [
  // Top row: High Regulation
  {
    id: 'trustedEcosystem',
    name: 'Trusted Ecosystem',
    shortName: 'TE',
    icon: '🛡️',
    position: 'top-left',
    color: 'bg-green-50 border-green-300 hover:bg-green-100',
    activeColor: 'ring-2 ring-green-500 bg-green-100',
  },
  {
    id: 'fragmentedCompliance',
    name: 'Fragmented Compliance',
    shortName: 'FC',
    icon: '🧩',
    position: 'top-right',
    color: 'bg-yellow-50 border-yellow-300 hover:bg-yellow-100',
    activeColor: 'ring-2 ring-yellow-500 bg-yellow-100',
  },
  // Bottom row: Low Regulation
  {
    id: 'openChaos',
    name: 'Open Chaos',
    shortName: 'OC',
    icon: '🌪️',
    position: 'bottom-left',
    color: 'bg-gray-50 border-gray-300 hover:bg-gray-100',
    activeColor: 'ring-2 ring-gray-500 bg-gray-100',
  },
  {
    id: 'behemothControl',
    name: 'Behemoth Control',
    shortName: 'BC',
    icon: '🏢',
    position: 'bottom-right',
    color: 'bg-red-50 border-red-300 hover:bg-red-100',
    activeColor: 'ring-2 ring-red-500 bg-red-100',
  },
];

interface ScenarioMiniMatrixProps {
  scenarios?: ScenarioAnalysis['scenarios'];
  mostLikely?: string;
  probabilityShift?: string;
  onClick: () => void;
}

const ScenarioMiniMatrix: React.FC<ScenarioMiniMatrixProps> = ({
  scenarios,
  mostLikely,
  probabilityShift,
  onClick,
}) => {
  // Normalize most likely ID (snake_case to camelCase)
  const normalizedMostLikely = mostLikely?.replace(/_([a-z])/g, (_, l: string) =>
    l.toUpperCase()
  );

  const getScenarioData = (id: string) => {
    if (!scenarios) return null;
    return scenarios[id] || null;
  };

  const getProbabilityDisplay = (id: string) => {
    const data = getScenarioData(id);
    if (!data) return '--';
    return `${Math.round(data.currentProbability)}%`;
  };

  // Parse probability shift to show direction
  const getProbabilityShiftIndicator = () => {
    if (!probabilityShift) return null;

    const isPositive =
      probabilityShift.includes('+') ||
      probabilityShift.toLowerCase().includes('toward');
    const isNegative =
      probabilityShift.includes('-') ||
      probabilityShift.toLowerCase().includes('away');

    if (isPositive) {
      return (
        <span className="flex items-center gap-1 text-red-600">
          <TrendingUp className="w-3 h-3" />
          {probabilityShift}
        </span>
      );
    }
    if (isNegative) {
      return (
        <span className="flex items-center gap-1 text-green-600">
          <TrendingDown className="w-3 h-3" />
          {probabilityShift}
        </span>
      );
    }
    return <span className="text-gray-500">{probabilityShift}</span>;
  };

  return (
    <Card
      className="cursor-pointer hover:shadow-md transition-shadow"
      onClick={onClick}
    >
      <CardHeader className="pb-2">
        <CardTitle className="text-lg flex items-center justify-between">
          <span>2030 Scenarios</span>
          <ChevronRight className="w-4 h-4 text-gray-400" />
        </CardTitle>
      </CardHeader>
      <CardContent>
        {/* Axis Labels */}
        <div className="relative mb-1">
          <div className="text-xs text-gray-500 text-center">
            ← Distributed | Concentrated →
          </div>
        </div>

        {/* 2x2 Matrix */}
        <div className="relative">
          {/* Left axis label */}
          <div className="absolute -left-4 top-1/2 -translate-y-1/2 -rotate-90 text-xs text-gray-500 whitespace-nowrap w-0">
            High Reg ↑
          </div>

          <div className="grid grid-cols-2 gap-1.5 ml-2">
            {/* Top row: High Regulation */}
            {SCENARIO_CONFIG.slice(0, 2).map((scenario) => {
              const isActive = normalizedMostLikely === scenario.id;
              return (
                <div
                  key={scenario.id}
                  className={`p-2 rounded border transition-all ${
                    isActive ? scenario.activeColor : scenario.color
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-lg">{scenario.icon}</span>
                    {isActive && (
                      <Badge className="bg-pink-500 text-xs px-1 py-0">
                        Likely
                      </Badge>
                    )}
                  </div>
                  <div className="text-xs font-medium truncate">
                    {scenario.shortName}
                  </div>
                  <div className="text-lg font-bold">
                    {getProbabilityDisplay(scenario.id)}
                  </div>
                </div>
              );
            })}

            {/* Bottom row: Low Regulation */}
            {SCENARIO_CONFIG.slice(2, 4).map((scenario) => {
              const isActive = normalizedMostLikely === scenario.id;
              return (
                <div
                  key={scenario.id}
                  className={`p-2 rounded border transition-all ${
                    isActive ? scenario.activeColor : scenario.color
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-lg">{scenario.icon}</span>
                    {isActive && (
                      <Badge className="bg-pink-500 text-xs px-1 py-0">
                        Likely
                      </Badge>
                    )}
                  </div>
                  <div className="text-xs font-medium truncate">
                    {scenario.shortName}
                  </div>
                  <div className="text-lg font-bold">
                    {getProbabilityDisplay(scenario.id)}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Right axis label */}
          <div className="absolute -right-2 top-1/2 -translate-y-1/2 rotate-90 text-xs text-gray-500 whitespace-nowrap w-0">
            ↓ Low Reg
          </div>
        </div>

        {/* Probability Shift Indicator */}
        {probabilityShift && (
          <div className="mt-2 pt-2 border-t text-xs text-center">
            {getProbabilityShiftIndicator()}
          </div>
        )}

        {/* Legend */}
        <div className="mt-2 pt-2 border-t text-xs text-gray-500">
          <div className="grid grid-cols-2 gap-1">
            <span>🛡️ TE: Trust Ecosystem</span>
            <span>🧩 FC: Fragmented</span>
            <span>🌪️ OC: Open Chaos</span>
            <span>🏢 BC: Behemoth</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default ScenarioMiniMatrix;
