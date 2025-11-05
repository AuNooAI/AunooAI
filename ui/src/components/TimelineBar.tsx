/**
 * Timeline Bar Component for Strategic Recommendations
 * Shows a full timeline from 2025-2040 with a colored indicator for the specific period
 */

interface TimelineBarProps {
  startYear: number;
  endYear: number;
  color: 'green' | 'yellow' | 'red';
}

const colorClasses = {
  green: 'bg-green-500',
  yellow: 'bg-amber-500',
  red: 'bg-rose-500',
};

export function TimelineBar({ startYear, endYear, color }: TimelineBarProps) {
  const TIMELINE_START = 2025;
  const TIMELINE_END = 2040;
  const totalYears = TIMELINE_END - TIMELINE_START;

  // Calculate position and width as percentages
  const startOffset = ((startYear - TIMELINE_START) / totalYears) * 100;
  const width = ((endYear - startYear) / totalYears) * 100;

  return (
    <div className="mt-4 pt-4 border-t border-gray-200">
      <div className="flex justify-between items-center mb-2">
        <span className="text-xs text-gray-600">{TIMELINE_START}</span>
        <span className="text-xs text-gray-600">{TIMELINE_END}</span>
      </div>
      <div className="relative h-2 bg-gray-200 rounded-full">
        <div
          className={`absolute h-full ${colorClasses[color]} rounded-full transition-all`}
          style={{
            left: `${startOffset}%`,
            width: `${width}%`
          }}
        ></div>
      </div>
    </div>
  );
}
