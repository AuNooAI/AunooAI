import { useEffect, useMemo, useState } from 'react';
import { ArticleCard, Banner, Chip, EmptyState, Icon, Pagination, Panel, Select, Skeleton, Stack, Text, TextField, type MenuItem } from '@aunoo/ui';
import { errorText } from '../../../../shell';
import { askAuspex, TitleLink } from '../../../feed/api';
import { getArticles, type ArticleQuery, type LinkedArticle, type SeverityLevel } from '../api';
import type { ArticleFilter, ThreatCtx } from '../context';
import { categoryLabel, fmtDate, SEVERITY_LABELS, SEVERITY_LEVELS, severityLabel } from '../labels';
import { LinkButton, SeverityChip } from '../parts';

/*
 * Articles the AI linked to threats, as the old ThreatArticlesTab, with the filter another view sent
 * the reader here with (a threat, an actor, a campaign, a severity or a type). Details open in the
 * shared article panel, which records "more/less like this" for real; the old panel only logged it.
 *
 * Two old bugs: "Show all … threats" from Categories and the Overview's type list opened every article,
 * because the old list ignored the type; and changing the threat, actor or campaign filter kept the old
 * page number, so the list could open on an empty page.
 */

type SortBy = ArticleQuery['sortBy'];
type GroupBy = 'none' | 'source' | 'severity' | 'date' | 'threat';

const ACTIONS: MenuItem[] = [
  { id: 'details', label: 'Show details', icon: 'FileText' },
  { id: 'auspex', label: 'Analyse with Auspex', icon: 'ChatCentered' },
  { id: 'open', label: 'Open the original', icon: 'ArrowSquareOut' },
];

function auspexPrompt(a: LinkedArticle) {
  const threats = (a.threats ?? []).map((t) => `${t.name} (${severityLabel(t.severity_level)} severity, ${categoryLabel(t.type)})`).join(', ');
  return [
    `Analyse this cybersecurity threat article: "${a.title ?? a.uri}"`,
    `Article: ${a.uri}`,
    `Source: ${a.source ?? 'unknown'}`,
    `Linked threats: ${threats || 'none identified'}`,
    `Highest severity: ${severityLabel(a.severity_level)}`,
    a.summary ? `Summary: ${a.summary}` : '',
    'Please give: 1. a technical analysis of the threats, 2. indicators of compromise to look for, 3. the MITRE ATT&CK techniques likely involved, 4. recommended defences, 5. attribution, if any is available.',
  ].filter(Boolean).join('\n');
}

export function Articles({ ctx, filter, onFilter }: { ctx: ThreatCtx; filter: ArticleFilter; onFilter: (f: ArticleFilter) => void }) {
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [sortBy, setSortBy] = useState<SortBy>('date');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [groupBy, setGroupBy] = useState<GroupBy>('none');
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<{ list: LinkedArticle[]; total: number; pages: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Typing waits a moment before searching, so each key press doesn't reload the list
  useEffect(() => {
    const t = setTimeout(() => setQuery(search.trim()), 350);
    return () => clearTimeout(t);
  }, [search]);
  const filterKey = JSON.stringify(filter);
  useEffect(() => setPage(1), [filterKey, query, sortBy, sortOrder]);

  useEffect(() => {
    let live = true;
    setError(null);
    getArticles({
      page, search: query || undefined, severityLevel: filter.severity, threatType: filter.threatType, threatId: filter.threat?.id,
      actorId: filter.actor?.id, campaignId: filter.campaign?.id, sortBy, sortOrder,
    }).then((r) => live && setResult({ list: r.data, total: r.total, pages: r.total_pages }), (e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, [page, query, filterKey, sortBy, sortOrder]); // eslint-disable-line react-hooks/exhaustive-deps

  const groups = useMemo(() => {
    const list = result?.list ?? [];
    if (groupBy === 'none') return [['', list]] as [string, LinkedArticle[]][];
    const m = new Map<string, LinkedArticle[]>();
    for (const a of list) {
      const k = groupBy === 'source' ? a.source || 'Unknown source'
        : groupBy === 'severity' ? severityLabel(a.severity_level)
          : groupBy === 'date' ? fmtDate(a.publication_date)
            : a.threats?.[0]?.name ?? 'No threat';
      m.set(k, [...(m.get(k) ?? []), a]);
    }
    return [...m.entries()];
  }, [result, groupBy]);

  const chips: { key: keyof ArticleFilter; text: string }[] = [
    filter.threat && { key: 'threat' as const, text: `Threat: ${filter.threat.name}` },
    filter.actor && { key: 'actor' as const, text: `Actor: ${filter.actor.name}` },
    filter.campaign && { key: 'campaign' as const, text: `Campaign: ${filter.campaign.name}` },
    filter.threatType && { key: 'threatType' as const, text: `Type: ${categoryLabel(filter.threatType)}` },
  ].filter(Boolean) as { key: keyof ArticleFilter; text: string }[];

  return (
    <Panel title="Articles" description={result ? `${result.total} article${result.total === 1 ? '' : 's'} linked to threats${chips.length || filter.severity ? ' for these filters' : ''}, all time.` : undefined}>
      <Stack gap="md">
        <Stack direction="row" gap="sm">
          <TextField label="Search articles" hideLabel type="search" placeholder="Search titles and summaries" value={search} onChange={setSearch} />
          <Select
            label="Severity"
            hideLabel
            icon="Funnel"
            options={[{ value: 'all', label: 'Any severity' }, ...SEVERITY_LEVELS.map((l) => ({ value: l, label: SEVERITY_LABELS[l] }))]}
            value={filter.severity ?? 'all'}
            onValueChange={(v) => onFilter({ ...filter, severity: v === 'all' ? undefined : (v as SeverityLevel) })}
          />
          <Select
            label="Sort"
            hideLabel
            icon="ArrowDown"
            options={[{ value: 'date', label: 'Newest first' }, { value: 'date-asc', label: 'Oldest first' }, { value: 'severity', label: 'Most severe first' }, { value: 'relevance', label: 'Most relevant first' }, { value: 'title', label: 'Title A to Z' }]}
            value={sortBy === 'date' && sortOrder === 'asc' ? 'date-asc' : sortBy}
            onValueChange={(v) => {
              if (v === 'date-asc') { setSortBy('date'); setSortOrder('asc'); }
              else { setSortBy(v as SortBy); setSortOrder(v === 'title' ? 'asc' : 'desc'); }
            }}
          />
          <Select
            label="Group by"
            hideLabel
            icon="ListBullets"
            options={[{ value: 'none', label: 'No grouping' }, { value: 'source', label: 'By source' }, { value: 'severity', label: 'By severity' }, { value: 'date', label: 'By date' }, { value: 'threat', label: 'By threat' }]}
            value={groupBy}
            onValueChange={(v) => setGroupBy(v as GroupBy)}
          />
        </Stack>
        {chips.length > 0 && (
          <Stack direction="row" gap="sm">
            {chips.map((c) => (
              <Chip key={c.key} tone="accent" icon={<Icon name="X" size="sm" />} label={`Remove the filter ${c.text}`} onClick={() => onFilter({ ...filter, [c.key]: undefined })}>{c.text}</Chip>
            ))}
          </Stack>
        )}
        {error && <Banner tone="error" title="Articles didn’t load" description={error} />}
        {!result && !error ? <Skeleton variant="text" lines={8} /> : result && !result.list.length ? (
          <EmptyState icon="Newspaper" title="No articles">No article linked to a threat matches these filters.</EmptyState>
        ) : result && (
          groups.map(([g, list]) => (
            <Stack key={g || 'all'} gap="sm">
              {g && <Text variant="label">{`${g} (${list.length})`}</Text>}
              <Stack as="ul" gap="sm" label={g ? `Articles: ${g}` : 'Articles'}>
                {list.map((a) => (
                  <ArticleCard
                    key={a.uri}
                    as="li"
                    variant="row"
                    headingLevel={3}
                    title={<TitleLink href={a.uri} onOpen={() => ctx.openArticle(a)}>{a.title || a.uri}</TitleLink>}
                    meta={[a.source, fmtDate(a.publication_date), a.relevance_score != null ? `relevance ${Math.round(a.relevance_score * 100)}%` : null].filter(Boolean).join(' · ')}
                    flag={<SeverityChip level={a.severity_level} />}
                    summary={a.summary ?? undefined}
                    tags={a.threats?.length ? (
                      <Stack direction="row" gap="sm">
                        {a.threats.slice(0, 4).map((t) => (
                          <LinkButton key={t.id} onClick={() => onFilter({ threat: { id: t.id, name: t.name } })} label={`Show articles about ${t.name}`}>{t.name}</LinkButton>
                        ))}
                        {a.threats.length > 4 && <Text as="span" variant="caption">{`+${a.threats.length - 4} more`}</Text>}
                      </Stack>
                    ) : undefined}
                    actions={ACTIONS}
                    actionsLabel={`Actions for “${a.title || a.uri}”`}
                    onAction={(id) => {
                      if (id === 'details') ctx.openArticle(a);
                      else if (id === 'auspex') askAuspex(auspexPrompt(a));
                      else if (id === 'open') window.open(a.uri, '_blank', 'noopener');
                    }}
                  />
                ))}
              </Stack>
            </Stack>
          ))
        )}
        {result && result.pages > 1 && <Pagination page={page} pageCount={result.pages} onPageChange={setPage} label="Article pages" />}
      </Stack>
    </Panel>
  );
}
