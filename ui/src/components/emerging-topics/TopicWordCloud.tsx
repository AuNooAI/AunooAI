/**
 * TopicWordCloud - CSS-based word cloud for keywords and entities
 * Displays keywords with variable font sizes based on prominence
 */

import { useMemo } from 'react';

interface TopicWordCloudProps {
  keywords?: string[];
  entities?: string[];
  themes?: string[];
  maxWords?: number;
  className?: string;
}

interface WordItem {
  text: string;
  weight: number;
  type: 'keyword' | 'entity' | 'theme';
}

// Color palette for different word types
const typeColors = {
  keyword: 'text-blue-600 dark:text-blue-400',
  entity: 'text-purple-600 dark:text-purple-400',
  theme: 'text-emerald-600 dark:text-emerald-400',
};

export function TopicWordCloud({
  keywords = [],
  entities = [],
  themes = [],
  maxWords = 20,
  className = '',
}: TopicWordCloudProps) {
  const words = useMemo(() => {
    const allWords: WordItem[] = [];

    // Add keywords with decreasing weight
    keywords.forEach((word, i) => {
      allWords.push({
        text: word,
        weight: 100 - (i * 8), // First keyword = 100, decreases
        type: 'keyword',
      });
    });

    // Add entities with slightly lower base weight
    entities.forEach((word, i) => {
      allWords.push({
        text: word,
        weight: 90 - (i * 6),
        type: 'entity',
      });
    });

    // Add themes with moderate weight
    themes.forEach((word, i) => {
      allWords.push({
        text: word,
        weight: 80 - (i * 5),
        type: 'theme',
      });
    });

    // Sort by weight and limit
    return allWords
      .sort((a, b) => b.weight - a.weight)
      .slice(0, maxWords)
      // Shuffle for visual variety (but keep larger words prominent)
      .sort(() => Math.random() - 0.5);
  }, [keywords, entities, themes, maxWords]);

  if (words.length === 0) {
    return null;
  }

  // Calculate font size based on weight (min 11px, max 24px)
  const getFontSize = (weight: number) => {
    const minSize = 11;
    const maxSize = 24;
    const normalized = Math.max(0, Math.min(100, weight)) / 100;
    return Math.round(minSize + (maxSize - minSize) * normalized);
  };

  // Get opacity based on weight
  const getOpacity = (weight: number) => {
    const minOpacity = 0.6;
    const maxOpacity = 1;
    const normalized = Math.max(0, Math.min(100, weight)) / 100;
    return minOpacity + (maxOpacity - minOpacity) * normalized;
  };

  return (
    <div className={`${className}`}>
      <div className="flex flex-wrap gap-x-3 gap-y-2 items-center justify-center p-3 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
        {words.map((word, index) => (
          <span
            key={`${word.text}-${index}`}
            className={`
              font-medium transition-all duration-200 cursor-default
              hover:scale-110 hover:opacity-100
              ${typeColors[word.type]}
            `}
            style={{
              fontSize: `${getFontSize(word.weight)}px`,
              opacity: getOpacity(word.weight),
            }}
            title={`${word.type}: ${word.text}`}
          >
            {word.text}
          </span>
        ))}
      </div>
      {/* Legend */}
      <div className="flex items-center justify-center gap-4 mt-2 text-xs text-gray-500 dark:text-gray-400">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-blue-500"></span>
          Keywords
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-purple-500"></span>
          Entities
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
          Themes
        </span>
      </div>
    </div>
  );
}

/**
 * Compact version without legend
 */
export function TopicWordCloudCompact({
  keywords = [],
  entities = [],
  maxWords = 10,
  className = '',
}: Omit<TopicWordCloudProps, 'themes'>) {
  const words = useMemo(() => {
    const allWords: WordItem[] = [];

    keywords.forEach((word, i) => {
      allWords.push({ text: word, weight: 100 - (i * 10), type: 'keyword' });
    });

    entities.forEach((word, i) => {
      allWords.push({ text: word, weight: 85 - (i * 8), type: 'entity' });
    });

    return allWords
      .sort((a, b) => b.weight - a.weight)
      .slice(0, maxWords);
  }, [keywords, entities, maxWords]);

  if (words.length === 0) return null;

  return (
    <div className={`flex flex-wrap gap-1.5 ${className}`}>
      {words.map((word, index) => (
        <span
          key={`${word.text}-${index}`}
          className={`
            text-xs font-medium px-1.5 py-0.5 rounded
            ${word.type === 'keyword'
              ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
              : 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400'
            }
          `}
        >
          {word.text}
        </span>
      ))}
    </div>
  );
}

export default TopicWordCloud;
