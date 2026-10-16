import { useEffect, useState } from 'react';
import {
  ActivityRow, Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, Eyebrow, Panel, SettingRow, Skeleton, Stack, StatusPill, Text,
} from '@aunoo/ui';
import { api } from '../../shell';

/*
 * What this workspace is set up to do, read from the same four routes as the old tab
 * (ui/src/components/WorkspaceOverview.tsx). Sections hide when they have nothing to show.
 * Lines in the default profile's custom_context that start with "Q:" are the questions.
 */

interface Profile {
  name: string;
  description: string | null;
  industry: string | null;
  region: string | null;
  strategic_priorities: string[];
  custom_context: string | null;
  is_default: boolean;
}

interface Topic {
  name: string;
  description: string;
  categories: string[];
  future_signals?: string[];
  languages: string[];
  providers: string[];
  active: boolean;
  collected: number;
  enriched: number;
}

interface Brand {
  id: number;
  display_name: string;
  enabled: boolean;
  is_primary?: boolean;
}

interface Report {
  id: number;
  report_name?: string;
  instruction_name?: string;
  created_at?: string;
}

const LANG_NAMES: Record<string, string> = { en: 'English', ja: 'Japanese', de: 'German', fr: 'French', es: 'Spanish', it: 'Italian' };
const num = new Intl.NumberFormat('en-GB');
const get = <T,>(url: string) => api<T>(url).catch(() => null);
const arr = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);

function TopicRows({ topics }: { topics: Topic[] }) {
  return (
    <Stack as="ul" gap="sm" label="Collected topics">
      {topics.map((t) => (
        <li key={t.name}>
          <SettingRow
            title={t.name}
            description={t.description || undefined}
            price={<Text variant="label" as="span">{num.format(t.enriched)} analysed / {num.format(t.collected)} collected</Text>}
            actions={t.active ? undefined : <StatusPill variant="muted" tone="pending">Collection paused</StatusPill>}
          >
            <Stack gap="sm">
              {t.languages.length > 0 && <Text variant="caption">Languages: {t.languages.map((l) => LANG_NAMES[l] || l).join(', ')}</Text>}
              {t.providers.length > 0 && <Text variant="caption">Sources: {t.providers.join(' · ')}</Text>}
            </Stack>
          </SettingRow>
        </li>
      ))}
    </Stack>
  );
}

/** One block per distinct taxonomy: topics share one on purpose so their results compare side by side. */
function Taxonomies({ topics }: { topics: Topic[] }) {
  const groups = new Map<string, { cats: string[]; signals: string[]; names: string[] }>();
  for (const t of topics) {
    if (!t.categories.length) continue;
    const key = JSON.stringify([t.categories, t.future_signals ?? []]);
    const g = groups.get(key) ?? { cats: t.categories, signals: t.future_signals ?? [], names: [] };
    g.names.push(t.name);
    groups.set(key, g);
  }
  if (!groups.size) return null;
  return (
    <Stack gap="sm">
      {[...groups.values()].map((g) => {
        const scope = g.names.length === topics.length && topics.length > 1 ? `Shared by all ${topics.length} topics` : g.names.length === 1 ? g.names[0] : `Shared by ${g.names.join(', ')}`;
        return (
          <Collapsible key={g.names.join('|')}>
            <SettingRow
              title={`Taxonomy: ${scope}`}
              description={`${g.cats.length} categories, ${g.signals.length} future signals`}
              actions={<CollapsibleTrigger variant="onSurface">Show</CollapsibleTrigger>}
            >
              <CollapsibleContent>
                <Stack gap="md">
                  <Stack gap="sm">
                    <Eyebrow as="h4">Categories</Eyebrow>
                    <Stack as="ul" direction="row" gap="sm" label="Categories">
                      {g.cats.map((c) => <li key={c}><Chip tone="neutral" size="sm">{c}</Chip></li>)}
                    </Stack>
                  </Stack>
                  {g.signals.length > 0 && (
                    <Stack gap="sm">
                      <Eyebrow as="h4">Future signals</Eyebrow>
                      <Stack as="ul" direction="row" gap="sm" label="Future signals">
                        {g.signals.map((s) => <li key={s}><Chip tone="info" size="sm">{s}</Chip></li>)}
                      </Stack>
                    </Stack>
                  )}
                </Stack>
              </CollapsibleContent>
            </SettingRow>
          </Collapsible>
        );
      })}
    </Stack>
  );
}

export function Overview() {
  const [data, setData] = useState<{ profile: Profile | null; topics: Topic[]; brands: Brand[]; reports: Report[] } | null>(null);

  useEffect(() => {
    void Promise.all([
      get<{ profiles?: Profile[] } | Profile[]>('/api/organizational-profiles'),
      get<{ topics?: Topic[] }>('/api/news-feed/workspace/topics-overview'),
      get<{ brands?: Brand[] } | Brand[]>('/api/brand-watcher/brands'),
      get<{ reports?: Report[] }>('/api/signal-reports?limit=10'),
    ]).then(([p, t, b, r]) => {
      const profiles = Array.isArray(p) ? p : arr<Profile>(p?.profiles);
      const brands = Array.isArray(b) ? b : arr<Brand>(b?.brands);
      setData({
        profile: profiles.find((x) => x.is_default) ?? profiles[0] ?? null,
        topics: arr<Topic>(t?.topics),
        brands: brands.filter((x) => x.enabled),
        reports: arr<Report>(r?.reports),
      });
    });
  }, []);

  if (!data) return <Skeleton variant="block" size="card" />;
  const { profile, topics, brands, reports } = data;
  const questions = (profile?.custom_context ?? '')
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l.toUpperCase().startsWith('Q:'))
    .map((l) => l.slice(2).trim());
  const streamTopics = topics.filter((t) => !t.name.startsWith('Brand Monitoring'));
  const brandTopics = topics.filter((t) => t.name.startsWith('Brand Monitoring'));
  const sortedBrands = [...brands].sort((a, b) => Number(!!b.is_primary) - Number(!!a.is_primary));

  return (
    <>
      {profile && (
        <Panel title={profile.name} description={[profile.industry, profile.region].filter(Boolean).join(' · ') || undefined}>
          <Stack gap="md">
            {profile.description && <Text variant="description">{profile.description}</Text>}
            {arr<string>(profile.strategic_priorities).length > 0 && (
              <Stack as="ul" direction="row" gap="sm" label="Strategic priorities">
                {profile.strategic_priorities.map((p) => <li key={p}><Chip tone="accent" variant="outline">{p}</Chip></li>)}
              </Stack>
            )}
          </Stack>
        </Panel>
      )}

      {questions.length > 0 && (
        <Panel title="Questions we’re answering">
          <Stack as="ul" gap="sm" label="Questions">
            {questions.map((q, i) => <li key={q}><Text>{i + 1}. {q}</Text></li>)}
          </Stack>
        </Panel>
      )}

      {streamTopics.length > 0 && (
        <Panel
          title="What we collect, and why"
          description="Each topic is a stream we collect all the time. Every article that passes the relevance check is labelled with a category from its taxonomy, plus sentiment, future signal, time to impact and driver type, so topics compare side by side."
        >
          <Stack gap="md">
            <TopicRows topics={streamTopics} />
            <Taxonomies topics={streamTopics} />
          </Stack>
        </Panel>
      )}

      {brands.length > 0 && (
        <Panel
          title="Brands being watched"
          description="Each brand has its own monitoring stream (news, and social where set up), labelled with a brand taxonomy. It feeds Brand Watcher’s perception, risk and alert views."
        >
          <Stack gap="md">
            <Stack as="ul" direction="row" gap="sm" label="Brands">
              {sortedBrands.map((b) => (
                <li key={b.id}>
                  {/* Each brand's colour, as on the old page: the same colour marks the brand in Brand Watcher's charts */}
                  <Chip
                    tone={b.is_primary ? 'accent' : 'neutral'}
                    icon={<span aria-hidden="true" style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', background: (b as { color?: string | null }).color || 'var(--viz-series-1)' }} />}
                  >
                    {b.display_name}{b.is_primary ? ' · Primary' : ''}
                  </Chip>
                </li>
              ))}
            </Stack>
            {brandTopics.length > 0 && (
              <>
                <TopicRows topics={brandTopics} />
                <Taxonomies topics={brandTopics} />
              </>
            )}
          </Stack>
        </Panel>
      )}

      <Panel title="Where reports live">
        <Stack gap="md">
          <Stack as="ul" gap="sm" label="Where reports live">
            <li><Text><strong>Consensus Analysis, Future Horizons, Strategic Recommendations, Market Signals, Impact Timeline:</strong> on the Anticipate page. Pick a topic and open the tab; the last saved analysis loads by itself.</Text></li>
            <li><Text><strong>Observer agent reports:</strong> Explore → Observer Agents, with each agent’s alerts and saved reports.</Text></li>
            <li><Text><strong>Topic Reports</strong> (long-form, per period): Anticipate → Topic Reports. If the tab is hidden, turn it on with the tab settings at the top right of Anticipate.</Text></li>
          </Stack>
          {reports.length > 0 && (
            <Stack gap="sm">
              <Eyebrow as="h3">Latest observer reports</Eyebrow>
              <Stack as="ul" gap="sm" label="Latest observer reports">
                {reports.slice(0, 5).map((r) => (
                  <ActivityRow
                    key={r.id}
                    as="li"
                    primary={r.report_name || r.instruction_name || `Report ${r.id}`}
                    timestamp={r.created_at ? String(r.created_at).slice(0, 10) : undefined}
                    dateTime={r.created_at ? String(r.created_at).slice(0, 10) : undefined}
                    dotTone="accent"
                  />
                ))}
              </Stack>
            </Stack>
          )}
        </Stack>
      </Panel>
    </>
  );
}
