/**
 * Timeline Bar Component for Strategic Recommendations
 */

interface TimelineBarProps {
  startYear: number;
  endYear: number;
  color: 'green' | 'yellow' | 'red';
}

const colorClasses = {
  green: 'bg-green-400',
  yellow: 'bg-yellow-400',
  red: 'bg-red-400',
};

export function TimelineBar({ startYear, endYear, color }: TimelineBarProps) {
  return (
    <div className="mt-4 pt-4 border-t border-gray-200">
      <div className="flex justify-between items-center mb-2">
        <span className="text-xs text-gray-700">{startYear}</span>
        <span className="text-xs text-gray-700">{endYear}</span>
      </div>
      <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
        <div className={`h-full ${colorClasses[color]} rounded-full`} style={{ width: '100%' }}></div>
      </div>
    </div>
  );
}
