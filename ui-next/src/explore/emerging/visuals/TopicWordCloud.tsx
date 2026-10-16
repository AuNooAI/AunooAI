import { useMemo } from 'react';
import './visuals.css';

/*
 * A theme's keywords, entities and themes as a word cloud, as the old TopicWordCloud. Size follows
 * the order the analysis listed them in (first = most prominent); colour says which kind of word it
 * is. The old cloud shuffled the words at random on each render; this one keeps them in order.
 */

interface TopicWordCloudProps {
  keywords?: string[];
  entities?: string[];
  themes?: string[];
  maxWords?: number;
  className?: string;
}

type Kind = 'keyword' | 'entity' | 'theme';
interface Word { text: string; weight: number; kind: Kind }

const bucket = (w: number) => (w >= 90 ? 5 : w >= 75 ? 4 : w >= 55 ? 3 : w >= 35 ? 2 : 1);

export function TopicWordCloud({ keywords = [], entities = [], themes = [], maxWords = 20, className }: TopicWordCloudProps) {
  const words = useMemo(() => {
    const all: Word[] = [
      ...keywords.map((text, i) => ({ text, weight: 100 - i * 8, kind: 'keyword' as const })),
      ...entities.map((text, i) => ({ text, weight: 90 - i * 6, kind: 'entity' as const })),
      ...themes.map((text, i) => ({ text, weight: 80 - i * 5, kind: 'theme' as const })),
    ].filter((w) => w.text);
    return all.sort((a, b) => b.weight - a.weight).slice(0, maxWords);
  }, [keywords, entities, themes, maxWords]);

  if (!words.length) return null;
  const kinds = new Set(words.map((w) => w.kind));
  return (
    <div className={className}>
      <ul className="et-cloud" aria-label="Keywords, entities and themes">
        {words.map((w, i) => (
          <li key={`${w.kind}-${w.text}-${i}`} className={`et-cloud__word et-cloud__word--${w.kind} et-cloud__w${bucket(w.weight)}`}>
            {w.text}
          </li>
        ))}
      </ul>
      <div className="et-legend">
        {kinds.has('keyword') && <span className="et-legend__item"><span className="et-dot et-dot--keyword" />Keywords</span>}
        {kinds.has('entity') && <span className="et-legend__item"><span className="et-dot et-dot--entity" />Entities</span>}
        {kinds.has('theme') && <span className="et-legend__item"><span className="et-dot et-dot--theme" />Themes</span>}
      </div>
    </div>
  );
}

/** Compact version: keywords and entities only, no legend */
export function TopicWordCloudCompact({ keywords = [], entities = [], maxWords = 10, className }: Omit<TopicWordCloudProps, 'themes'>) {
  return <TopicWordCloud keywords={keywords} entities={entities} maxWords={maxWords} className={className} />;
}

export default TopicWordCloud;
