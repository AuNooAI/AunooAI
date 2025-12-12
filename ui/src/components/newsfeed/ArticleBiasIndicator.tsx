/**
 * Article Bias and Factuality Indicator
 * Shows visual badges for bias rating and factuality
 */

interface ArticleBiasIndicatorProps {
  bias?: string;
  factuality?: string;
  size?: 'sm' | 'md';
  showLabels?: boolean;
}

const biasColors: Record<string, { bg: string; text: string; label: string }> = {
  'left': { bg: 'bg-blue-100', text: 'text-blue-700', label: 'Left' },
  'left-center': { bg: 'bg-blue-50', text: 'text-blue-600', label: 'Left-Center' },
  'center': { bg: 'bg-gray-100', text: 'text-gray-700', label: 'Center' },
  'right-center': { bg: 'bg-red-50', text: 'text-red-600', label: 'Right-Center' },
  'right': { bg: 'bg-red-100', text: 'text-red-700', label: 'Right' },
  'mixed': { bg: 'bg-purple-100', text: 'text-purple-700', label: 'Mixed' },
};

const factualityColors: Record<string, { bg: string; text: string; label: string }> = {
  'very high': { bg: 'bg-green-100', text: 'text-green-700', label: 'Very High' },
  'high': { bg: 'bg-green-50', text: 'text-green-600', label: 'High' },
  'mostly factual': { bg: 'bg-yellow-50', text: 'text-yellow-700', label: 'Mostly Factual' },
  'mixed': { bg: 'bg-orange-100', text: 'text-orange-700', label: 'Mixed' },
  'low': { bg: 'bg-red-100', text: 'text-red-600', label: 'Low' },
  'very low': { bg: 'bg-red-200', text: 'text-red-800', label: 'Very Low' },
};

/**
 * Normalize bias value to match our keys
 */
function normalizeBias(bias: string): string | null {
  if (!bias) return null;
  const lower = bias.toLowerCase().trim();
  // Handle variations like "left-center bias", "left center", etc.
  const normalized = lower
    .replace(' bias', '')
    .replace('least biased', 'center')
    .replace('pro-science', 'center')
    .trim();

  // Check if it matches a key
  if (biasColors[normalized]) return normalized;

  // Try with hyphen variations
  const withHyphen = normalized.replace(' ', '-');
  if (biasColors[withHyphen]) return withHyphen;

  const withoutHyphen = normalized.replace('-', ' ');
  if (biasColors[withoutHyphen]) return withoutHyphen;

  return null;
}

/**
 * Normalize factuality value to match our keys
 */
function normalizeFactuality(factuality: string): string | null {
  if (!factuality) return null;
  const lower = factuality.toLowerCase().trim();

  // Check if it matches a key directly
  if (factualityColors[lower]) return lower;

  // Handle hyphenated versions
  const withSpaces = lower.replace(/-/g, ' ');
  if (factualityColors[withSpaces]) return withSpaces;

  return null;
}

export function ArticleBiasIndicator({
  bias,
  factuality,
  size = 'sm',
  showLabels = false
}: ArticleBiasIndicatorProps) {
  const sizeClasses = size === 'sm' ? 'text-xs px-1.5 py-0.5' : 'text-sm px-2 py-1';

  const normalizedBias = bias ? normalizeBias(bias) : null;
  const normalizedFactuality = factuality ? normalizeFactuality(factuality) : null;

  if (!normalizedBias && !normalizedFactuality) {
    return null;
  }

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {normalizedBias && biasColors[normalizedBias] && (
        <span
          className={`${biasColors[normalizedBias].bg} ${biasColors[normalizedBias].text} ${sizeClasses} rounded font-medium`}
          title={`Political Bias: ${biasColors[normalizedBias].label}`}
        >
          {showLabels ? biasColors[normalizedBias].label : normalizedBias.charAt(0).toUpperCase()}
        </span>
      )}
      {normalizedFactuality && factualityColors[normalizedFactuality] && (
        <span
          className={`${factualityColors[normalizedFactuality].bg} ${factualityColors[normalizedFactuality].text} ${sizeClasses} rounded font-medium`}
          title={`Factuality: ${factualityColors[normalizedFactuality].label}`}
        >
          {showLabels ? factualityColors[normalizedFactuality].label : (
            normalizedFactuality === 'very high' ? 'VH' :
            normalizedFactuality === 'high' ? 'H' :
            normalizedFactuality === 'mostly factual' ? 'MF' :
            normalizedFactuality === 'mixed' ? 'M' :
            normalizedFactuality === 'low' ? 'L' : 'VL'
          )}
        </span>
      )}
    </div>
  );
}
