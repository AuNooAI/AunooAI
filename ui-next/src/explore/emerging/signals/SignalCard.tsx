import { Chip, Meter } from '@aunoo/ui';
import type { EmergingTopic } from './types';
import { CATEGORY_LABELS, deriveCategory, scoreOf, scoreTone, URGENCY, VELOCITY } from './utils';
import './signals.css';

/*
 * One theme as a card, as the old SignalCard: category, urgency, name, key takeaway, the overall
 * score as a bar, velocity and how many runs in a row found it. The edge colour follows urgency.
 */

interface SignalCardProps {
  topic: EmergingTopic;
  isSelected: boolean;
  onClick: () => void;
}

export function SignalCard({ topic, isSelected, onClick }: SignalCardProps) {
  const urgency = topic.synthesis?.urgency ?? 'low';
  const u = URGENCY[urgency] ?? URGENCY.low;
  const v = VELOCITY[topic.velocity ?? 'stable'] ?? VELOCITY.stable;
  const score = Math.round(scoreOf(topic));
  const ts = topic.trend_score;
  const breakdown = ts
    ? `Volume ${Math.round(ts.volume)}, velocity ${Math.round(ts.velocity)}, diversity ${Math.round(ts.diversity)}, novelty ${Math.round(ts.novelty)}`
    : 'Overall trend score';
  return (
    <button type="button" className={`sig-card sig-card--${urgency}`} aria-pressed={isSelected} onClick={onClick}>
      <span className="sig-card__top">
        {/* The category comes from the topic that was scanned; a scan across all topics has none */}
        <span className="sig-eyebrow">{topic.topic_filter ? CATEGORY_LABELS[deriveCategory(topic.topic_filter)] : ''}</span>
        <Chip tone={u.tone} size="sm">{u.label}</Chip>
      </span>
      <span className="sig-card__name">{topic.name}</span>
      {topic.synthesis?.key_takeaway && <span className="sig-card__takeaway">{topic.synthesis.key_takeaway}</span>}
      <Meter label={`Score ${score}`} value={score} max={100} tone={scoreTone(score)} valueText={`${score} out of 100. ${breakdown}`} hideValue />
      <span className="sig-card__foot">
        <span className="sig-small" title={breakdown}>Score {score}</span>
        <Chip tone={v.tone} size="sm">{v.label}</Chip>
        {(topic.consecutive_detections ?? 0) > 1 && <span className="sig-small">{topic.consecutive_detections} runs in a row</span>}
      </span>
    </button>
  );
}
