/**
 * Impact Timeline Card Component
 */

interface ImpactTimelineCardProps {
  title: string;
  description: string;
  timelineStart: number;
  timelineEnd: number;
  tooltipPositions: Array<{ year: number; label: string }>;
  color: 'orange' | 'purple' | 'green' | 'blue' | 'pink' | 'lime';
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
}: ImpactTimelineCardProps) {
  const colors = colorClasses[color];
  const totalYears = timelineEnd - timelineStart;

  return (
    <div className="grid grid-cols-[330px_1fr] gap-4 mb-4">
      {/* Left: Title and Description */}
      <div className={`${colors.bg} ${colors.text} rounded-xl p-5`}>
        <h3 className="font-bold text-base mb-2">{title}</h3>
        <p className="text-sm">{description}</p>
      </div>

      {/* Right: Timeline */}
      <div className="bg-white border border-gray-200 rounded-xl p-5 flex items-center">
        <div className="flex-1">
          {/* Year labels */}
          <div className="flex justify-between text-xs text-gray-600 mb-2 px-1">
            <span>{timelineStart}</span>
            <span>{timelineEnd}</span>
          </div>

          {/* Timeline bar with tooltips */}
          <div className="relative h-8">
            {/* Background bar */}
            <div className="absolute top-3 left-0 right-0 h-2 bg-gray-200 rounded-full"></div>

            {/* Colored progress bar */}
            <div
              className={`absolute top-3 h-2 ${colors.bar} rounded-full`}
              style={{
                left: '0%',
                width: '70%', // Default span
              }}
            ></div>

            {/* Tooltip markers */}
            {tooltipPositions.map((tooltip, idx) => {
              const position = ((tooltip.year - timelineStart) / totalYears) * 100;
              return (
                <div
                  key={idx}
                  className="absolute top-0"
                  style={{ left: `${position}%`, transform: 'translateX(-50%)' }}
                >
                  {/* Tooltip label */}
                  <div className="absolute -top-6 left-1/2 transform -translate-x-1/2 bg-gray-800 text-white text-xs px-2 py-1 rounded whitespace-nowrap">
                    {tooltip.label}
                  </div>
                  {/* Dot marker */}
                  <div className="w-2 h-2 bg-gray-800 rounded-full"></div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
