import { Panel, Stack, Text } from '@aunoo/ui';
import type { EmergingTopic } from './types';
import './signals.css';

/*
 * Key actors and things to watch for, as the old WatchPanel. Actors come from accelerating or
 * high-urgency themes (two per theme, six at most); "watch for" items come from high-urgency themes
 * (two per theme, six at most). Each row opens its theme.
 */

interface WatchPanelProps {
  topics: EmergingTopic[];
  onSelectTopic: (topic: EmergingTopic) => void;
}

export function WatchPanel({ topics, onSelectTopic }: WatchPanelProps) {
  const watchFor = topics
    .filter((t) => t.synthesis?.urgency === 'high')
    .flatMap((t) => (t.signals?.watch_for ?? []).slice(0, 2).map((text) => ({ text, topic: t })))
    .slice(0, 6);
  const actors: { name: string; topic: EmergingTopic }[] = [];
  for (const t of topics.filter((x) => x.velocity === 'accelerating' || x.synthesis?.urgency === 'high')) {
    for (const name of [...(t.actors?.companies ?? []), ...(t.actors?.people ?? [])].slice(0, 2)) {
      if (actors.length < 6) actors.push({ name, topic: t });
    }
    if (actors.length >= 6) break;
  }
  return (
    <Panel title="Key actors and what to watch" headingLevel={3}>
      <Stack gap="md">
        <Stack gap="sm">
          <Text variant="label">Key actors in play</Text>
          {actors.length === 0 ? <Text variant="caption">No actors named in the accelerating or high-urgency themes.</Text> : (
            <ul className="sig-list">
              {actors.map(({ name, topic }, i) => (
                <li key={`${name}-${i}`}>
                  <button type="button" className="sig-row" onClick={() => onSelectTopic(topic)}>
                    <span className="sig-row__text">{name}</span>
                    <span className="sig-row__meta" title={topic.name}>{topic.name}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Stack>
        <Stack gap="sm">
          <Text variant="label">Watch for</Text>
          {watchFor.length === 0 ? <Text variant="caption">No watch items in the high-urgency themes.</Text> : (
            <ul className="sig-list">
              {watchFor.map(({ text, topic }, i) => (
                <li key={i}>
                  <button type="button" className="sig-row" onClick={() => onSelectTopic(topic)} title={topic.name}>
                    <span className="sig-row__text">{text}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Stack>
      </Stack>
    </Panel>
  );
}
