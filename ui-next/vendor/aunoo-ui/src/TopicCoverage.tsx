import { Collapsible, CollapsibleContent, CollapsibleTrigger } from './Collapsible';
import { Eyebrow } from './Eyebrow';
import { Text } from './Text';
import { TopicPill } from './TopicPill';
import './TopicCoverage.css';

export interface TopicCoverageChosenTopic {
  name: string;
  priceTag?: string;
}

export interface TopicCoverageProps {
  label?: string;
  /** Topics in the key: names, or `{ name, priceTag }` to mark the paid ones. */
  chosen?: Array<string | TopicCoverageChosenTopic>;
  /** Topic names not yet in the key. */
  available?: string[];
  /** How many available topics show before the fold. */
  previewCount?: number;
  /** Tag on available pills when adding one would cost extra, e.g. "$3/mo". */
  nextTopicPrice?: string;
  /** Bold cost, e.g. "+$6/month". */
  cost?: React.ReactNode;
  /** e.g. "3 free · 2 extra topics at $3 each" or "2 of 3 free topics used". */
  costNote?: React.ReactNode;
  emptyNote?: React.ReactNode;
  allChosenNote?: React.ReactNode;
  foldLabel?: string;
  open?: boolean;
  defaultOpen?: boolean;
  /** `(open) => void` */
  onOpenChange?: (open: boolean) => void;
  /** `(name, nextSelected) => void` */
  onToggleTopic?: (name: string, nextSelected: boolean) => void;
  className?: string;
}

/**
 * "What your key covers → Topics": the chosen topics (click to remove), a cost line,
 * a preview of available topics (click to add) and the rest behind a fold.
 */
export function TopicCoverage({
  label = 'Topics',
  chosen = [],
  available = [],
  previewCount = 6,
  nextTopicPrice,
  cost,
  costNote,
  emptyNote = 'No topics yet — pick one to scope your key.',
  allChosenNote = 'Every topic is already in your key.',
  foldLabel = 'Manage topics',
  open,
  defaultOpen,
  onOpenChange,
  onToggleTopic,
  className,
}: TopicCoverageProps) {
  const preview = available.slice(0, previewCount);
  const rest = available.slice(previewCount);
  const pills = (names: Array<string | TopicCoverageChosenTopic>, selected: boolean) =>
    names.map((t) => {
      const name = typeof t === 'string' ? t : t.name;
      const priceTag = typeof t === 'string' ? (selected ? undefined : nextTopicPrice) : t.priceTag;
      return (
        <TopicPill
          key={name}
          label={name}
          selected={selected}
          priceTag={priceTag}
          surface="raised"
          onToggle={(next) => onToggleTopic?.(name, next)}
        />
      );
    });

  return (
    <Collapsible open={open} defaultOpen={defaultOpen} onOpenChange={onOpenChange} className={['topic-coverage', className].filter(Boolean).join(' ')}>
      <div className="topic-coverage__head">
        <Eyebrow as="h3">{label}</Eyebrow>
        {rest.length > 0 && <CollapsibleTrigger variant="onSurface">{foldLabel}</CollapsibleTrigger>}
      </div>

      {chosen.length > 0 ? (
        <>
          <div className="topic-coverage__pills" role="group" aria-label="Topics in your key">{pills(chosen, true)}</div>
          {(cost || costNote) && (
            <div className="topic-coverage__foot">
              {cost && <span className="topic-coverage__cost">{cost}</span>}
              {costNote && <Text as="span" variant="hint">{costNote}</Text>}
            </div>
          )}
        </>
      ) : (
        <Text variant="hint">{emptyNote}</Text>
      )}

      {available.length > 0 ? (
        <>
          <Eyebrow as="h4" className="topic-coverage__available-label">Available</Eyebrow>
          <div className="topic-coverage__pills" role="group" aria-label="Available topics">{pills(preview, false)}</div>
          {rest.length > 0 && (
            <CollapsibleContent>
              <div className="topic-coverage__pills topic-coverage__fold" role="group" aria-label="More available topics">
                {pills(rest, false)}
              </div>
            </CollapsibleContent>
          )}
        </>
      ) : (
        <Text variant="hint" className="topic-coverage__all">{allChosenNote}</Text>
      )}
    </Collapsible>
  );
}
