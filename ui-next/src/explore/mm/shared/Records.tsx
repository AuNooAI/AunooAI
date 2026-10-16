import { useEffect, useMemo, useState } from 'react';
import { Banner, Chip, Dialog, Pagination, Skeleton, Stack, Table, Text, TextLink, type TableColumn } from '@aunoo/ui';
import {
  getCoverageItems, getFundingVendors, getInvestors, getMarketJobs, getMarketPosts, getVoicePosts, listCsvUrl,
  type CoverageRecord, type FundingRecord, type InvestorRecord, type JobRecord, type ListEnvelope, type PostRecord, type VoicePostRecord,
} from '@monolith/marketMonitorApi';
import { errorText } from '../../../shell';
import { DataStateBadge, MetricHelp, UnmeasuredNotice } from './metric';
import { Missing } from './SortTable';

/*
 * The records behind a number, as the old MarketDrilldown + MarketDrilldownHost. Every list endpoint
 * returns the same envelope, so one dialog serves them all. It always shows the server's true total,
 * the filters the server says it applied, and the metric's state, so an empty list says whether
 * nothing matched or nothing was collected. The spec carries the filters the figure itself used, so
 * the list can't disagree with the card that opened it.
 */

export type DrilldownSpec =
  | { kind: 'posts'; title: string; days?: number | null; vendorId?: number; ownership?: 'owned' | 'reshared' | 'earned'; classification?: string; expectedTotal?: number }
  | { kind: 'coverage'; title: string; days?: number | null; week?: string; source?: string; vendorId?: number; expectedTotal?: number }
  | { kind: 'jobs'; title: string; vendorId?: number; status?: JobRecord['status']; source?: string; expectedTotal?: number }
  | { kind: 'funding'; title: string; stage?: string; disclosure?: string; expectedTotal?: number }
  | { kind: 'investors'; title: string; expectedTotal?: number }
  | { kind: 'voice'; title: string; author: string; days?: number | null; expectedTotal?: number };

/** `first_observation` isn't "new": with one run of history there is nothing to have been absent from */
export const JOB_STATUS_LABELS: Record<string, string> = {
  currently_observed: 'currently observed',
  newly_observed: 'newly observed',
  no_longer_observed: 'no longer observed',
  first_observation: 'first observation',
};
export const JOB_SOURCE_LABELS: Record<string, string> = { linkedin_jobs: 'LinkedIn', ats_jobs: 'the company’s own board' };
const OWNERSHIP_LABELS: Record<string, string> = { owned: 'the vendor', reshared: 'reshared', earned: 'someone else' };

/** Shared cell renderers, so a date or a link looks the same in every list */
export const cell = {
  date: (v: string | null | undefined) => (v ? String(v).slice(0, 10) : '—'),
  link: (url: string | null | undefined, label: string | null | undefined) => {
    const text = label || url || '—';
    return url ? <TextLink href={url} external>{text}</TextLink> : <span>{text}</span>;
  },
  excerpt: (v: string | null | undefined, chars = 160) =>
    v ? <Text as="span" variant="caption">{v.length > chars ? `${v.slice(0, chars)}…` : v}</Text> : <Missing />,
  number: (v: number | null | undefined) => (v === null || v === undefined ? '—' : v.toLocaleString()),
};

const titled = (url: string | null | undefined, title: string | null | undefined, excerpt: string | null | undefined) => (
  <Stack gap="sm">
    {cell.link(url, title)}
    {cell.excerpt(excerpt)}
  </Stack>
);

type Row = Record<string, unknown>;

function fetcher(marketId: number, spec: DrilldownSpec): (page: number) => Promise<ListEnvelope<Row>> {
  const go = (p: Promise<ListEnvelope<unknown>>) => p as Promise<ListEnvelope<Row>>;
  switch (spec.kind) {
    case 'posts':
      return (page) => go(getMarketPosts(marketId, { days: spec.days, vendor_id: spec.vendorId, ownership: spec.ownership, classification: spec.classification, page, page_size: 50 }));
    case 'coverage':
      return (page) => go(getCoverageItems(marketId, { days: spec.days, week: spec.week, source: spec.source, vendor_id: spec.vendorId, page, page_size: 50 }));
    case 'jobs':
      return (page) => go(getMarketJobs(marketId, { brand_id: spec.vendorId, status: spec.status, source: spec.source, page, page_size: 50 }));
    case 'funding':
      return (page) => go(getFundingVendors(marketId, { stage: spec.stage, disclosure: spec.disclosure, page, page_size: 50 }));
    case 'investors':
      return (page) => go(getInvestors(marketId, { page, page_size: 50 }));
    case 'voice':
      return (page) => go(getVoicePosts(marketId, spec.author, { days: spec.days, page, page_size: 50 }));
  }
}

function csvFor(marketId: number, spec: DrilldownSpec) {
  switch (spec.kind) {
    case 'posts':
      return listCsvUrl(marketId, 'posts', { days: spec.days, vendor_id: spec.vendorId, ownership: spec.ownership, classification: spec.classification });
    case 'coverage':
      return listCsvUrl(marketId, 'coverage/items', { days: spec.days, week: spec.week, source: spec.source, vendor_id: spec.vendorId });
    case 'jobs':
      return listCsvUrl(marketId, 'jobs', { brand_id: spec.vendorId, status: spec.status, source: spec.source });
    case 'funding':
      return listCsvUrl(marketId, 'funding/vendors', { stage: spec.stage, disclosure: spec.disclosure });
    case 'investors':
      return listCsvUrl(marketId, 'funding/investors', {});
    case 'voice':
      return listCsvUrl(marketId, `voices/${encodeURIComponent(spec.author)}/posts`, { days: spec.days });
  }
}

function columnsFor(spec: DrilldownSpec): TableColumn<Row>[] {
  const c = <T,>(col: Omit<TableColumn<T>, 'render'> & { render?: (r: T) => React.ReactNode }) => col as unknown as TableColumn<Row>;
  switch (spec.kind) {
    case 'posts':
      return [
        c<PostRecord>({ key: 'vendor', header: 'Vendor', rowHeader: true }),
        c<PostRecord>({ key: 'published_at', header: 'Published', render: (r) => cell.date(r.published_at) }),
        c<PostRecord>({ key: 'title', header: 'Post', wrap: true, render: (r) => titled(r.url ?? r.uri, r.title ?? r.uri, r.excerpt) }),
        c<PostRecord>({ key: 'ownership', header: 'Voice', render: (r) => OWNERSHIP_LABELS[r.ownership] ?? r.ownership }),
        c<PostRecord>({ key: 'classification', header: 'Kind', wrap: true, render: (r) => (r.why_relevant ? `${r.classification}: ${r.why_relevant}` : r.classification) }),
        c<PostRecord>({ key: 'platform', header: 'Platform' }),
        c<PostRecord>({ key: 'engagement', header: 'Engagement', align: 'end', render: (r) => cell.number(r.engagement) }),
      ];
    case 'coverage':
      return [
        c<CoverageRecord>({ key: 'published_at', header: 'Published', render: (r) => cell.date(r.published_at) }),
        c<CoverageRecord>({ key: 'title', header: 'Item', wrap: true, render: (r) => titled(r.url ?? r.uri, r.title ?? r.uri, r.excerpt) }),
        c<CoverageRecord>({ key: 'platform', header: 'Platform' }),
        c<CoverageRecord>({ key: 'ownership', header: 'Whose voice' }),
      ];
    case 'jobs':
      return [
        c<JobRecord>({ key: 'vendor', header: 'Vendor', rowHeader: true }),
        c<JobRecord>({ key: 'title', header: 'Role', wrap: true, render: (r) => cell.link(r.url, r.title) }),
        c<JobRecord>({ key: 'function_group', header: 'Function' }),
        c<JobRecord>({ key: 'seniority', header: 'Seniority' }),
        c<JobRecord>({ key: 'location', header: 'Location', wrap: true }),
        c<JobRecord>({ key: 'source', header: 'Source', render: (r) => JOB_SOURCE_LABELS[r.source] ?? r.source }),
        // The company's own date where its board gives one; "first seen" is when we noticed
        c<JobRecord>({ key: 'posted_at', header: 'Posted', render: (r) => (r.posted_at ? cell.date(r.posted_at) : <Missing>no date on this board</Missing>) }),
        c<JobRecord>({ key: 'first_seen', header: 'First seen', render: (r) => cell.date(r.first_seen) }),
        c<JobRecord>({ key: 'last_seen', header: 'Last seen', render: (r) => cell.date(r.last_seen) }),
        c<JobRecord>({
          key: 'status', header: 'Status', wrap: true,
          render: (r) => `${JOB_STATUS_LABELS[r.status] ?? r.status}${r.runs_covering_vendor < 2 ? ' (one collection so far, so no change can be reported yet)' : ''}`,
        }),
      ];
    case 'funding':
      return [
        c<FundingRecord>({ key: 'vendor', header: 'Vendor', rowHeader: true }),
        // Never a zero for a missing figure; the word says which kind of missing
        c<FundingRecord>({
          key: 'disclosed_total_musd', header: 'Disclosed total (cumulative)', align: 'end',
          render: (r) => (r.disclosed_total_musd !== null ? `$${r.disclosed_total_musd.toLocaleString()}M` : <Missing>{r.disclosure === 'undisclosed' ? 'undisclosed' : 'unavailable'}</Missing>),
        }),
        c<FundingRecord>({ key: 'stage_group', header: 'Stage', render: (r) => `${r.stage_group}${r.stage_raw && r.stage_raw !== r.stage_group ? ` (${r.stage_raw})` : ''}${!r.is_equity_stage ? ', not equity' : ''}` }),
        c<FundingRecord>({
          key: 'investors', header: 'Investors', wrap: true,
          render: (r) => (r.investors?.length ? `${r.investors.slice(0, 3).join(', ')}${r.investors.length > 3 ? ` +${r.investors.length - 3}` : ''}` : <Missing />),
        }),
        c<FundingRecord>({ key: 'crunchbase_read_at', header: 'Crunchbase read', render: (r) => cell.date(r.crunchbase_read_at) }),
      ];
    case 'investors':
      return [
        c<InvestorRecord>({ key: 'investor', header: 'Investor', rowHeader: true, wrap: true, render: (r) => (r.forms ? `${r.investor} (also written as ${r.forms.join(', ')})` : r.investor) }),
        c<InvestorRecord>({ key: 'vendor_count', header: 'Vendors', align: 'end', render: (r) => cell.number(r.vendor_count) }),
        c<InvestorRecord>({ key: 'vendors', header: 'Backing', wrap: true, render: (r) => r.vendors.map((v) => v.vendor).join(', ') }),
        c<InvestorRecord>({
          key: 'evidence', header: 'Evidence', wrap: true,
          render: (r) => <Stack direction="row" gap="sm">{r.vendors.filter((v) => v.evidence_url).map((v) => <span key={v.brand_id}>{cell.link(v.evidence_url, v.vendor)}</span>)}</Stack>,
        }),
      ];
    case 'voice':
      return [
        c<VoicePostRecord>({ key: 'published_at', header: 'Published', render: (r) => cell.date(r.published_at) }),
        c<VoicePostRecord>({ key: 'title', header: 'Post', wrap: true, render: (r) => titled(r.url ?? r.uri, r.title ?? r.uri, r.excerpt) }),
        c<VoicePostRecord>({ key: 'platform', header: 'Platform' }),
        // A post can be about the market without naming a tracked vendor
        c<VoicePostRecord>({ key: 'vendors_mentioned', header: 'Vendors named', wrap: true, render: (r) => (r.vendors_mentioned?.length ? r.vendors_mentioned.join(', ') : <Missing>none tracked</Missing>) }),
        c<VoicePostRecord>({ key: 'engagement', header: 'Engagement', align: 'end', render: (r) => cell.number(r.engagement) }),
      ];
  }
}

export function RecordsDialog({ marketId, spec, onClose, onVendor }: { marketId: number; spec: DrilldownSpec | null; onClose: () => void; onVendor?: (id: number) => void }) {
  const specKey = JSON.stringify(spec);
  const fetchPage = useMemo(() => (spec ? fetcher(marketId, spec) : null), [marketId, specKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const columns = useMemo(() => (spec ? columnsFor(spec) : []), [specKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<ListEnvelope<Row> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setPage(1);
    setResult(null);
  }, [fetchPage]);
  useEffect(() => {
    if (!fetchPage) return;
    let live = true;
    setLoading(true);
    setError(null);
    fetchPage(page)
      .then((r) => live && setResult(r), (e) => live && setError(errorText(e)))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [fetchPage, page]);

  if (!spec) return null;
  const pag = result?.meta.pagination;
  const meta = result?.meta.metric ?? null;
  const filters = Object.entries(result?.meta.applied_filters ?? {});
  const disagrees = spec.expectedTotal !== undefined && pag && pag.total !== spec.expectedTotal;
  // Rows with a vendor open its page, as the old list did for posts, jobs and funding
  const vendorRows = onVendor && (spec.kind === 'posts' || spec.kind === 'jobs' || spec.kind === 'funding');
  const cols = vendorRows
    ? columns.map((col) => (col.key !== 'vendor' ? col : {
      ...col,
      render: (r: Row) => (r.brand_id ? (
        <a className="text-link" href={`${window.location.pathname}?vendor=${r.brand_id}`} onClick={(e) => { if (e.button !== 0 || e.metaKey || e.ctrlKey) return; e.preventDefault(); onVendor!(r.brand_id as number); }}>{String(r.vendor ?? '')}</a>
      ) : String(r.vendor ?? '')),
    }))
    : columns;

  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      size="xl"
      title={spec.title}
      description={pag ? `${pag.total.toLocaleString()} record${pag.total === 1 ? '' : 's'}${pag.pages > 1 ? ` · page ${pag.page} of ${pag.pages}` : ''}` : loading ? 'Loading…' : undefined}
    >
      <Stack gap="md">
        <Stack direction="row" justify="between" gap="sm">
          <Stack direction="row" gap="sm">
            <MetricHelp meta={meta} />
            <DataStateBadge meta={meta} />
            {/* The server's own account of what it filtered on, so an ignored filter can't pass unnoticed */}
            {filters.map(([k, v]) => <Chip key={k} tone="muted" size="sm">{`${k.replace(/_/g, ' ')}: ${String(v)}`}</Chip>)}
          </Stack>
          <TextLink href={csvFor(marketId, spec)}>Download as CSV</TextLink>
        </Stack>
        {disagrees && (
          <Banner
            tone="warning"
            title="This list and the figure disagree"
            description={`This list holds ${pag!.total.toLocaleString()} records but the figure that opened it said ${spec.expectedTotal!.toLocaleString()}. The filters may not match, so treat both numbers as unconfirmed.`}
          />
        )}
        {result && result.meta.notes.length > 0 && <Banner tone="info" title="Notes" description={result.meta.notes.join(' ')} />}
        {error && <Banner tone="error" title="The list didn’t load" description={error} />}
        {!result && !error && <Skeleton variant="text" lines={8} />}
        {result && !error && (result.data.length === 0
          ? (meta && !meta.measured ? <UnmeasuredNotice meta={meta} /> : <Text>Nothing matched these filters.</Text>)
          : <Table caption={spec.title} hideCaption rows={result.data} rowKey={(r) => `${String(r.uri ?? r.provider_item_id ?? r.brand_id ?? r.normalized ?? '')}:${result.data.indexOf(r)}`} columns={cols} />)}
        {pag && pag.pages > 1 && <Pagination page={page} pageCount={pag.pages} onPageChange={setPage} label={`${spec.title} pages`} />}
      </Stack>
    </Dialog>
  );
}
