import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import type { MenuItem } from '@aunoo/ui';
import {
  exportBrandData, getAllAppRatings, getAppReviews, getBrandAlerts, getComparison, getEmployeeRisk, getLatestNarrative, getPerception,
  getRiskAssessment, getRiskSummary, getSentimentTrends, getShareOfVoice, getSocialPosts, listIncidents,
} from '@monolith/brandWatcherApi';
import { downloadBrandWatcherReport } from '@monolith/brandReportHtml';
import { errorText } from '../../../shell';
import { Markdown } from '../../../shell/Markdown';
import { download } from '../../feed/api';
import { downloadElementPng, downloadPdf } from '../../shared/exports';
import type { BwContext } from '../context';
import { buildReportMarkdown, reportPeriod, reportTitle, type ReportData } from './reportMarkdown';

/*
 * The header's Export menu.
 * - Interactive report (HTML): the old page's self-contained file (ui/src/services/brandReportHtml.ts).
 * - Markdown, PDF and print: one report text (reportMarkdown.ts) from the same reads, so they agree.
 * - Image (PNG): a picture of the Brand Watcher view as it is on screen (the element with id
 *   BW_EXPORT_ROOT in BrandWatcher.tsx).
 * - Article files: /api/brand-watcher/brands/{id}/export.
 * Nothing here calls the AI; the summary in the report is the last one saved.
 */

export const BW_EXPORT_ROOT = 'bw-export-root';

export const exportItems = (ctx: BwContext): MenuItem[] => [
  { id: 'html', label: 'Interactive report (HTML)', icon: 'FileText' },
  { id: 'pdf', label: 'Report (PDF)', icon: 'FileText' },
  { id: 'md', label: 'Report (Markdown)', icon: 'NotePencil' },
  { id: 'print', label: 'Print the report', icon: 'FileText' },
  { id: 'png', label: 'This view as an image (PNG)', icon: 'DownloadSimple' },
  { id: 'csv', label: `Articles as CSV${ctx.focusBrand ? ` (${ctx.focusBrand.display_name})` : ''}`, icon: 'Table', disabled: !ctx.focusBrand, separatorBefore: true },
  { id: 'json', label: `Articles as JSON${ctx.focusBrand ? ` (${ctx.focusBrand.display_name})` : ''}`, icon: 'Database', disabled: !ctx.focusBrand },
];

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'all-brands';
const stamp = () => new Date().toISOString().slice(0, 10);

/** The print view: the report text as a plain page, printed by the browser (and "Save as PDF" from there) */
function printReport(win: Window, title: string, markdown: string) {
  const body = renderToStaticMarkup(createElement(Markdown, { text: markdown }));
  win.document.open();
  win.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${title.replace(/</g, '&lt;')}</title>
<style>
  body { font: 13px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; color: #1a1a1a; max-width: 52rem; margin: 2rem auto; padding: 0 1.5rem; }
  h1 { font-size: 1.5rem; } h2 { font-size: 1.15rem; margin-top: 1.6rem; border-bottom: 1px solid #ddd; padding-bottom: .2rem; }
  table { border-collapse: collapse; width: 100%; margin: .5rem 0 1rem; } th, td { border: 1px solid #ccc; padding: .3rem .5rem; text-align: left; vertical-align: top; }
  th { background: #f3f3f3; } a { color: #1a1a1a; } hr { border: 0; border-top: 1px solid #ccc; margin: 1.5rem 0; }
  @media print { body { margin: 0 auto; } a { text-decoration: none; } }
</style></head><body>${body}</body></html>`);
  win.document.close();
  win.focus();
  // Give the browser a moment to lay out the tables before the print dialog
  win.setTimeout(() => win.print(), 300);
}

async function gather(ctx: BwContext) {
  const { bw } = ctx;
  const brand = ctx.focusBrand;
  const days = bw.config.daysBack;
  const bid = brand?.id;
  const topics = bw.config.selectedTopics.length ? bw.config.selectedTopics : undefined;
  const none = <T,>(v: T) => Promise.resolve(v);
  const [comparison, shareOfVoice, trends, alerts, narrative, riskAssessment, incidents] = await Promise.all([
    getComparison(days, topics).catch(() => bw.comparison),
    getShareOfVoice(days, topics).catch(() => bw.shareOfVoice),
    bid ? getSentimentTrends(bid, days).then((r) => r.trends).catch(() => []) : none([]),
    bid ? getBrandAlerts(bid, days).then((r) => r.alerts).catch(() => []) : none([]),
    bid ? getLatestNarrative(bid).catch(() => null) : none(null),
    bid ? getRiskAssessment(bid).catch(() => null) : none(null),
    bid ? listIncidents(undefined, bid).catch(() => []) : none([]),
  ]);
  return { comparison, shareOfVoice, trends, alerts, narrative, riskAssessment, incidents };
}

export async function runExport(id: string, ctx: BwContext) {
  const { bw, notify } = ctx;
  const brand = ctx.focusBrand;
  const days = bw.config.daysBack;
  // The print window must open in the click itself, or the browser blocks it as a pop-up
  const printWin = id === 'print' ? window.open('', '_blank') : null;
  try {
    if (id === 'csv' || id === 'json') {
      if (!brand) return;
      notify(`Preparing the ${id.toUpperCase()} file…`);
      const data = await exportBrandData(brand.id, id, days);
      // The CSV downloads itself; the JSON comes back as data, which the old page dropped
      if (id === 'json') download(`brand_watcher_${brand.name || brand.id}_${stamp()}.json`, JSON.stringify(data, null, 2), 'application/json');
      return;
    }

    if (id === 'png') {
      const el = document.getElementById(BW_EXPORT_ROOT);
      if (!el) throw new Error('The view to capture isn’t on the page.');
      notify('Making the image…');
      await downloadElementPng(el, `brand-watcher-${slug(brand?.display_name ?? 'all')}-${stamp()}.png`);
      return;
    }

    if (id === 'md' || id === 'pdf' || id === 'print') {
      if (id === 'print' && !printWin) throw new Error('The browser blocked the print window. Allow pop-ups for this site and try again.');
      notify('Building the report…');
      const g = await gather(ctx);
      const data: ReportData = {
        brand, daysBack: days, stats: bw.stats, categories: bw.categories, sentimentTrends: g.trends, alerts: g.alerts,
        comparison: g.comparison, shareOfVoice: g.shareOfVoice, narrative: g.narrative, riskAssessment: g.riskAssessment,
        incidents: g.incidents, articles: bw.articles,
      };
      const md = buildReportMarkdown(data);
      const base = `brand-report-${slug(brand?.display_name ?? 'all')}-${stamp()}`;
      if (id === 'md') download(`${base}.md`, md, 'text/markdown');
      else if (id === 'pdf') await downloadPdf({ filename: `${base}.pdf`, title: reportTitle(data), subtitle: reportPeriod(data), markdown: md });
      else printReport(printWin!, reportTitle(data), md);
      return;
    }

    notify('Building the report…');
    const bid = brand?.id;
    const topics = bw.config.selectedTopics.length ? bw.config.selectedTopics : undefined;
    const socialTopics = brand ? [`Brand Monitoring ${brand.display_name}`] : topics;
    const laneTopics = bw.brands.length > 1 ? bw.brands.map((b) => `Brand Monitoring ${b.display_name}`) : undefined;
    const none = <T,>(v: T) => Promise.resolve(v);
    const [g, social, riskSummary, employee, lanePosts, perception, appRatings, appReviews] = await Promise.all([
      gather(ctx),
      getSocialPosts(socialTopics, days, 0, undefined, true, { limit: 5000 }).catch(() => bw.social),
      bid ? getRiskSummary(bid, days).catch(() => null) : none(null),
      bid ? getEmployeeRisk(bid, days).catch(() => null) : none(null),
      laneTopics ? getSocialPosts(laneTopics, days, 0.4, undefined, false, { limit: 2000 }).then((r) => r.posts ?? []).catch(() => []) : none(null),
      getPerception(days).catch(() => null),
      getAllAppRatings().catch(() => null),
      bid ? getAppReviews(bid, { maxStars: 2, daysBack: 30, limit: 8 }).catch(() => null) : none(null),
    ]);
    downloadBrandWatcherReport({
      brand: brand ?? undefined, daysBack: days, stats: bw.stats, categories: bw.categories,
      sentimentTrends: g.trends, alerts: g.alerts, comparison: g.comparison, shareOfVoice: g.shareOfVoice, narrative: g.narrative, social,
      riskSummary, riskAssessment: g.riskAssessment, incidents: g.incidents,
      employee, allBrandPosts: lanePosts, laneBrands: bw.brands.map((b) => b.display_name), perception, appRatings, appReviews,
      generatedAt: new Date().toISOString(),
    } as Parameters<typeof downloadBrandWatcherReport>[0]);
  } catch (e) {
    printWin?.close();
    notify(`Export failed: ${errorText(e)}`);
  }
}
