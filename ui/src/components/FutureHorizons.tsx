/**
 * Future Horizons Tab Component with Three Horizons Model
 * Shows transitions from current state (H1) through innovation (H2) to future vision (H3)
 */

import { useState } from 'react';
import { X } from 'lucide-react';
import '../styles/citations.css';

interface Scenario {
  type: 'h1' | 'h2' | 'h3'; // Three Horizons: H1 (current), H2 (transition), H3 (future)
  title: string;
  description: string;
  timeframe: string;
  sentiment?: string;
  drivers?: Array<{ type: string; description: string }>;
  signals?: string[];
}

interface Article {
  id?: number;
  uri?: string;
  url?: string;
  title: string;
  source?: string;
  source_name?: string;
  publication_date?: string;
}

interface FutureHorizonsProps {
  scenarios: Scenario[];
  articleList?: Article[];
}

export function FutureHorizons({ scenarios, articleList = [] }: FutureHorizonsProps) {
  const [selectedScenario, setSelectedScenario] = useState<Scenario | null>(null);

  // Parse timeframe to get years
  const parseTimeframe = (timeframe: string): { start: number; end: number } => {
    const years = timeframe.match(/\d{4}/g);
    if (years && years.length >= 2) {
      return { start: parseInt(years[0]), end: parseInt(years[1]) };
    }
    return { start: 2025, end: 2040 };
  };

  // Interpolate along actual SVG Bezier curves
  const interpolateBezier = (t: number, points: number[][]): number => {
    // For quadratic Bezier: B(t) = (1-t)^2 * P0 + 2(1-t)t * P1 + t^2 * P2
    const [p0, p1, p2] = points;
    const mt = 1 - t;
    return mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1];
  };

  // Get Y coordinate for a given X position on a specific wave
  const getYOnCurve = (x: number, waveType: 'h1' | 'h2' | 'h3'): number => {
    const t = x / 100;
    let y = 50;

    switch (waveType) {
      case 'h1': // Blue wave: M 0,25 Q 25,28 50,45 T 100,75
        if (t <= 0.5) {
          const localT = t / 0.5;
          y = interpolateBezier(localT, [[0, 25], [25, 28], [50, 45]]);
        } else {
          const localT = (t - 0.5) / 0.5;
          y = interpolateBezier(localT, [[50, 45], [75, 62], [100, 75]]);
        }
        break;

      case 'h2': // Purple wave: M 0,85 Q 25,75 40,55 Q 55,35 70,40 Q 85,45 100,60
        if (t <= 0.4) {
          const localT = t / 0.4;
          y = interpolateBezier(localT, [[0, 85], [25, 75], [40, 55]]);
        } else if (t <= 0.7) {
          const localT = (t - 0.4) / 0.3;
          y = interpolateBezier(localT, [[40, 55], [55, 35], [70, 40]]);
        } else {
          const localT = (t - 0.7) / 0.3;
          y = interpolateBezier(localT, [[70, 40], [85, 45], [100, 60]]);
        }
        break;

      case 'h3': // Green wave: M 0,95 Q 30,95 50,85 Q 70,75 85,55 T 100,20
        if (t <= 0.5) {
          const localT = t / 0.5;
          y = interpolateBezier(localT, [[0, 95], [30, 95], [50, 85]]);
        } else if (t <= 0.85) {
          const localT = (t - 0.5) / 0.35;
          y = interpolateBezier(localT, [[50, 85], [70, 75], [85, 55]]);
        } else {
          const localT = (t - 0.85) / 0.15;
          y = interpolateBezier(localT, [[85, 55], [92.5, 37.5], [100, 20]]);
        }
        break;
    }

    return y;
  };

  // Calculate position on Three Horizons curves for scenario markers
  const calculateHorizonPosition = (scenario: Scenario, idx: number, typeIndex: number, totalInType: number): { x: number; y: number } => {
    const { start, end } = parseTimeframe(scenario.timeframe);
    const avgYear = (start + end) / 2;

    // X position based on time (10% at 2025, 90% at 2040)
    const baseX = 10 + ((avgYear - 2025) / 15) * 75;

    // Distribute cards within their type group to prevent overlap
    // Spread them across the X axis more aggressively
    const spreadFactor = totalInType > 1 ? (typeIndex / (totalInType - 1) - 0.5) * 40 : 0;
    const x = Math.min(92, Math.max(8, baseX + spreadFactor));

    // Get Y position on the curve for this X
    let y = getYOnCurve(x, scenario.type);

    // Add alternating vertical offset to prevent overlap
    const verticalOffset = (typeIndex % 3 - 1) * 8;
    y += verticalOffset;

    return { x, y };
  };

  // Replace [1], [2] citations with clickable links
  const replaceCitations = (text: string): string => {
    if (!text) return '';

    return text.replace(/\[(\d+)\]/g, (match, num) => {
      const index = parseInt(num) - 1;
      const article = articleList[index];

      if (article && (article.url || article.uri)) {
        const url = article.url || article.uri || '#';
        const title = article.title || 'Unknown';
        const source = article.source || article.source_name || 'Unknown source';

        return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="citation-link" title="${title} - ${source}">[${num}]</a>`;
      }
      return match;
    });
  };

  // Timeline slider component for each scenario card
  const TimelineSlider = ({ scenario }: { scenario: Scenario }) => {
    const { start, end } = parseTimeframe(scenario.timeframe);
    const totalYears = 2040 - 2025; // 15 years
    const startPercent = ((start - 2025) / totalYears) * 100;
    const endPercent = ((end - 2025) / totalYears) * 100;
    const rangeWidth = endPercent - startPercent;

    return (
      <div className="mt-3">
        {/* Timeline track */}
        <div className="relative h-2 bg-gray-300 rounded-full">
          {/* Active range indicator */}
          <div
            className="absolute top-0 h-full bg-gradient-to-r from-gray-600 to-gray-800 rounded-full"
            style={{
              left: `${startPercent}%`,
              width: `${rangeWidth}%`,
            }}
          />
          {/* Start marker */}
          <div
            className="absolute top-1/2 w-3 h-3 bg-white border-2 border-gray-800 rounded-full shadow-sm"
            style={{ left: `${startPercent}%`, transform: 'translate(-50%, -50%)' }}
          />
          {/* End marker */}
          <div
            className="absolute top-1/2 w-3 h-3 bg-white border-2 border-gray-800 rounded-full shadow-sm"
            style={{ left: `${endPercent}%`, transform: 'translate(-50%, -50%)' }}
          />
        </div>
        {/* Year labels */}
        <div className="flex justify-between text-[9px] text-gray-700 font-medium mt-1">
          <span>2025<br/>Present</span>
          <span>2029<br/>Short</span>
          <span>2033<br/>Mid</span>
          <span>2037<br/>Long</span>
          <span>2040<br/>Horizon</span>
        </div>
      </div>
    );
  };

  // Three Horizons definitions
  const horizons = [
    {
      key: 'h1',
      label: 'Current',
      subtitle: 'Declining Systems',
      tooltip: 'The dominant paradigm today - business-as-usual trends that are gradually declining as new innovations emerge',
      color: 'blue',
      bgClass: 'bg-blue-600',
      textClass: 'text-blue-600'
    },
    {
      key: 'h2',
      label: 'Transition',
      subtitle: 'Innovation',
      tooltip: 'Emerging innovations and disruptions - entrepreneurial activity, pilot projects, and transitional period where old and new coexist',
      color: 'purple',
      bgClass: 'bg-purple-600',
      textClass: 'text-purple-600'
    },
    {
      key: 'h3',
      label: 'Future',
      subtitle: 'Emerging Vision',
      tooltip: 'Transformative visions becoming reality - preferred future state where the new paradigm is fully established',
      color: 'green',
      bgClass: 'bg-green-600',
      textClass: 'text-green-600'
    },
  ];

  return (
    <div className="space-y-8">
      {/* Three Horizons Visualization */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm" style={{ overflow: 'visible' }}>
        {/* Title and Description */}
        <div className="border-b border-gray-200 bg-gradient-to-r from-blue-50 via-purple-50 to-green-50 px-6 py-4">
          <h3 className="text-lg font-bold text-gray-900">Three Horizons Model</h3>
          <p className="text-sm text-gray-600 mt-1">
            Visualizing the transition from current systems (H1) through emerging innovations (H2) to future visions (H3)
          </p>
        </div>

        {/* Waves Container */}
        <div className="relative bg-gradient-to-br from-pink-50 via-purple-50 to-blue-50" style={{ height: '500px' }}>
          {/* SVG Three Horizons Waves */}
          <svg className="absolute inset-0 w-full h-full" viewBox="0 0 100 100" preserveAspectRatio="none">
            <defs>
              {/* H1 gradient - Blue with pink tones (declining) */}
              <linearGradient id="h1Gradient" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" style={{ stopColor: '#3b82f6', stopOpacity: 0.7 }} />
                <stop offset="50%" style={{ stopColor: '#ec4899', stopOpacity: 0.3 }} />
                <stop offset="100%" style={{ stopColor: '#93c5fd', stopOpacity: 0.2 }} />
              </linearGradient>
              {/* H2 gradient - Purple with pink (transitioning) */}
              <linearGradient id="h2Gradient" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" style={{ stopColor: '#a855f7', stopOpacity: 0.3 }} />
                <stop offset="50%" style={{ stopColor: '#ec4899', stopOpacity: 0.7 }} />
                <stop offset="100%" style={{ stopColor: '#c084fc', stopOpacity: 0.3 }} />
              </linearGradient>
              {/* H3 gradient - Green with pink accents (emerging) */}
              <linearGradient id="h3Gradient" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" style={{ stopColor: '#22c55e', stopOpacity: 0.2 }} />
                <stop offset="50%" style={{ stopColor: '#f472b6', stopOpacity: 0.4 }} />
                <stop offset="100%" style={{ stopColor: '#4ade80', stopOpacity: 0.7 }} />
              </linearGradient>
            </defs>

            {/* H1 - Current/Declining (Blue wave starting high, declining) */}
            <path
              d="M 0,25 Q 25,28 50,45 T 100,75 L 100,100 L 0,100 Z"
              fill="url(#h1Gradient)"
            />
            <path
              d="M 0,25 Q 25,28 50,45 T 100,75"
              fill="none"
              stroke="#2563eb"
              strokeWidth="0.6"
            />

            {/* H2 - Transition/Innovation (Purple bell curve) */}
            <path
              d="M 0,85 Q 25,75 40,55 Q 55,35 70,40 Q 85,45 100,60 L 100,100 L 0,100 Z"
              fill="url(#h2Gradient)"
            />
            <path
              d="M 0,85 Q 25,75 40,55 Q 55,35 70,40 Q 85,45 100,60"
              fill="none"
              stroke="#9333ea"
              strokeWidth="0.6"
            />

            {/* H3 - Future Vision (Green wave starting low, rising) */}
            <path
              d="M 0,95 Q 30,95 50,85 Q 70,75 85,55 T 100,20 L 100,100 L 0,100 Z"
              fill="url(#h3Gradient)"
            />
            <path
              d="M 0,95 Q 30,95 50,85 Q 70,75 85,55 T 100,20"
              fill="none"
              stroke="#16a34a"
              strokeWidth="0.6"
            />

            {/* NOW marker at left */}
            <circle cx="3" cy="50" r="2" fill="#1f2937" />
            <text x="3" y="58" fontSize="3" fill="#1f2937" textAnchor="middle" fontWeight="bold">NOW</text>
          </svg>

          {/* Horizon labels on left with tooltips - positioned at wave start points */}
          <div className="absolute left-3 top-0 bottom-0 text-xs font-medium pointer-events-auto z-20">
            {horizons.map(({ key, label, tooltip, bgClass }) => {
              // Position badges at wave starting points
              const topPosition =
                key === 'h1' ? '25%' :  // Blue wave starts at ~25%
                key === 'h2' ? '85%' :  // Purple wave starts at ~85%
                '95%';                   // Green wave starts at ~95%

              return (
                <div key={key} className="absolute relative group" style={{ top: topPosition, transform: 'translateY(-50%)' }}>
                  <div className={`${bgClass} text-white px-3 py-1.5 rounded shadow-md cursor-help`}>
                    {label}
                  </div>
                  {/* Tooltip on hover */}
                  <div className="absolute left-full ml-3 top-1/2 -translate-y-1/2 hidden group-hover:block z-50 pointer-events-none">
                    <div className="bg-gray-900 text-white text-xs rounded-lg p-3 shadow-xl max-w-xs">
                      <div className="font-semibold mb-1">{label}</div>
                      {tooltip}
                      {/* Arrow pointing left */}
                      <div className="absolute right-full top-1/2 -translate-y-1/2 border-[6px] border-transparent border-r-gray-900"></div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Scenario markers ON the waves */}
          {(() => {
            // Group scenarios by type and sort by timeframe within each type
            const h1Scenarios = scenarios.filter(s => s.type === 'h1').sort((a, b) => {
              const { start: aStart } = parseTimeframe(a.timeframe);
              const { start: bStart } = parseTimeframe(b.timeframe);
              return aStart - bStart;
            });
            const h2Scenarios = scenarios.filter(s => s.type === 'h2').sort((a, b) => {
              const { start: aStart } = parseTimeframe(a.timeframe);
              const { start: bStart } = parseTimeframe(b.timeframe);
              return aStart - bStart;
            });
            const h3Scenarios = scenarios.filter(s => s.type === 'h3').sort((a, b) => {
              const { start: aStart } = parseTimeframe(a.timeframe);
              const { start: bStart } = parseTimeframe(b.timeframe);
              return aStart - bStart;
            });

            // Create indexed scenarios with their position within their type
            const indexedScenarios = [
              ...h1Scenarios.map((s, i) => ({ scenario: s, typeIndex: i, totalInType: h1Scenarios.length })),
              ...h2Scenarios.map((s, i) => ({ scenario: s, typeIndex: i, totalInType: h2Scenarios.length })),
              ...h3Scenarios.map((s, i) => ({ scenario: s, typeIndex: i, totalInType: h3Scenarios.length })),
            ];

            return indexedScenarios.map(({ scenario, typeIndex, totalInType }, idx) => {
              const pos = calculateHorizonPosition(scenario, idx, typeIndex, totalInType);

            // Get border color matching horizon
            const borderColor =
              scenario.type === 'h1' ? 'border-blue-600' :
              scenario.type === 'h2' ? 'border-purple-600' :
              'border-green-600'; // h3

            const bgColor =
              scenario.type === 'h1' ? 'bg-blue-50' :
              scenario.type === 'h2' ? 'bg-purple-50' :
              'bg-green-50'; // h3

            return (
              <div
                key={idx}
                className="absolute transform -translate-x-1/2 -translate-y-1/2 z-10 group cursor-pointer"
                style={{
                  left: `${pos.x}%`,
                  top: `${pos.y}%`,
                }}
                onClick={() => setSelectedScenario(scenario)}
              >
                {/* Small card with title */}
                <div className={`${bgColor} border-2 ${borderColor} rounded px-2 py-1 shadow-md hover:shadow-xl transition-all max-w-[140px]`}>
                  <div className="text-[9px] font-bold text-gray-900 leading-tight line-clamp-2">
                    {scenario.title}
                  </div>
                </div>

                {/* Hover popup with details */}
                <div className="absolute left-full ml-2 top-0 hidden group-hover:block z-50 pointer-events-none">
                  <div className="bg-gray-900 text-white text-xs rounded-lg p-3 shadow-xl w-64">
                    <div className="font-bold mb-1">{scenario.title}</div>
                    <div className="text-[10px] mb-2 opacity-90">{scenario.timeframe}</div>
                    <p
                      className="text-[10px] leading-relaxed"
                      dangerouslySetInnerHTML={{ __html: replaceCitations(scenario.description.substring(0, 150) + '...') }}
                    />
                    {/* Arrow pointing left */}
                    <div className="absolute right-full top-4 border-[6px] border-transparent border-r-gray-900"></div>
                  </div>
                </div>
              </div>
            );
          });
          })()}
        </div>

        {/* Timeline at bottom */}
        <div className="border-t border-gray-200 bg-gray-50 px-8 py-3">
          <div className="flex justify-between text-sm text-gray-600">
            <div><span className="font-semibold">2025</span><br/><span className="text-xs">Present</span></div>
            <div><span className="font-semibold">2029</span><br/><span className="text-xs">Short-term</span></div>
            <div><span className="font-semibold">2033</span><br/><span className="text-xs">Mid-term</span></div>
            <div><span className="font-semibold">2037</span><br/><span className="text-xs">Long-term</span></div>
            <div><span className="font-semibold">2040</span><br/><span className="text-xs">Horizon</span></div>
          </div>
        </div>
      </div>

      {/* Three Horizons Columns */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {horizons.map(({ key, label, subtitle, tooltip, bgClass }) => {
          const typeScenarios = scenarios.filter(s => s.type === key);

          return (
            <div key={key} className="flex flex-col">
              {/* Column header */}
              <div className={`${bgClass} text-white px-4 py-3 rounded-t-lg text-center group relative`}>
                <div className="font-bold text-sm">{label}</div>
                <div className="text-xs opacity-90">{subtitle}</div>
                {/* Tooltip on hover */}
                <div className="absolute left-1/2 -translate-x-1/2 top-full mt-2 hidden group-hover:block z-50 pointer-events-none">
                  <div className="bg-gray-900 text-white text-xs rounded-lg p-3 shadow-xl max-w-xs whitespace-normal">
                    {tooltip}
                    {/* Arrow pointing up */}
                    <div className="absolute bottom-full left-1/2 -translate-x-1/2 border-[6px] border-transparent border-b-gray-900"></div>
                  </div>
                </div>
              </div>

              {/* Scenario cards */}
              <div className="bg-gray-50 rounded-b-lg p-3 space-y-3 flex-1">
                {typeScenarios.length > 0 ? (
                  typeScenarios.map((scenario, idx) => (
                    <div
                      key={idx}
                      className="bg-white rounded-lg p-3 border border-gray-200 hover:shadow-lg transition-shadow cursor-pointer"
                      onClick={() => setSelectedScenario(scenario)}
                    >
                      {/* Title with edit icon */}
                      <div className="flex items-start justify-between mb-2">
                        <h4 className="font-semibold text-sm text-gray-900 flex-1 leading-tight">
                          {scenario.title}
                        </h4>
                        <button className="text-gray-400 hover:text-gray-600 ml-2 flex-shrink-0">
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                          </svg>
                        </button>
                      </div>

                      {/* Description with citations */}
                      <p
                        className="text-xs text-gray-800 mb-3 leading-relaxed"
                        dangerouslySetInnerHTML={{ __html: replaceCitations(scenario.description) }}
                      />

                      {/* Individual timeline slider */}
                      <TimelineSlider scenario={scenario} />
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-gray-500 text-center py-4">No {label.toLowerCase()} scenarios</p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Detailed scenario modal */}
      {selectedScenario && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl max-w-3xl w-full max-h-[90vh] overflow-y-auto">
            <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold text-gray-900">{selectedScenario.title}</h2>
                <div className="flex items-center gap-3 mt-1">
                  <span className="text-sm text-gray-500">{selectedScenario.timeframe}</span>
                  <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                    selectedScenario.type === 'h1' ? 'bg-blue-100 text-blue-800' :
                    selectedScenario.type === 'h2' ? 'bg-purple-100 text-purple-800' :
                    'bg-green-100 text-green-800' // h3
                  }`}>
                    {selectedScenario.type === 'h1' ? 'Current' :
                     selectedScenario.type === 'h2' ? 'Transition' :
                     'Future'}
                  </span>
                </div>
              </div>
              <button
                onClick={() => setSelectedScenario(null)}
                className="text-gray-400 hover:text-gray-600"
              >
                <X className="w-6 h-6" />
              </button>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <h3 className="font-semibold text-gray-700 mb-2">Description</h3>
                <p
                  className="text-gray-600 leading-relaxed"
                  dangerouslySetInnerHTML={{ __html: replaceCitations(selectedScenario.description) }}
                />
              </div>
              {selectedScenario.sentiment && (
                <div>
                  <h3 className="font-semibold text-gray-700 mb-2">Sentiment</h3>
                  <span className="text-gray-600">{selectedScenario.sentiment}</span>
                </div>
              )}
              {selectedScenario.drivers && selectedScenario.drivers.length > 0 && (
                <div>
                  <h3 className="font-semibold text-gray-700 mb-2">Key Drivers</h3>
                  <ul className="space-y-2">
                    {selectedScenario.drivers.map((driver, idx) => (
                      <li key={idx} className="text-gray-600">
                        <span className="font-medium">{driver.type}:</span> {driver.description}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {selectedScenario.signals && selectedScenario.signals.length > 0 && (
                <div>
                  <h3 className="font-semibold text-gray-700 mb-2">Signals</h3>
                  <ul className="list-disc list-inside space-y-1">
                    {selectedScenario.signals.map((signal, idx) => (
                      <li key={idx} className="text-gray-600">{signal}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
