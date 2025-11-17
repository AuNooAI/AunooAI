/**
 * Impact Timeline Card Component
 */

import { useState, useRef, useEffect } from 'react';

interface ImpactTimelineCardProps {
  title: string;
  description: string;
  timelineStart: number;
  timelineEnd: number;
  tooltipPositions: Array<{ year: number; label: string }>;
  color: 'orange' | 'purple' | 'green' | 'blue' | 'pink' | 'lime';
  citations?: Array<{ title: string; url: string }>;
  keyInsightCitations?: Array<{ title: string; url: string }>;
}

interface TooltipPosition {
  year: number;
  label: string;
  position: number;
  row: number;
  originalIndex: number;
}

const colorClasses = {
  orange: {
    bg: 'bg-orange-100',
    text: 'text-orange-900',
    bar: 'bg-orange-300',
  },
  purple: {
    bg: 'bg-purple-100',
    text: 'text-purple-900',
    bar: 'bg-purple-300',
  },
  green: {
    bg: 'bg-green-100',
    text: 'text-green-900',
    bar: 'bg-green-300',
  },
  blue: {
    bg: 'bg-blue-100',
    text: 'text-blue-900',
    bar: 'bg-blue-300',
  },
  pink: {
    bg: 'bg-pink-100',
    text: 'text-pink-900',
    bar: 'bg-pink-300',
  },
  lime: {
    bg: 'bg-lime-100',
    text: 'text-lime-900',
    bar: 'bg-lime-300',
  },
};

export function ImpactTimelineCard({
  title,
  description,
  timelineStart,
  timelineEnd,
  tooltipPositions,
  color,
  citations = [],
  keyInsightCitations = [],
}: ImpactTimelineCardProps) {
  const colors = colorClasses[color];
  const totalYears = timelineEnd - timelineStart;
  const [showCitations, setShowCitations] = useState(false);
  const [calculatedPositions, setCalculatedPositions] = useState<TooltipPosition[]>([]);
  const labelRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const timelineContainerRef = useRef<HTMLDivElement>(null);

  // Calculate initial positions without collision detection
  const calculateInitialPositions = (): TooltipPosition[] => {
    if (!tooltipPositions || tooltipPositions.length === 0) return [];

    // Fixed timeline range: 2025-2040
    const FIXED_START = 2025;
    const FIXED_END = 2040;
    const fixedTotalYears = FIXED_END - FIXED_START;

    return tooltipPositions.map((tooltip, idx) => {
      // Calculate position relative to FIXED 2025-2040 timeline
      let position = ((tooltip.year - FIXED_START) / fixedTotalYears) * 100;
      position = Math.max(0, Math.min(100, position)); // Clamp to 0-100%

      return {
        ...tooltip,
        position,
        row: 0, // Start with all in row 0, will be adjusted for collisions
        originalIndex: idx
      };
    });
  };

  // Dynamic collision detection with actual text width measurement
  useEffect(() => {
    const positions = calculateInitialPositions();
    if (positions.length === 0) {
      setCalculatedPositions([]);
      return;
    }

    // Wait for DOM to render, then measure and detect collisions
    const timeoutId = setTimeout(() => {
      const timelineWidth = timelineContainerRef.current?.offsetWidth || 800;
      const PADDING = 12; // 12px padding between labels (increased for better spacing)

      // Track occupied ranges in each row: [{ start: px, end: px }]
      const rowOccupancy: Array<Array<{ start: number; end: number }>> = [[], [], []]; // 3 rows

      const positionsWithCollisionDetection = positions.map((tooltip, idx) => {
        // Get actual label width from DOM
        const labelElement = labelRefs.current.get(idx);
        // Better fallback: estimate width based on text length (~8px per character)
        const labelWidth = labelElement?.offsetWidth || (tooltip.label.length * 8);

        // Calculate pixel position on timeline
        const centerPx = (tooltip.position / 100) * timelineWidth;
        const startPx = centerPx - (labelWidth / 2);
        const endPx = centerPx + (labelWidth / 2);

        // Find first row where this label doesn't collide
        let assignedRow = 0;
        for (let row = 0; row < 3; row++) {
          const hasCollision = rowOccupancy[row].some(occupied => {
            // Check if ranges overlap (with padding)
            return !(endPx + PADDING < occupied.start || startPx - PADDING > occupied.end);
          });

          if (!hasCollision) {
            assignedRow = row;
            break;
          }
        }

        // Mark this range as occupied in the assigned row
        rowOccupancy[assignedRow].push({ start: startPx, end: endPx });

        return { ...tooltip, row: assignedRow };
      });

      setCalculatedPositions(positionsWithCollisionDetection);
    }, 100); // 100ms delay to ensure DOM is rendered and fonts are loaded

    return () => clearTimeout(timeoutId);
  }, [tooltipPositions]);

  const tooltipPositionsWithRows = calculatedPositions;

  // Calculate colored bar position/width for fixed 2025-2040 timeline
  const FIXED_START = 2025;
  const FIXED_END = 2040;
  const fixedTotalYears = FIXED_END - FIXED_START;

  // Calculate where the colored segment should start and end
  const coloredBarStart = Math.max(0, ((timelineStart - FIXED_START) / fixedTotalYears) * 100);
  const coloredBarEnd = Math.min(100, ((timelineEnd - FIXED_START) / fixedTotalYears) * 100);
  const coloredBarWidth = coloredBarEnd - coloredBarStart;

  return (
    <div className="grid grid-cols-[330px_1fr] gap-4 mb-4">
      {/* Left: Title and Description */}
      <div className={`${colors.bg} ${colors.text} rounded-xl p-5 relative`}>
        <h3 className="font-bold text-base mb-2">{title}</h3>
        <p className="text-sm mb-3">{description}</p>

        {/* Citations Badge - Compact hover display */}
        {citations && citations.length > 0 && (
          <div className="mt-3 relative">
            <button
              className="inline-flex items-center justify-center px-2.5 py-1 rounded-full bg-white/50 hover:bg-white/80 border border-current/20 text-xs font-semibold cursor-pointer transition-colors print:hidden"
              onMouseEnter={() => setShowCitations(true)}
              onMouseLeave={() => setShowCitations(false)}
              onClick={() => setShowCitations(!showCitations)}
              title="View sources"
            >
              Sources
            </button>

            {/* Citation popup on hover/click */}
            {showCitations && (
              <div
                className="absolute left-0 top-8 z-10 bg-white border border-gray-300 rounded-lg shadow-lg p-3 min-w-[300px] max-w-[400px]"
                onMouseEnter={() => setShowCitations(true)}
                onMouseLeave={() => setShowCitations(false)}
              >
                <div className="text-xs font-semibold mb-2 text-gray-700">Sources:</div>
                <div className="space-y-1.5">
                  {citations.slice(0, 5).map((citation, idx) => (
                    <div key={idx} className="text-xs">
                      <a
                        href={citation.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:underline"
                      >
                        [{idx + 1}] {citation.title}
                      </a>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Print-only citation list - visible in PDF/image exports */}
            <div className="hidden print:block mt-3 pt-3 border-t border-current/20">
              <div className="text-xs font-semibold mb-1.5">Sources:</div>
              <div className="space-y-1">
                {citations.slice(0, 5).map((citation, idx) => (
                  <div key={idx} className="text-[11px] leading-tight">
                    [{idx + 1}] {citation.title}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Right: Timeline */}
      <div className="bg-white border border-gray-200 rounded-xl p-5 flex items-center">
        <div className="flex-1" ref={timelineContainerRef}>
          {/* Year labels - FIXED 2025-2040 */}
          <div className="flex justify-between text-xs text-gray-700 mb-2 px-1">
            <span>2025</span>
            <span>2040</span>
          </div>

          {/* Timeline bar with tooltips */}
          <div className="relative h-40">
            {/* Background bar - full width gray (2025-2040) */}
            <div className="absolute top-16 left-0 right-0 h-2 bg-gray-200 rounded-full"></div>

            {/* Colored segment showing this card's impact period */}
            <div
              className={`absolute top-16 h-2 ${colors.bar} rounded-full`}
              style={{
                left: `${coloredBarStart}%`,
                width: `${coloredBarWidth}%`,
              }}
            ></div>

            {/* Tooltip markers with dynamic collision detection */}
            {tooltipPositionsWithRows.map((tooltip, idx) => {
              // Dynamic row positioning with 3 rows
              // Timeline bar is at 64px (top-16)
              // Row 0: 54px (10px above timeline)
              // Row 1: 74px (10px below timeline)
              // Row 2: 44px (20px above timeline)
              const getTopOffset = (row: number) => {
                if (row === 0) return '54px';  // 10px above timeline (64 - 10)
                if (row === 1) return '74px';  // 10px BELOW timeline (64 + 10)
                return '44px';                 // 20px above timeline (64 - 20)
              };

              const getLabelTopOffset = (row: number) => {
                if (row === 0) return '-top-10';   // Above timeline
                if (row === 1) return 'top-6';     // Below timeline
                return '-top-14';                  // Highest above timeline
              };

              const topOffset = getTopOffset(tooltip.row);
              const labelTopOffset = getLabelTopOffset(tooltip.row);

              return (
                <div
                  key={idx}
                  className="absolute group"
                  style={{
                    left: `${tooltip.position}%`,
                    transform: 'translateX(-50%)',
                    top: topOffset
                  }}
                  title={`${tooltip.label} (${tooltip.year})`}
                >
                  {/* Tooltip label - collision-aware position with ref for measurement and colored badge */}
                  <div
                    ref={(el) => {
                      if (el) labelRefs.current.set(idx, el);
                      else labelRefs.current.delete(idx);
                    }}
                    className={`absolute left-1/2 transform -translate-x-1/2 ${colors.bar} bg-opacity-70 text-gray-900 text-xs px-2.5 py-1 rounded-md font-medium whitespace-nowrap ${labelTopOffset} group-hover:bg-opacity-100 group-hover:scale-105 transition-all duration-200 shadow-sm`}
                  >
                    {tooltip.label}
                  </div>

                  {/* Hover tooltip with full info */}
                  <div
                    className="absolute left-1/2 transform -translate-x-1/2 -top-24 bg-gray-900 text-white text-xs px-3 py-2 rounded-lg shadow-lg whitespace-normal w-48 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-20"
                  >
                    <div className="font-semibold mb-1">{tooltip.label}</div>
                    <div className="text-gray-300">{tooltip.year}</div>
                  </div>

                  {/* Dot marker - colored to match category */}
                  <div className={`w-2.5 h-2.5 ${colors.bar} rounded-full cursor-help group-hover:scale-125 transition-transform duration-200 shadow-sm`}></div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
