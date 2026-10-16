import { Chip, Dialog, Grid, Meter, Stack, Text } from '@aunoo/ui';
import type { EmergingTopic } from './types';
import { allActors, CATEGORY_LABELS, deriveCategory, formatDate, scoreOf, scoreTone, URGENCY, VELOCITY } from './utils';
import './signals.css';

/*
 * A theme's full reading, as the old TopicDetailPanel: what happened, implications, signals,
 * actors, the score breakdown and the detection history. Everything here was written by the AI when
 * the theme was detected; nothing is generated on opening.
 */

interface TopicDetailPanelProps {
  topic: EmergingTopic | null;
  open: boolean;
  onClose: () => void;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Stack gap="sm">
      <Text variant="label">{title}</Text>
      {children}
    </Stack>
  );
}

function Bullets({ items }: { items: string[] }) {
  return <ul className="sig-bullets">{items.map((s, i) => <li key={i}>{s}</li>)}</ul>;
}

export function TopicDetailPanel({ topic, open, onClose }: TopicDetailPanelProps) {
  if (!topic) return null;
  const urgency = topic.synthesis?.urgency ?? 'low';
  const u = URGENCY[urgency] ?? URGENCY.low;
  const v = VELOCITY[topic.velocity ?? 'stable'] ?? VELOCITY.stable;
  const score = scoreOf(topic);
  const tone = scoreTone(score);
  const actors = allActors(topic);
  const ev = topic.events;
  const imp = topic.implications;
  const sig = topic.signals;
  const ts = topic.trend_score;
  const none = <Text variant="caption">Nothing recorded.</Text>;

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      size="xl"
      title={topic.name}
      description={ev?.current_status || undefined}
    >
      <Stack gap="lg">
        <Stack direction="row" gap="sm">
          {topic.topic_filter && <Chip tone="muted" size="sm">{CATEGORY_LABELS[deriveCategory(topic.topic_filter)]}</Chip>}
          <Chip tone={u.tone} size="sm">{u.label}</Chip>
          <Chip tone={v.tone} size="sm">{v.label}</Chip>
        </Stack>

        {topic.synthesis?.key_takeaway && (
          <div className={`sig-takeaway${tone === 'neutral' ? '' : ` sig-takeaway--${tone}`}`}>
            <Text variant="label">Key takeaway</Text>
            <Text>{topic.synthesis.key_takeaway}</Text>
          </div>
        )}

        <Grid columns={3} stackAt="wide">
          <Section title="What happened">
            {ev?.trigger_event && <Text>{ev.trigger_event}</Text>}
            {(ev?.timeline ?? []).length > 0 && <Bullets items={ev!.timeline} />}
            {!ev?.trigger_event && !(ev?.timeline ?? []).length && none}
          </Section>
          <Section title="Implications">
            {imp?.industry_impact && <Text><strong>Industry:</strong> {imp.industry_impact}</Text>}
            {imp?.regulatory && <Text><strong>Regulatory:</strong> {imp.regulatory}</Text>}
            {imp?.market && <Text><strong>Market:</strong> {imp.market}</Text>}
            {!imp?.industry_impact && !imp?.regulatory && !imp?.market && none}
          </Section>
          <Section title="Signals">
            {(sig?.growth_indicators ?? []).length > 0 && <><Text variant="caption">Growth</Text><Bullets items={sig!.growth_indicators} /></>}
            {(sig?.risk_factors ?? []).length > 0 && <><Text variant="caption">Risk</Text><Bullets items={sig!.risk_factors} /></>}
            {(sig?.watch_for ?? []).length > 0 && <><Text variant="caption">Watch for</Text><Bullets items={sig!.watch_for} /></>}
            {!(sig?.growth_indicators ?? []).length && !(sig?.risk_factors ?? []).length && !(sig?.watch_for ?? []).length && none}
          </Section>
        </Grid>

        <Grid columns={3} stackAt="wide">
          <Section title="Actors">
            {actors.length ? (
              <Stack direction="row" gap="sm">{actors.slice(0, 8).map((a) => <Chip key={a} tone="neutral" variant="outline" size="sm">{a}</Chip>)}</Stack>
            ) : none}
          </Section>
          <Section title="Score breakdown">
            {ts ? (
              <Stack gap="sm">
                {([['Volume', ts.volume], ['Velocity', ts.velocity], ['Diversity', ts.diversity], ['Novelty', ts.novelty]] as [string, number][]).map(([label, val]) => (
                  <Meter key={label} label={label} value={Math.round(val)} max={100} tone={scoreTone(val)} valueText={`${Math.round(val)} out of 100`} />
                ))}
              </Stack>
            ) : <Text variant="caption">No score breakdown recorded.</Text>}
          </Section>
          <Section title="Detection history">
            <dl className="sig-meta">
              <dt>First detected</dt><dd>{formatDate(topic.first_detection_date)}</dd>
              <dt>Last detected</dt><dd>{formatDate(topic.last_detection_date)}</dd>
              <dt>Times detected</dt><dd>{topic.detection_count ?? '—'}</dd>
              <dt>Runs in a row</dt><dd>{topic.consecutive_detections ?? '—'}</dd>
              <dt>Runs missed</dt><dd>{topic.missed_runs ?? '—'}</dd>
              <dt>Articles</dt><dd>{topic.article_count ?? '—'}</dd>
            </dl>
          </Section>
        </Grid>
      </Stack>
    </Dialog>
  );
}
