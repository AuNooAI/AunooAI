import { useEffect, useMemo, useState } from 'react';
import { Banner, Button, Chip, EmptyState, Grid, Icon, Panel, SegmentedControl, Select, Skeleton, Stack, Table, Text } from '@aunoo/ui';
import { errorText } from '../../../../shell';
import { getActors, getActorThreats, type ActorThreat, type ActorType, type ThreatActor } from '../api';
import type { ThreatCtx } from '../context';
import { ACTOR_TYPES, actorTypeLabel, categoryLabel, fmtDate } from '../labels';
import { LinkButton, SeverityChip, ValueChips } from '../parts';

/*
 * The groups and people the AI named behind threats, as the old ThreatActorsTab: cards (the old page's
 * default) or a sortable table, either grouped by type or country, and the picked actor's profile with
 * its threats. The view is remembered in this browser.
 */

const VIEW_KEY = 'aunoo.threat.actorsView';
const loadView = (): 'cards' | 'table' => {
  try {
    return localStorage.getItem(VIEW_KEY) === 'table' ? 'table' : 'cards';
  } catch {
    return 'cards';
  }
};

type SortKey = 'name' | 'threat_count' | 'article_count';
type GroupBy = 'none' | 'type' | 'country';

export function Actors(ctx: ThreatCtx) {
  const [actorType, setActorType] = useState<ActorType | 'all'>('all');
  const [actors, setActors] = useState<ThreatActor[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useState<{ key: SortKey; direction: 'asc' | 'desc' }>({ key: 'threat_count', direction: 'desc' });
  const [groupBy, setGroupBy] = useState<GroupBy>('none');
  const [view, setView] = useState<'cards' | 'table'>(loadView);
  const pickView = (v: string) => {
    setView(v as 'cards' | 'table');
    try {
      localStorage.setItem(VIEW_KEY, v);
    } catch {
      // per visit only
    }
  };
  const [picked, setPicked] = useState<ThreatActor | null>(null);
  const [threats, setThreats] = useState<ActorThreat[] | null>(null);

  useEffect(() => {
    let live = true;
    setActors(null);
    setError(null);
    getActors(actorType === 'all' ? undefined : actorType).then((r) => live && setActors(r.data), (e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, [actorType]);

  useEffect(() => {
    if (!picked) return;
    let live = true;
    setThreats(null);
    getActorThreats(picked.id).then((r) => live && setThreats(r.data), () => live && setThreats([]));
    return () => {
      live = false;
    };
  }, [picked]);

  const groups = useMemo(() => {
    const sorted = [...(actors ?? [])].sort((a, b) => {
      const va = sort.key === 'name' ? a.name.toLowerCase() : a[sort.key];
      const vb = sort.key === 'name' ? b.name.toLowerCase() : b[sort.key];
      const c = va < vb ? -1 : va > vb ? 1 : 0;
      return sort.direction === 'asc' ? c : -c;
    });
    if (groupBy === 'none') return [['', sorted]] as [string, ThreatActor[]][];
    const m = new Map<string, ThreatActor[]>();
    for (const a of sorted) {
      const k = groupBy === 'type' ? actorTypeLabel(a.actor_type) : a.attributed_country_name || 'Unknown country';
      m.set(k, [...(m.get(k) ?? []), a]);
    }
    return [...m.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [actors, sort, groupBy]);

  const onSort = (key: string) => setSort((s) => (s.key === key ? { key: s.key, direction: s.direction === 'asc' ? 'desc' : 'asc' } : { key: key as SortKey, direction: 'desc' }));

  const table = (rows: ThreatActor[], caption: string) => (
    <Table
      caption={caption}
      hideCaption
      rows={rows}
      rowKey={(a) => String(a.id)}
      sort={sort}
      onSortChange={onSort}
      columns={[
        { key: 'name', header: 'Actor', rowHeader: true, sortable: true, wrap: true, render: (a) => <LinkButton onClick={() => setPicked(a)} label={`Show the profile of ${a.name}`}>{a.name}</LinkButton> },
        { key: 'actor_type', header: 'Type', render: (a) => actorTypeLabel(a.actor_type) },
        { key: 'origin', header: 'Origin', render: (a) => a.attributed_country_name || '—' },
        { key: 'threat_count', header: 'Threats', align: 'end', sortable: true },
        { key: 'article_count', header: 'Articles', align: 'end', sortable: true },
        { key: 'sophistication_level', header: 'Skill', render: (a) => a.sophistication_level || '—' },
      ]}
    />
  );

  const cards = (rows: ThreatActor[], caption: string) => (
    <ul className="threat-actor-cards" aria-label={caption}>
      {rows.map((a) => (
        <li key={a.id}>
          <button type="button" className="threat-actor-card" aria-pressed={picked?.id === a.id} onClick={() => setPicked(a)} aria-label={`Show the profile of ${a.name}`}>
            <span className="threat-actor-card__name"><Icon name="Users" size="sm" />{a.name}</span>
            <span className="threat-actor-card__chips">
              <Chip tone="neutral" size="sm">{actorTypeLabel(a.actor_type)}</Chip>
              {a.sophistication_level && <Chip tone={/advanced|expert|high/i.test(a.sophistication_level) ? 'error' : /intermediate|medium/i.test(a.sophistication_level) ? 'warning' : 'muted'} size="sm">{`Skill: ${a.sophistication_level}`}</Chip>}
            </span>
            <Text as="span" variant="caption">
              {[`${a.threat_count} threat${a.threat_count === 1 ? '' : 's'}`, `${a.article_count} article${a.article_count === 1 ? '' : 's'}`, a.attributed_country_name].filter(Boolean).join(' · ')}
            </Text>
            {a.description && <Text as="span" variant="caption">{a.description.length > 140 ? `${a.description.slice(0, 140)}…` : a.description}</Text>}
          </button>
        </li>
      ))}
    </ul>
  );

  return (
    <Grid columns="main-aside">
      <Panel
        title="Threat actors"
        description={actors ? `${actors.length} actor${actors.length === 1 ? '' : 's'}. Pick one for its profile.` : undefined}
        headerAside={
          <Stack direction="row" gap="sm">
            <SegmentedControl label="Show actors as" options={[{ value: 'cards', label: 'Cards', icon: 'SquaresFour' }, { value: 'table', label: 'Table', icon: 'Table' }]} value={view} onValueChange={pickView} />
            <Select label="Actor type" hideLabel icon="Users" options={[{ value: 'all', label: 'All types' }, ...ACTOR_TYPES.map((t) => ({ value: t, label: actorTypeLabel(t) }))]} value={actorType} onValueChange={(v) => setActorType(v as ActorType | 'all')} />
            <Select label="Group by" hideLabel icon="ListBullets" options={[{ value: 'none', label: 'No grouping' }, { value: 'type', label: 'By type' }, { value: 'country', label: 'By country' }]} value={groupBy} onValueChange={(v) => setGroupBy(v as GroupBy)} />
          </Stack>
        }
      >
        {error ? <Banner tone="error" title="Actors didn’t load" description={error} /> : !actors ? <Skeleton variant="text" lines={6} /> : !actors.length ? (
          <EmptyState icon="Users" title="No actors yet">The AI names an actor when an article attributes a threat to a group or person.</EmptyState>
        ) : (
          <Stack gap="md">
            {groups.map(([g, rows]) => (
              <Stack key={g || 'all'} gap="sm">
                {g && <Text variant="label">{`${g} (${rows.length})`}</Text>}
                {view === 'cards' ? cards(rows, g ? `Actors: ${g}` : 'Threat actors') : table(rows, g ? `Actors: ${g}` : 'Threat actors')}
              </Stack>
            ))}
          </Stack>
        )}
      </Panel>

      <Panel title={picked ? picked.name : 'Actor profile'} description={picked ? undefined : 'Pick an actor to see who they are, what they target and their threats.'}>
        {picked && (
          <Stack gap="md">
            <Stack direction="row" gap="sm">
              <Chip tone="neutral" size="sm">{actorTypeLabel(picked.actor_type)}</Chip>
              {picked.sophistication_level && <Chip tone="muted" size="sm">{`Skill: ${picked.sophistication_level}`}</Chip>}
            </Stack>
            <Text variant="caption">
              {[`${picked.threat_count} threat${picked.threat_count === 1 ? '' : 's'}`, `${picked.article_count} article${picked.article_count === 1 ? '' : 's'}`,
                picked.attributed_country_name ? `origin: ${picked.attributed_country_name}` : null, picked.motivation ? `motive: ${picked.motivation}` : null,
                picked.first_observed ? `first seen ${fmtDate(picked.first_observed)}` : null, picked.last_active ? `last active ${fmtDate(picked.last_active)}` : null].filter(Boolean).join(' · ')}
            </Text>
            {picked.description && <Text>{picked.description}</Text>}
            {!!picked.aliases?.length && <Stack gap="sm"><Text variant="label">Also known as</Text><Stack direction="row" gap="sm"><ValueChips values={picked.aliases} /></Stack></Stack>}
            {!!picked.target_industries?.length && <Stack gap="sm"><Text variant="label">Target industries</Text><Stack direction="row" gap="sm"><ValueChips values={picked.target_industries} /></Stack></Stack>}
            {!!picked.target_regions?.length && <Stack gap="sm"><Text variant="label">Target regions</Text><Stack direction="row" gap="sm"><ValueChips values={picked.target_regions} /></Stack></Stack>}
            {!!picked.known_ttps?.length && <Stack gap="sm"><Text variant="label">Techniques (MITRE ATT&CK)</Text><Stack direction="row" gap="sm"><ValueChips values={picked.known_ttps} /></Stack></Stack>}
            {!!picked.associated_malware?.length && <Stack gap="sm"><Text variant="label">Malware</Text><Stack direction="row" gap="sm"><ValueChips values={picked.associated_malware} /></Stack></Stack>}
            <Stack gap="sm">
              <Text variant="label">{`Threats (${picked.threat_count})`}</Text>
              {!threats ? <Skeleton variant="text" lines={3} /> : !threats.length ? <Text variant="caption">No threats linked yet.</Text> : (
                <ul className="threat-plainlist">
                  {threats.map((t) => (
                    <li key={t.id}>
                      <Stack gap="sm">
                        <LinkButton onClick={() => ctx.showArticles({ threat: { id: t.id, name: t.threat_name } })}>{t.threat_name}</LinkButton>
                        <Stack direction="row" gap="sm">
                          <SeverityChip level={t.severity_level} />
                          <Text as="span" variant="caption">{`${categoryLabel(t.threat_type)} · ${t.article_count} article${t.article_count === 1 ? '' : 's'}`}</Text>
                        </Stack>
                      </Stack>
                    </li>
                  ))}
                  {picked.threat_count > threats.length && <li><Text variant="caption">{`and ${picked.threat_count - threats.length} more`}</Text></li>}
                </ul>
              )}
            </Stack>
            {picked.article_count > 0 && (
              <div>
                <Button variant="secondary" iconStart={<Icon name="Newspaper" size="sm" />} onClick={() => ctx.showArticles({ actor: { id: picked.id, name: picked.name } })}>
                  {`Show ${picked.article_count} article${picked.article_count === 1 ? '' : 's'}`}
                </Button>
              </div>
            )}
          </Stack>
        )}
      </Panel>
    </Grid>
  );
}
