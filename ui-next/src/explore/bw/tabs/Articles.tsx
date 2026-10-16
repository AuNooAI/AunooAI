import { useState } from 'react';
import { ArticleCard, Button, Chip, EmptyState, FilterChipRow, Icon, Pagination, Panel, Skeleton, Stack, Text, type MenuItem } from '@aunoo/ui';
import { CATEGORY_SHORT_NAMES, getArticles, setFindingState, type BWArticle } from '@monolith/brandWatcherApi';
import { errorText } from '../../../shell';
import { download, TitleLink } from '../../feed/api';
import type { BwContext } from '../context';
import { AddToIncidentDialog, type IncidentSource } from '../overlays/AddToIncidentDialog';
import { Coverage } from './cases/Coverage';
import { SignalsChips, sigKey, useSignalsOverrides } from './cases/signals';

/*
 * The classified article list (old Articles tab): category filters, sentiment, risk findings,
 * story size and framing, Five Signals chips, case state and CSV export. Reads only; screening
 * runs start inside the Five Signals dialog.
 */

type ReviewState = 'reviewed' | 'escalated' | 'dismissed' | 'false_positive';
const REVIEW_LABEL: Record<string, string> = { reviewed: 'Reviewed', escalated: 'Escalated', dismissed: 'Dismissed', false_positive: 'False positive' };
const short = (c: string) => (CATEGORY_SHORT_NAMES as Record<string, string>)[c] ?? c;

// Story framing across the copies of one story (old isNegConsensus / isPolarized)
export const negativeConsensus = (a: BWArticle) => (a.story_scored ?? 0) >= 3 && (a.story_neg ?? 0) / (a.story_scored ?? 1) >= 0.7;
export const polarized = (a: BWArticle) =>
  (a.story_scored ?? 0) >= 4 && Math.min(a.story_neg ?? 0, a.story_pos ?? 0) / (a.story_scored ?? 1) >= 0.3;

export function factualityTone(f: string): 'success' | 'warning' | 'error' | 'muted' {
  const t = f.toLowerCase();
  if (t.includes('very high') || t === 'high') return 'success';
  if (t.includes('mixed') || t.includes('mostly')) return 'warning';
  if (t.includes('low')) return 'error';
  return 'muted';
}

function sentimentTone(s: string): 'success' | 'error' | 'muted' {
  const t = s.toLowerCase();
  return t === 'positive' ? 'success' : t === 'negative' ? 'error' : 'muted';
}

/** Downloads every article matching the current filters (pages of 200, at most 5,000). */
async function exportCsv(ctx: BwContext) {
  const c = ctx.bw.config;
  const all: BWArticle[] = [];
  for (let page = 1; ; page++) {
    const r = await getArticles({
      brand_ids: c.selectedBrandIds.length ? c.selectedBrandIds : undefined,
      topics: c.selectedTopics.length ? c.selectedTopics : undefined,
      categories: c.selectedCategories.length ? c.selectedCategories : undefined,
      days_back: c.daysBack, sort_by: c.sortBy, page, per_page: 200,
    });
    all.push(...r.articles);
    if (page >= r.total_pages || all.length >= 5000) break;
  }
  const esc = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const header = ['title', 'url', 'source', 'published', 'brand', 'sentiment', 'categories', 'matched_keywords', 'factual_reporting', 'risks', 'case_status', 'signals_verdict', 'signals_composite'];
  const lines = [header.join(','), ...all.map((a) => [
    a.title, a.uri, a.news_source, a.publication_date, a.brand_name, a.sentiment, (a.categories ?? []).join('; '),
    (a.matched_keywords ?? []).join('; '), a.factual_reporting, (a.risks ?? []).map((r) => `${r.risk_type}:${r.severity}`).join('; '),
    a.review_status, a.signals_summary?.verdict, a.signals_summary?.composite,
  ].map(esc).join(','))];
  download(`brand_watcher_articles_${new Date().toISOString().slice(0, 10)}.csv`, lines.join('\n'), 'text/csv;charset=utf-8');
  return all.length;
}

export function Articles(ctx: BwContext) {
  const { bw, notify } = ctx;
  const { config, updateConfig } = bw;
  const overrides = useSignalsOverrides();
  const [review, setReview] = useState<Record<string, string>>({});
  const [attach, setAttach] = useState<IncidentSource | null>(null);
  const [exporting, setExporting] = useState(false);

  const cats = bw.categories.filter((c) => c.article_count > 0);
  const reviewOf = (a: BWArticle) => review[sigKey(a.uri, a.brand_id)] || a.review_status || 'new';

  const setState = async (a: BWArticle, status: ReviewState) => {
    if (!a.brand_id) {
      notify('This article has no brand, so its case state can’t be set.');
      return;
    }
    const k = sigKey(a.uri, a.brand_id);
    const before = review[k];
    setReview((r) => ({ ...r, [k]: status }));
    try {
      await setFindingState(a.uri, a.brand_id, status);
      notify(`Marked ${REVIEW_LABEL[status].toLowerCase()}`);
    } catch (e) {
      setReview((r) => ({ ...r, [k]: before }));
      notify(`Not saved: ${errorText(e)}`);
    }
  };

  const onExport = async () => {
    setExporting(true);
    try {
      const n = await exportCsv(ctx);
      notify(`${n} articles downloaded`);
    } catch (e) {
      notify(`Export failed: ${errorText(e)}`);
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      {ctx.selectedBrands.length <= 1 && <Coverage brand={ctx.focusBrand} daysBack={config.daysBack} />}
      <Panel
        title="Articles"
        description={bw.totalArticles ? `${bw.totalArticles.toLocaleString('en-GB')} articles · page ${config.page} of ${bw.totalPages}` : undefined}
        headerAside={<Button size="sm" variant="secondary" iconStart={<Icon name="DownloadSimple" size="sm" />} disabled={exporting} onClick={() => void onExport()}>{exporting ? 'Exporting…' : 'Export CSV'}</Button>}
      >
        <Stack gap="lg">
          {cats.length > 0 && (
            <FilterChipRow
              label="Categories"
              options={cats.map((c) => ({ value: c.category, label: `${short(c.category)} (${c.article_count})` }))}
              selected={config.selectedCategories}
              onChange={(selectedCategories) => updateConfig({ selectedCategories })}
              maxVisible={10}
            />
          )}
          {bw.loadingArticles ? <Skeleton variant="text" lines={8} /> : bw.articles.length === 0 ? (
            <EmptyState icon="Newspaper" title="No articles">Nothing matches these brands, categories and dates.</EmptyState>
          ) : (
            <Stack as="ul" gap="sm" label="Articles">
              {bw.articles.map((a) => {
                const state = reviewOf(a);
                const summary = overrides[sigKey(a.uri, a.brand_id)] ?? a.signals_summary;
                const open = () => ctx.openArticle({ ...a });
                const actions: MenuItem[] = [
                  { id: 'details', label: 'Details', icon: 'Info' },
                  { id: 'reviewed', label: 'Mark reviewed', icon: 'Check', separatorBefore: true },
                  { id: 'escalated', label: 'Escalate', icon: 'Warning' },
                  { id: 'dismissed', label: 'Dismiss', icon: 'X' },
                  { id: 'false_positive', label: 'False positive', icon: 'EyeSlash' },
                  { id: 'incident', label: 'Add to incident…', icon: 'FolderPlus', separatorBefore: true },
                ];
                if (a.brand_id && a.uri.startsWith('http')) actions.splice(1, 0, { id: 'signals', label: 'Five Signals screen', icon: 'ShieldCheck' });
                return (
                  <ArticleCard
                    key={`${a.uri}-${a.brand_id}`}
                    as="li"
                    variant="row"
                    headingLevel={3}
                    meta={[a.brand_name, a.news_source, a.publication_date?.slice(0, 10)].filter(Boolean).join(' · ')}
                    flag={state !== 'new' ? <Chip size="sm" tone={state === 'escalated' ? 'error' : 'muted'}>{REVIEW_LABEL[state] ?? state}</Chip> : undefined}
                    title={<TitleLink href={a.uri} onOpen={open}>{a.title}</TitleLink>}
                    summary={a.summary ?? undefined}
                    actions={actions}
                    actionsLabel={`Actions for “${a.title}”`}
                    onAction={(id) => {
                      if (id === 'details') open();
                      else if (id === 'signals') ctx.openSignals({ uri: a.uri, title: a.title, brand_id: a.brand_id });
                      else if (id === 'incident') setAttach({ kind: 'article', ref: a.uri, label: a.title || a.uri, brandId: a.brand_id });
                      else void setState(a, id as ReviewState);
                    }}
                    tags={
                      <>
                        {a.categories.map((c) => <Chip key={c} size="sm" tone="neutral">{short(c)}</Chip>)}
                        {a.sentiment && <Chip size="sm" tone={sentimentTone(a.sentiment)}>{a.sentiment}</Chip>}
                        {(a.risks ?? []).map((r) => (
                          <Chip key={r.risk_type} size="sm" tone={r.severity === 'high' ? 'error' : r.severity === 'medium' ? 'warning' : 'muted'} icon={<Icon name="Warning" size="sm" />}>
                            {r.risk_type.replace(/_/g, ' ')} ({r.severity})
                          </Chip>
                        ))}
                        {(a.story_size ?? 1) >= 2 && <Chip size="sm" tone="muted">Carried by {a.story_size} sources</Chip>}
                        {negativeConsensus(a) && <Chip size="sm" tone="error">Negative across sources ({a.story_neg} of {a.story_scored})</Chip>}
                        {!negativeConsensus(a) && polarized(a) && <Chip size="sm" tone="warning">Split coverage ({a.story_pos} positive, {a.story_neg} negative)</Chip>}
                        {a.factual_reporting && <Chip size="sm" tone={factualityTone(a.factual_reporting)}>Factual: {a.factual_reporting}</Chip>}
                        {a.entity_match?.verified && <Chip size="sm" tone="info">Entity verified{a.entity_match.relevance != null ? ` ${a.entity_match.relevance.toFixed(2)}` : ''}</Chip>}
                        {a.is_owned && <Chip size="sm" tone="muted">Brand’s own content, not counted</Chip>}
                        {(a.matched_keywords ?? []).length > 0 && <Chip size="sm" tone="muted">Matched: {a.matched_keywords.join(', ')}</Chip>}
                        <SignalsChips summary={summary} available={bw.signalsAvailable && !!a.brand_id} uri={a.uri} onOpen={() => ctx.openSignals({ uri: a.uri, title: a.title, brand_id: a.brand_id })} />
                      </>
                    }
                  />
                );
              })}
            </Stack>
          )}
          {bw.totalPages > 1 && <Pagination label="Article pages" page={config.page} pageCount={bw.totalPages} onPageChange={(page) => updateConfig({ page })} />}
          <Text variant="caption">The brand’s own content is listed but left out of sentiment and share of voice.</Text>
        </Stack>
      </Panel>
      <AddToIncidentDialog source={attach} onClose={() => setAttach(null)} notify={notify} />
    </>
  );
}
