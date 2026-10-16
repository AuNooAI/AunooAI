import { Button, Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, Dialog, DialogClose, EmptyState, Icon, IconButton, Meter, Panel, Skeleton, Stack, Table, Text } from '@aunoo/ui';
import { formatElapsed, SCENARIO_LABEL, scoreOf, stepLabel, text, typeOf, URGENCY_LABEL, urgencyOf, VELOCITY_LABEL, type DetectionProgress, type EmergingTopic, type HighNoveltyArticle, type HorizonsResult } from './types';
import './tab.css';

/* The smaller pieces of the Emerging Topics tab: progress, table, retired list, high-novelty list, horizons dialog. */

/** An inline link that is really a button */
export function LinkButton({ onClick, children, label }: { onClick: () => void; children: React.ReactNode; label?: string }) {
  return <button type="button" className="text-link et-linkbutton" aria-label={label} onClick={onClick}>{children}</button>;
}

export function ProgressPanel({ p }: { p: DetectionProgress }) {
  const batch = (p.topic_total ?? 1) > 1;
  const step = stepLabel(batch ? p.topic_step : p.step);
  const facts = [
    step && `Step: ${step}`,
    p.elapsed_seconds !== undefined && `Elapsed: ${formatElapsed(p.elapsed_seconds)}`,
    p.proposed_count !== undefined && `Proposed: ${p.proposed_count}`,
    p.validated_count !== undefined && `Kept after checking: ${p.validated_count}`,
  ].filter(Boolean);
  return (
    <Panel title="Detection running" description="It runs on the server, so you can leave this page; it re-attaches when you come back.">
      <Stack gap="sm">
        <Meter label={p.message} value={Math.round(p.progress ?? 0)} max={100} progress valueText={`${Math.round(p.progress ?? 0)}%`} />
        {batch && (
          <Meter
            label={`Topic ${p.topic_index ?? '?'} of ${p.topic_total}${p.current_topic ? `: ${p.current_topic}` : ''}`}
            value={Math.round(p.topic_progress ?? 0)}
            max={100}
            progress
            valueText={`${Math.round(p.topic_progress ?? 0)}%`}
          />
        )}
        {facts.length > 0 && <Text variant="caption">{facts.join(' · ')}</Text>}
      </Stack>
    </Panel>
  );
}

export function TopicTable({ topics, onOpen, onAuspex, onRetire, onDelete }: {
  topics: EmergingTopic[];
  onOpen: (t: EmergingTopic) => void;
  onAuspex: (t: EmergingTopic) => void;
  onRetire: (t: EmergingTopic) => void;
  onDelete: (t: EmergingTopic) => void;
}) {
  const n = (v?: number) => (v != null ? Math.round(v) : '—');
  return (
    <Table
      caption="Trending themes"
      hideCaption
      rows={topics}
      rowKey={(t) => String(t.id)}
      columns={[
        {
          key: 'label', header: 'Theme', rowHeader: true, wrap: true,
          render: (t) => (
            <Stack gap="sm">
              <LinkButton onClick={() => onOpen(t)} label={`Open ${t.topic_label} as a card`}>{t.topic_label}</LinkButton>
              <Text variant="caption" truncate>{t.topic_description}</Text>
            </Stack>
          ),
        },
        { key: 'score', header: 'Score', align: 'end', render: (t) => Math.round(scoreOf(t)) },
        { key: 'vol', header: 'Volume', align: 'end', render: (t) => n(t.trend_score?.volume) },
        { key: 'div', header: 'Diversity', align: 'end', render: (t) => n(t.trend_score?.diversity) },
        { key: 'nov', header: 'Novelty', align: 'end', render: (t) => n(t.trend_score?.novelty) },
        { key: 'articles', header: 'Articles', align: 'end', render: (t) => t.article_count },
        { key: 'urgency', header: 'Urgency', render: (t) => { const u = urgencyOf(t) || 'medium'; return <Chip size="sm" tone={URGENCY_LABEL[u]?.tone ?? 'neutral'}>{URGENCY_LABEL[u]?.label ?? u}</Chip>; } },
        { key: 'velocity', header: 'Velocity', render: (t) => VELOCITY_LABEL[t.velocity]?.label ?? t.velocity },
        { key: 'type', header: 'Type', render: (t) => typeOf(t.detection_type).label },
        {
          key: 'actions', header: 'Actions',
          render: (t) => (
            <Stack direction="row" gap="sm" wrap={false}>
              <IconButton icon={<Icon name="ChatCentered" size="sm" />} label={`Ask Auspex about ${t.topic_label}`} onClick={() => onAuspex(t)} />
              <IconButton icon={<Icon name="Folder" size="sm" />} label={`Retire ${t.topic_label}`} onClick={() => onRetire(t)} />
              <IconButton icon={<Icon name="Trash" size="sm" />} tone="danger" label={`Delete ${t.topic_label}`} onClick={() => onDelete(t)} />
            </Stack>
          ),
        },
      ]}
    />
  );
}

export function RetiredSection({ open, onOpenChange, topics, loading, onRestore }: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  topics: EmergingTopic[] | null;
  loading: boolean;
  onRestore: (t: EmergingTopic) => void;
}) {
  return (
    <Collapsible open={open} onOpenChange={onOpenChange}>
      <CollapsibleTrigger variant="secondary">{`Retired themes${topics?.length ? ` (${topics.length})` : ''}`}</CollapsibleTrigger>
      <CollapsibleContent>
        {loading || !topics ? <Skeleton variant="text" lines={4} /> : topics.length === 0 ? (
          <EmptyState icon="Folder" title="No retired themes">Themes you retire appear here, and can be brought back.</EmptyState>
        ) : (
          <Stack as="ul" gap="sm" label="Retired themes">
            {topics.map((t) => (
              <li key={t.id}>
                <Panel
                  title={t.topic_label}
                  headingLevel={4}
                  description={`${t.article_count} articles${t.trend_score ? ` · score ${Math.round(t.trend_score.composite)}` : ''}`}
                  headerAside={<Button variant="secondary" size="sm" iconStart={<Icon name="ArrowClockwise" size="sm" />} onClick={() => onRestore(t)}>Restore</Button>}
                >
                  <Text variant="caption">{text(t.synthesis?.key_takeaway) ?? (t.topic_description || 'No summary available.')}</Text>
                </Panel>
              </li>
            ))}
          </Stack>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}

export function HighNovelty({ articles, onArticle }: { articles: HighNoveltyArticle[]; onArticle: (uri: string, title?: string) => void }) {
  return (
    <Panel title="High-novelty articles" description="Recent articles (last three days) that scored 70 or more for novelty during scanning: unusually unlike what came before them.">
      {articles.length === 0 ? (
        <EmptyState icon="Lightning" title="No high-novelty articles">Run a detection to score recent articles for novelty.</EmptyState>
      ) : (
        <Stack as="ul" gap="sm" label="High-novelty articles">
          {articles.map((a) => (
            <li key={a.article_uri}>
              <Stack direction="row" justify="between" gap="md" wrap={false}>
                <Stack gap="sm">
                  <a
                    className="text-link"
                    href={a.article_uri}
                    onClick={(e) => { if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey) return; e.preventDefault(); onArticle(a.article_uri, a.article_title || a.title); }}
                  >
                    {a.article_title || a.title || 'Untitled'}
                  </a>
                  <Stack direction="row" gap="sm">
                    <Text variant="caption">{a.publication_date || 'Date unknown'}</Text>
                    {a.is_outlier && <Chip size="sm" tone="warning" icon={<Icon name="Lightning" size="sm" />}>Outlier</Chip>}
                  </Stack>
                </Stack>
                <Text variant="label">{`${Math.round(a.composite_novelty_score)} novelty`}</Text>
              </Stack>
            </li>
          ))}
        </Stack>
      )}
    </Panel>
  );
}

export function HorizonsDialog({ open, onOpenChange, label, result, busy, saving, onRegenerate, onSave }: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  label: string;
  result: HorizonsResult | null;
  busy: boolean;
  saving: boolean;
  onRegenerate: () => void;
  onSave: () => void;
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      title={`Future Horizons: ${label}`}
      description="Scenarios the AI projects for this theme over the next 15 years, from probable to wild card. Not saved until you save them."
      footer={
        <>
          <DialogClose><Button variant="secondary" size="lg">Close</Button></DialogClose>
          <Button variant="secondary" size="lg" disabled={busy} onClick={onRegenerate}>{busy ? 'Projecting…' : 'Regenerate (AI)'}</Button>
          <Button size="lg" disabled={saving || !result} onClick={onSave}>{saving ? 'Saving…' : 'Save to the theme'}</Button>
        </>
      }
    >
      {!result ? <Skeleton variant="text" lines={6} /> : (
        <Stack gap="lg">
          {!!result.scenarios?.length && (
            <Stack as="ul" gap="md" label="Scenarios">
              {result.scenarios.map((s, i) => (
                <li key={i}>
                  <Stack gap="sm">
                    <Stack direction="row" gap="sm">
                      <Chip size="sm" tone={SCENARIO_LABEL[s.type ?? '']?.tone ?? 'neutral'}>{SCENARIO_LABEL[s.type ?? '']?.label ?? s.type ?? 'Scenario'}</Chip>
                      {s.timeframe && <Text as="span" variant="caption">{s.timeframe}</Text>}
                    </Stack>
                    <Text variant="label">{s.title}</Text>
                    <Text variant="caption">{s.description}</Text>
                  </Stack>
                </li>
              ))}
            </Stack>
          )}
          {!!result.key_signals?.length && (
            <Stack gap="sm">
              <Text variant="label">Signals to watch</Text>
              <ul className="et-list">{result.key_signals.map((k, i) => <li key={i}><Text as="span" variant="caption">{k}</Text></li>)}</ul>
            </Stack>
          )}
          {result.metadata?.model_used && <Text variant="caption">Written by {result.metadata.model_used}.</Text>}
        </Stack>
      )}
    </Dialog>
  );
}
