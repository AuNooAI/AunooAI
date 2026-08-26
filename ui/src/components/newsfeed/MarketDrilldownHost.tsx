/**
 * Which columns each drill-down shows, and how it is opened.
 *
 * The generic table lives in MarketDrilldown; this file holds the per-list
 * decisions so MarketMonitorTab only has to say what the reader clicked. A
 * caller builds a spec, this turns it into a fetcher plus columns.
 *
 * The spec carries the filters the aggregate itself used -- period, vendor,
 * week -- rather than letting this file re-derive them. A drill-down that
 * recomputes its own window will disagree with the card that opened it, and the
 * disagreement looks like a counting bug.
 */

import React, { useCallback, useMemo } from 'react';
import {
  getCoverageItems, getFundingVendors, getInvestors, getMarketJobs,
  getMarketPosts, getVoicePosts, listCsvUrl,
  type CoverageRecord, type FundingRecord, type InvestorRecord,
  type JobRecord, type PostRecord, type VoicePostRecord,
} from '../../services/marketMonitorApi';
import {
  MarketDrilldown, cell, JOB_STATUS_LABELS, JOB_SOURCE_LABELS,
  type DrilldownColumn,
} from './MarketDrilldown';

export type DrilldownSpec =
  | { kind: 'posts'; title: string; days?: number | null; vendorId?: number;
      ownership?: 'owned' | 'reshared' | 'earned'; classification?: string;
      expectedTotal?: number }
  | { kind: 'coverage'; title: string; days?: number | null; week?: string;
      source?: string; vendorId?: number; expectedTotal?: number }
  | { kind: 'jobs'; title: string; vendorId?: number;
      status?: JobRecord['status']; source?: string; expectedTotal?: number }
  | { kind: 'funding'; title: string; stage?: string; disclosure?: string;
      expectedTotal?: number }
  | { kind: 'investors'; title: string; expectedTotal?: number }
  | { kind: 'voice'; title: string; author: string; days?: number | null;
      expectedTotal?: number };

const OWNERSHIP_LABELS: Record<string, string> = {
  owned: 'the vendor',
  reshared: 'reshared',
  earned: 'someone else',
};

export function DrilldownHost({ marketId, spec, onClose, onVendor }: {
  marketId: number;
  spec: DrilldownSpec;
  onClose: () => void;
  onVendor?: (brandId: number) => void;
}) {
  // Keyed on the spec's own values so changing a filter reloads from page one
  // instead of paging a query that no longer applies.
  const key = JSON.stringify(spec);

  const fetchPage = useCallback((page: number): Promise<any> => {
    switch (spec.kind) {
      case 'posts':
        return getMarketPosts(marketId, {
          days: spec.days, vendor_id: spec.vendorId,
          ownership: spec.ownership, classification: spec.classification,
          page, page_size: 50,
        });
      case 'coverage':
        return getCoverageItems(marketId, {
          days: spec.days, week: spec.week, source: spec.source,
          vendor_id: spec.vendorId, page, page_size: 50,
        });
      case 'jobs':
        return getMarketJobs(marketId, {
          brand_id: spec.vendorId, status: spec.status, source: spec.source,
          page, page_size: 50,
        });
      case 'funding':
        return getFundingVendors(marketId, {
          stage: spec.stage, disclosure: spec.disclosure, page, page_size: 50,
        });
      case 'investors':
        return getInvestors(marketId, { page, page_size: 50 });
      case 'voice':
        return getVoicePosts(marketId, spec.author,
                             { days: spec.days, page, page_size: 50 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [marketId, key]);

  const csvUrl = useMemo(() => {
    switch (spec.kind) {
      case 'posts':
        return listCsvUrl(marketId, 'posts', {
          days: spec.days, vendor_id: spec.vendorId,
          ownership: spec.ownership, classification: spec.classification });
      case 'coverage':
        return listCsvUrl(marketId, 'coverage/items', {
          days: spec.days, week: spec.week, source: spec.source,
          vendor_id: spec.vendorId });
      case 'jobs':
        return listCsvUrl(marketId, 'jobs',
                          { brand_id: spec.vendorId, status: spec.status,
                            source: spec.source });
      case 'funding':
        return listCsvUrl(marketId, 'funding/vendors',
                          { stage: spec.stage, disclosure: spec.disclosure });
      case 'investors':
        return listCsvUrl(marketId, 'funding/investors', {});
      case 'voice':
        return listCsvUrl(marketId, `voices/${encodeURIComponent(spec.author)}/posts`,
                          { days: spec.days });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [marketId, key]);

  const columns = useMemo(() => buildColumns(spec), [key]);

  return (
    <MarketDrilldown
      title={spec.title}
      fetchPage={fetchPage}
      columns={columns as DrilldownColumn<any>[]}
      rowKey={(row: any, i) =>
        String(row.uri ?? row.provider_item_id ?? row.brand_id
               ?? row.normalized ?? i) + ':' + i}
      onRowClick={onVendor && (spec.kind === 'posts' || spec.kind === 'jobs'
                               || spec.kind === 'funding')
        ? (row: any) => row.brand_id && onVendor(row.brand_id)
        : undefined}
      csvUrl={csvUrl}
      expectedTotal={spec.expectedTotal}
      onClose={onClose}
    />
  );
}

function buildColumns(spec: DrilldownSpec): DrilldownColumn<any>[] {
  switch (spec.kind) {
    case 'posts':
      return [
        { key: 'vendor', label: 'Vendor' },
        { key: 'published_at', label: 'Published',
          render: (r: PostRecord) => cell.date(r.published_at) },
        { key: 'title', label: 'Post',
          render: (r: PostRecord) => (
            <div className="max-w-[38rem]">
              {cell.link(r.url ?? r.uri, r.title ?? r.uri)}
              <div className="mt-0.5">{cell.excerpt(r.excerpt)}</div>
            </div>
          ) },
        // Ownership is shown as a word rather than a flag, because "owned:
        // false" does not distinguish a reshare from somebody else's article.
        { key: 'ownership', label: 'Voice', secondary: true,
          render: (r: PostRecord) =>
            OWNERSHIP_LABELS[r.ownership] ?? r.ownership },
        { key: 'classification', label: 'Kind', secondary: true,
          render: (r: PostRecord) => (
            <span title={r.why_relevant ?? undefined}>{r.classification}</span>
          ) },
        { key: 'platform', label: 'Platform', secondary: true },
        { key: 'engagement', label: 'Engagement', align: 'right',
          secondary: true,
          render: (r: PostRecord) => cell.number(r.engagement) },
      ];

    case 'coverage':
      return [
        { key: 'published_at', label: 'Published',
          render: (r: CoverageRecord) => cell.date(r.published_at) },
        { key: 'title', label: 'Item',
          render: (r: CoverageRecord) => (
            <div className="max-w-[38rem]">
              {cell.link(r.url ?? r.uri, r.title ?? r.uri)}
              <div className="mt-0.5">{cell.excerpt(r.excerpt)}</div>
            </div>
          ) },
        { key: 'platform', label: 'Platform', secondary: true },
        { key: 'ownership', label: 'Whose voice', secondary: true },
      ];

    case 'jobs':
      return [
        { key: 'vendor', label: 'Vendor' },
        { key: 'title', label: 'Role',
          render: (r: JobRecord) => cell.link(r.url, r.title) },
        { key: 'function_group', label: 'Function', secondary: true },
        { key: 'seniority', label: 'Seniority', secondary: true },
        { key: 'location', label: 'Location', secondary: true },
        // Where the listing came from. Two sources with very different
        // coverage read as one number otherwise.
        { key: 'source', label: 'Source', secondary: true,
          render: (r: JobRecord) => JOB_SOURCE_LABELS[r.source] ?? r.source },
        // The company's own publication date where its board gives one. Kept
        // distinct from "first seen", which is when we noticed.
        { key: 'posted_at', label: 'Posted',
          render: (r: JobRecord) => r.posted_at
            ? cell.date(r.posted_at)
            : <span className="text-slate-400"
                    title="This board does not publish a posting date">—</span> },
        { key: 'first_seen', label: 'First seen', secondary: true,
          render: (r: JobRecord) => cell.date(r.first_seen) },
        { key: 'last_seen', label: 'Last seen', secondary: true,
          render: (r: JobRecord) => cell.date(r.last_seen) },
        { key: 'status', label: 'Status',
          render: (r: JobRecord) => (
            <span title={r.runs_covering_vendor < 2
              ? 'Only one successful collection for this vendor, so no change '
                + 'can be reported yet.'
              : undefined}>
              {JOB_STATUS_LABELS[r.status] ?? r.status}
            </span>
          ) },
      ];

    case 'funding':
      return [
        { key: 'vendor', label: 'Vendor' },
        { key: 'disclosed_total_musd', label: 'Disclosed total', align: 'right',
          render: (r: FundingRecord) => (
            // Never a zero for a missing figure. The word says which kind of
            // missing it is.
            r.disclosed_total_musd !== null
              ? <span title="Cumulative total from the imported workbook, not a single round">
                  ${r.disclosed_total_musd.toLocaleString()}M
                </span>
              : <span className="text-slate-400 dark:text-gray-500">
                  {r.disclosure === 'undisclosed' ? 'undisclosed' : 'unavailable'}
                </span>
          ) },
        { key: 'stage_group', label: 'Stage',
          render: (r: FundingRecord) => (
            <span title={r.stage_raw ?? undefined}>
              {r.stage_group}
              {!r.is_equity_stage && (
                <span className="ml-1 text-[10px] text-slate-400">not equity</span>
              )}
            </span>
          ) },
        { key: 'investors', label: 'Investors', secondary: true,
          render: (r: FundingRecord) =>
            r.investors?.length
              ? <span title={r.investors.join(', ')}>
                  {r.investors.slice(0, 3).join(', ')}
                  {r.investors.length > 3 && ` +${r.investors.length - 3}`}
                </span>
              : <span className="text-slate-400">—</span> },
        { key: 'crunchbase_read_at', label: 'Crunchbase read', secondary: true,
          render: (r: FundingRecord) => cell.date(r.crunchbase_read_at) },
      ];

    case 'investors':
      return [
        { key: 'investor', label: 'Investor',
          render: (r: InvestorRecord) => (
            <span title={r.forms ? `Also written as: ${r.forms.join(', ')}`
                                 : undefined}>
              {r.investor}
              {r.forms && (
                <span className="ml-1 text-[10px] text-slate-400">
                  {r.forms.length} spellings
                </span>
              )}
            </span>
          ) },
        { key: 'vendor_count', label: 'Vendors', align: 'right',
          render: (r: InvestorRecord) => cell.number(r.vendor_count) },
        { key: 'vendors', label: 'Backing',
          render: (r: InvestorRecord) => (
            <span>{r.vendors.map(v => v.vendor).join(', ')}</span>
          ) },
        { key: 'evidence', label: 'Evidence', secondary: true,
          render: (r: InvestorRecord) => (
            <span className="flex flex-wrap gap-2">
              {r.vendors.filter(v => v.evidence_url).map(v => (
                <React.Fragment key={v.brand_id}>
                  {cell.link(v.evidence_url, v.vendor)}
                </React.Fragment>
              ))}
            </span>
          ) },
      ];

    case 'voice':
      return [
        { key: 'published_at', label: 'Published',
          render: (r: VoicePostRecord) => cell.date(r.published_at) },
        { key: 'title', label: 'Post',
          render: (r: VoicePostRecord) => (
            <div className="max-w-[38rem]">
              {cell.link(r.url ?? r.uri, r.title ?? r.uri)}
              <div className="mt-0.5">{cell.excerpt(r.excerpt)}</div>
            </div>
          ) },
        { key: 'platform', label: 'Platform', secondary: true },
        { key: 'vendors_mentioned', label: 'Vendors named',
          render: (r: VoicePostRecord) =>
            r.vendors_mentioned?.length
              ? r.vendors_mentioned.join(', ')
              // A post can be about the market without naming a tracked vendor,
              // and that is not a matching failure.
              : <span className="text-slate-400">none tracked</span> },
        { key: 'engagement', label: 'Engagement', align: 'right',
          secondary: true,
          render: (r: VoicePostRecord) => cell.number(r.engagement) },
      ];
  }
}
