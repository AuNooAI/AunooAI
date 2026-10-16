import { Button, Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, Grid, Icon, IconButton, Menu, Panel, Skeleton, Stack, Stat, Text } from '@aunoo/ui';
import { MomentumGauge, TopicScoreRadar, TopicSparkline, TopicWordCloud, TrajectoryTimeline } from '../visuals';
import {
  asStrings, parseTimelineItem, SCENARIO_LABEL, scoreOf, text, typeOf, URGENCY_LABEL,
  type EmergingTopic, type HistoryPoint, type TopicDetail, type TrendScore,
} from './types';
import './tab.css';

/* One trending theme as a card, with its analysis folded away until opened (old EmergingTopicsTab card view). */

interface Props {
  t: EmergingTopic;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  detail?: TopicDetail;
  history?: HistoryPoint[];
  tracked: boolean;
  horizonsBusy: boolean;
  onTrack: () => void;
  onAuspex: () => void;
  onHorizons: () => void;
  onRetire: () => void;
  onDelete: () => void;
  /** Adds the theme to a Briefing Desk briefing */
  onAddToBriefing?: () => void;
  /** Opens share by email for this theme */
  onShare?: () => void;
  onArticle: (uri: string, title?: string) => void;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Stack gap="sm">
      <Text variant="label">{title}</Text>
      {children}
    </Stack>
  );
}

function Labelled({ items }: { items: [string, unknown][] }) {
  const rows = items.filter(([, v]) => text(v));
  if (!rows.length) return null;
  return (
    <Grid columns={rows.length > 2 ? 3 : 2} stackAt="small">
      {rows.map(([k, v]) => (
        <Stack key={k} gap="sm">
          <Text variant="label">{k}</Text>
          <Text variant="caption">{text(v)}</Text>
        </Stack>
      ))}
    </Grid>
  );
}

function TrendScoreBlock({ s }: { s: TrendScore }) {
  return (
    <Section title="Trend score">
      <Stack direction="row" gap="md">
        <TopicScoreRadar trendScore={s as Parameters<typeof TopicScoreRadar>[0]['trendScore']} size={160} />
        <Grid columns={3} stackAt="never" gap="sm">
          {([['Volume', s.volume], ['Velocity', s.velocity], ['Diversity', s.diversity], ['Novelty', s.novelty], ['Overall', s.composite]] as const).map(([k, v]) => (
            <Stat key={k} size="compact" label={k} value={Math.round(v ?? 0)} tone={v >= 70 ? 'success' : v >= 40 ? 'warning' : 'default'} />
          ))}
        </Grid>
      </Stack>
      <Text variant="caption">Volume is how many articles, velocity how fast they are arriving, diversity how many different sources, novelty how unlike earlier coverage. Each runs 0 to 100.</Text>
    </Section>
  );
}

export function TopicCard(p: Props) {
  const { t, detail } = p;
  const type = typeOf(t.detection_type);
  const urgency = t.synthesis?.urgency;
  const timeline = (t.events?.timeline ?? []).map(parseTimelineItem);
  const growth = asStrings(t.signals?.growth_indicators), risks = asStrings(t.signals?.risk_factors), watch = asStrings(t.signals?.watch_for);
  const actors = t.actors;
  const scenarios = t.future_horizons?.scenarios ?? [];

  return (
    <div id={`topic-${t.id}`} className="et-card">
      <Panel
        title={t.topic_label}
        headingLevel={3}
        description={t.topic_description}
        headerAside={
          <Stack direction="row" gap="sm" wrap={false}>
            <IconButton icon={<Icon name="Folder" size="sm" />} label={`Retire “${t.topic_label}” (archive it)`} onClick={p.onRetire} />
            <Menu
              label={`Actions for ${t.topic_label}`}
              align="end"
              trigger={<IconButton icon={<Icon name="DotsThreeOutlineVertical" size="sm" />} label={`More actions for ${t.topic_label}`} />}
              items={[
                { id: 'track', label: p.tracked ? 'Saved: stop tracking' : 'Save (track this theme)', icon: 'BookmarkSimple' },
                { id: 'auspex', label: 'Ask Auspex', icon: 'ChatCentered' },
                { id: 'horizons', label: 'Future Horizons (AI)', icon: 'Sparkle', disabled: p.horizonsBusy },
                ...(p.onAddToBriefing ? [{ id: 'briefing', label: 'Add to a briefing', icon: 'Notebook' as const }] : []),
                ...(p.onShare ? [{ id: 'share', label: 'Share by email', icon: 'ShareNetwork' as const }] : []),
                { id: 'delete', label: 'Delete permanently', icon: 'Trash', tone: 'danger', separatorBefore: true },
              ]}
              onSelect={(id) => {
                if (id === 'track') p.onTrack();
                else if (id === 'auspex') p.onAuspex();
                else if (id === 'horizons') p.onHorizons();
                else if (id === 'briefing') p.onAddToBriefing?.();
                else if (id === 'share') p.onShare?.();
                else if (id === 'delete') p.onDelete();
              }}
            />
          </Stack>
        }
      >
        <Stack gap="md">
          <Stack direction="row" gap="sm">
            <Chip size="sm" tone={type.tone}>{type.label}</Chip>
            {urgency && <Chip size="sm" tone={URGENCY_LABEL[urgency]?.tone ?? 'neutral'}>{URGENCY_LABEL[urgency]?.label ?? urgency}</Chip>}
            {(t.detection_count ?? 1) > 1 && <Chip size="sm" tone="muted" icon={<Icon name="Clock" size="sm" />}>{`Detected ${t.detection_count} times`}</Chip>}
            {t.trajectory && <Chip size="sm" tone={t.trajectory === 'rising' ? 'success' : t.trajectory === 'declining' ? 'error' : 'muted'}>{t.trajectory}</Chip>}
            {p.tracked && <Chip size="sm" tone="accent" icon={<Icon name="BookmarkSimple" size="sm" />}>Saved</Chip>}
          </Stack>

          <Stack direction="row" justify="between" gap="md">
            <Stack direction="row" gap="md">
              <Stat size="compact" label="Articles" value={t.article_count} />
              {t.trend_score && <Stat size="compact" label="Score" value={Math.round(scoreOf(t))} tone={scoreOf(t) >= 70 ? 'success' : scoreOf(t) >= 40 ? 'warning' : 'default'} />}
            </Stack>
            <Stack direction="row" gap="sm">
              <MomentumGauge velocity={t.velocity} velocityScore={t.trend_score?.velocity} size="sm" />
              {(p.history?.length ?? 0) > 1 && (
                <TopicSparkline history={p.history as Parameters<typeof TopicSparkline>[0]['history']} width={60} height={20} showTrend={false} />
              )}
            </Stack>
          </Stack>

          {t.first_detection_date && (t.detection_count ?? 1) > 1 && (
            <TrajectoryTimeline
              firstDetection={t.first_detection_date}
              lastDetection={t.last_detection_date || t.detection_date}
              detectionCount={t.detection_count || 1}
              consecutiveDetections={t.consecutive_detections || 1}
              missedRuns={t.missed_runs || 0}
              trajectory={t.trajectory || 'stable'}
            />
          )}

          {!!t.key_entities?.length && (
            <Stack direction="row" gap="sm">
              {t.key_entities.slice(0, 5).map((e) => <Chip key={e} size="sm" tone="neutral" variant="outline">{e}</Chip>)}
            </Stack>
          )}

          <Collapsible open={p.open} onOpenChange={p.onOpenChange}>
            <CollapsibleTrigger variant="ghost" size="sm">{p.open ? 'Hide the analysis' : 'Show the analysis'}</CollapsibleTrigger>
            <CollapsibleContent>
              <Stack gap="lg">
                {text(t.why_emerging) && <Section title="Why it is emerging"><Text>{t.why_emerging}</Text></Section>}
                {text(t.synthesis?.key_takeaway) && <Section title="Key takeaway"><Text>{t.synthesis!.key_takeaway}</Text></Section>}
                {t.trend_score && <TrendScoreBlock s={t.trend_score} />}

                {(!!t.representative_keywords?.length || !!t.key_entities?.length) && (
                  <Section title="Key terms">
                    <TopicWordCloud keywords={t.representative_keywords || []} entities={t.key_entities || []} themes={t.key_themes || []} maxWords={15} />
                  </Section>
                )}

                {(actors?.companies?.length || actors?.people?.length || actors?.organizations?.length) ? (
                  <Section title="Key actors">
                    <Stack direction="row" gap="sm">
                      {actors?.companies?.map((c) => <Chip key={`c${c}`} size="sm" tone="info" icon={<Icon name="Buildings" size="sm" />}>{c}</Chip>)}
                      {actors?.people?.map((c) => <Chip key={`p${c}`} size="sm" tone="success" icon={<Icon name="User" size="sm" />}>{c}</Chip>)}
                      {actors?.organizations?.map((c) => <Chip key={`o${c}`} size="sm" tone="accent" icon={<Icon name="Scales" size="sm" />}>{c}</Chip>)}
                    </Stack>
                  </Section>
                ) : null}

                {(text(t.events?.trigger_event) || timeline.length > 0 || text(t.events?.current_status)) && (
                  <Section title="Events">
                    <ol className="et-timeline">
                      {text(t.events?.trigger_event) && (
                        <li data-kind="trigger"><Text variant="label">Trigger</Text><Text variant="caption">{t.events!.trigger_event}</Text></li>
                      )}
                      {timeline.map((it, i) => (
                        <li key={i}>{it.date && <Text variant="label">{it.date}</Text>}<Text variant="caption">{it.event}</Text></li>
                      ))}
                      {text(t.events?.current_status) && (
                        <li data-kind="now"><Text variant="label">Current status</Text><Text variant="caption">{t.events!.current_status}</Text></li>
                      )}
                    </ol>
                  </Section>
                )}

                {(growth.length || risks.length || watch.length) ? (
                  <Section title="Signals">
                    <Grid columns={3} stackAt="small">
                      {([['Growth', growth], ['Risks', risks], ['Watch for', watch]] as const).filter(([, l]) => l.length).map(([k, l]) => (
                        <Stack key={k} gap="sm">
                          <Text variant="label">{k}</Text>
                          <ul className="et-list">{l.slice(0, 2).map((x, i) => <li key={i}><Text as="span" variant="caption">{x}</Text></li>)}</ul>
                        </Stack>
                      ))}
                    </Grid>
                  </Section>
                ) : null}

                {t.implications && (text(t.implications.industry_impact) || text(t.implications.regulatory) || text(t.implications.market)) && (
                  <Section title="Implications">
                    <Labelled items={[['Industry', t.implications.industry_impact], ['Regulatory', t.implications.regulatory], ['Market', t.implications.market]]} />
                  </Section>
                )}

                {t.organization_implications && (
                  <Section title="What it means for the organisation">
                    <Labelled items={[
                      ['Strategic relevance', t.organization_implications.strategic_relevance],
                      ['Stakeholder impact', t.organization_implications.stakeholder_impact],
                      ['Risk assessment', t.organization_implications.risk_assessment],
                      ['Recommended response', t.organization_implications.recommended_response],
                    ]} />
                  </Section>
                )}

                {scenarios.length > 0 && (
                  <Section title="Future Horizons (saved)">
                    <Stack as="ul" gap="sm" label="Saved scenarios">
                      {scenarios.map((s, i) => (
                        <li key={i}>
                          <Stack gap="sm">
                            <Stack direction="row" gap="sm"><Chip size="sm" tone={SCENARIO_LABEL[s.type ?? '']?.tone ?? 'neutral'}>{SCENARIO_LABEL[s.type ?? '']?.label ?? s.type ?? 'Scenario'}</Chip><Text variant="label">{s.title}</Text></Stack>
                            <Text variant="caption">{s.description}</Text>
                          </Stack>
                        </li>
                      ))}
                    </Stack>
                  </Section>
                )}

                <Stack direction="row" gap="sm">
                  <Button variant="secondary" size="sm" iconStart={<Icon name="ChatCentered" size="sm" />} onClick={p.onAuspex}>Ask Auspex</Button>
                  <Button variant="secondary" size="sm" iconStart={<Icon name="Sparkle" size="sm" />} disabled={p.horizonsBusy} onClick={p.onHorizons}>
                    {p.horizonsBusy ? 'Projecting…' : 'Future Horizons'}
                  </Button>
                </Stack>

                {detail?.error ? (
                  <Text variant="caption">The sample articles didn’t load: {detail.error}</Text>
                ) : !detail ? (
                  <Skeleton variant="text" lines={3} />
                ) : !!detail.articles?.length && (
                  <Section title={`Sample articles${detail.model_used ? ` · analysed with ${detail.model_used}` : ''}`}>
                    <Stack as="ul" gap="sm" label="Sample articles">
                      {detail.articles.slice(0, 5).map((a) => (
                        <li key={a.uri}>
                          <Stack gap="sm">
                            <a
                              className="text-link"
                              href={a.uri}
                              onClick={(e) => { if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey) return; e.preventDefault(); p.onArticle(a.uri, a.title); }}
                            >
                              {a.title || a.uri}
                            </a>
                            <Text variant="caption">
                              {[a.news_source, a.publication_date, (a.novelty_score ?? 0) > 0 ? `${Math.round(a.novelty_score!)} novelty` : null, a.knn_distance_score != null ? `${a.knn_distance_score.toFixed(2)} distance from earlier coverage` : null].filter(Boolean).join(' · ')}
                            </Text>
                          </Stack>
                        </li>
                      ))}
                    </Stack>
                  </Section>
                )}
              </Stack>
            </CollapsibleContent>
          </Collapsible>
        </Stack>
      </Panel>
    </div>
  );
}
