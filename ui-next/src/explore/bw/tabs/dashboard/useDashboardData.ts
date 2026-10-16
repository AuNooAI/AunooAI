import { useCallback, useEffect, useState } from 'react';
import {
  collapseSentimentTrends, getAppRatings, getArticles, getBrandAlerts, getEmployeeRisk, getRiskAssessment, getSentimentTrends, getSocialPosts, listIncidents,
  type BWAlert, type BWAppRatings, type BWArticle, type BWEmployeeRisk, type BWIncident, type BWRiskAssessment, type BWSentimentBucket,
  type BWSentimentTrendsResponse, type BWSocialPost,
} from '@monolith/brandWatcherApi';
import { getAccountProfile, type BWAccountProfile } from '@monolith/socialProfileApi';
import type { BwContext } from '../../context';
import { fansAndCritics, sentimentOf, socialBrandOf } from './helpers';

/*
 * What the dashboard loads on top of the shared Brand Watcher data, as the old tab did when the
 * dashboard opened. Nothing here calls an AI model. Brand-specific parts (sentiment trends, spike
 * alerts, risk, workforce, app ratings) load only when exactly one brand is picked in the header,
 * as on the old page ("primarySelectedId" = the first picked brand).
 */

export type SocialScope = 'selected' | 'all';

const weeklyOf = (d: BWSentimentTrendsResponse) => {
  const fallback = d.weekly && d.totals ? null : collapseSentimentTrends(d.trends || []);
  return { weekly: d.weekly ?? fallback!.weekly, totals: d.totals ?? fallback!.totals };
};

export function useDashboardData(ctx: BwContext, scope: SocialScope) {
  const { bw, selectedBrands } = ctx;
  const { brands, config } = bw;
  const primaryId = config.selectedBrandIds[0] ?? null;
  const days = config.daysBack;
  const brandIdsKey = config.selectedBrandIds.join(',');
  const topicsKey = config.selectedTopics.join(',');

  const [weekly, setWeekly] = useState<BWSentimentBucket[]>([]);
  const [totals, setTotals] = useState<Record<string, number>>({});
  const [hasTrends, setHasTrends] = useState(false);
  const [alerts, setAlerts] = useState<BWAlert[]>([]);
  const [risk, setRisk] = useState<BWRiskAssessment | null>(null);
  const [employee, setEmployee] = useState<BWEmployeeRisk | null>(null);
  const [apps, setApps] = useState<BWAppRatings | null>(null);
  const [incidents, setIncidents] = useState<BWIncident[]>([]);
  const [pool, setPool] = useState<BWArticle[] | null>(null);
  const [social, setSocial] = useState<BWSocialPost[] | null>(null);
  const [loadingSocial, setLoadingSocial] = useState(false);
  const [benchPosts, setBenchPosts] = useState<BWSocialPost[] | null>(null);
  const [compWeekly, setCompWeekly] = useState<BWSentimentBucket[][]>([]);
  const [profiles, setProfiles] = useState<Record<string, BWAccountProfile | 'missing'>>({});

  const loadIncidents = useCallback(() => {
    listIncidents().then(setIncidents, () => setIncidents([]));
  }, []);

  // Comparison feeds the sentiment-by-brand chart and the competitor benchmark
  useEffect(() => {
    void bw.fetchComparison();
    loadIncidents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days, topicsKey]);

  // Brand-specific: trends, spike alerts, risk
  useEffect(() => {
    setRisk(null);
    if (!primaryId) {
      setWeekly([]); setTotals({}); setHasTrends(false); setAlerts([]);
      return;
    }
    let stale = false;
    getSentimentTrends(primaryId, days).then((d) => {
      if (stale) return;
      const w = weeklyOf(d);
      setWeekly(w.weekly); setTotals(w.totals); setHasTrends((d.trends || []).length > 0);
    }, () => undefined);
    getBrandAlerts(primaryId).then((d) => !stale && setAlerts(d.alerts), () => undefined);
    getRiskAssessment(primaryId).then((r) => !stale && setRisk(r), () => undefined);
    return () => { stale = true; };
  }, [primaryId, days]);

  // Workforce (Glassdoor aggregates cached 24 h server-side) and app ratings: once per brand
  useEffect(() => {
    if (!primaryId) { setEmployee(null); setApps(null); return; }
    let stale = false;
    getEmployeeRisk(primaryId, days).then((e) => !stale && setEmployee(e), () => !stale && setEmployee(null));
    getAppRatings(primaryId).then((a) => !stale && setApps(a), () => !stale && setApps(null));
    return () => { stale = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [primaryId]);

  // Competitors' weekly news sentiment, for the benchmark line
  useEffect(() => {
    if (!primaryId) { setCompWeekly([]); return; }
    const comps = brands.filter((b) => b.enabled && b.id !== primaryId);
    if (!comps.length) { setCompWeekly([]); return; }
    let stale = false;
    void Promise.all(comps.map((b) => getSentimentTrends(b.id, days).then((r) => weeklyOf(r).weekly, () => [] as BWSentimentBucket[])))
      .then((r) => !stale && setCompWeekly(r));
    return () => { stale = true; };
  }, [primaryId, days, brands]);

  // A wider article pool (up to 200) for the adverse breakdowns; the shared list is one page
  useEffect(() => {
    let stale = false;
    getArticles({
      brand_ids: config.selectedBrandIds.length ? config.selectedBrandIds : undefined,
      topics: config.selectedTopics.length ? config.selectedTopics : undefined,
      days_back: days, page: 1, per_page: 200,
    }).then((r) => !stale && setPool(r.articles), () => undefined);
    return () => { stale = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [brandIdsKey, topicsKey, days]);

  // On-brand social posts for the chosen scope. "Selected" means the picked brands, else the
  // primary brand, so it never silently widens to every brand.
  useEffect(() => {
    if (!brands.length) return;
    const focus = selectedBrands.length ? selectedBrands : [brands.find((b) => b.is_primary) || brands[0]].filter(Boolean);
    const topics = (scope === 'all' ? brands : focus).map((b) => `Brand Monitoring ${b.display_name}`);
    let stale = false;
    setLoadingSocial(true);
    getSocialPosts(topics, days, 0.4, undefined, false, { limit: 500 })
      .then((d) => !stale && setSocial((d.posts || []).filter((p) => p.review_status !== 'false_positive')), () => !stale && setSocial([]))
      .finally(() => !stale && setLoadingSocial(false));
    return () => { stale = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope, brandIdsKey, days, brands.length]);

  // All-brands snapshot for "you against the competitor average", whatever the scope
  useEffect(() => {
    if (brands.length < 2) { setBenchPosts(null); return; }
    let stale = false;
    getSocialPosts(brands.map((b) => `Brand Monitoring ${b.display_name}`), days, 0.4, undefined, false, { limit: 2000 })
      .then((d) => !stale && setBenchPosts(d.posts || []), () => !stale && setBenchPosts(null));
    return () => { stale = true; };
  }, [brands, days]);

  const fc = fansAndCritics(social ?? [], brands);
  const fcKey = [...fc.critics.slice(0, 5), ...fc.fans.slice(0, 5)].map((a) => `${a.platform}:${a.author.toLowerCase()}`).join('|');

  // Stored account profiles for the top fans and critics (read only). The old page also built
  // missing profiles in the background, a paid lookup per account; that now happens only from
  // the Accounts tab.
  useEffect(() => {
    let stale = false;
    const targets = [...fc.critics.slice(0, 5), ...fc.fans.slice(0, 5)].filter((a) => ['twitter', 'bluesky', 'reddit', 'instagram', 'tiktok'].includes(a.platform));
    for (const t of targets) {
      const key = `${t.platform}:${t.author.toLowerCase()}`;
      if (profiles[key]) continue;
      getAccountProfile(t.platform, t.author).then(
        (p) => !stale && setProfiles((x) => ({ ...x, [key]: p })),
        () => !stale && setProfiles((x) => ({ ...x, [key]: 'missing' })),
      );
    }
    return () => { stale = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fcKey]);

  // Social sentiment per competitor brand (focus brand left out by the caller)
  const benchByBrand: Record<string, { pos: number; neg: number; scored: number }> = {};
  for (const p of benchPosts ?? []) {
    const s = sentimentOf(p.sentiment);
    if (s === 'unrated') continue;
    const b = (benchByBrand[socialBrandOf(p)] ||= { pos: 0, neg: 0, scored: 0 });
    if (s === 'positive') b.pos++;
    else if (s === 'negative') b.neg++;
    b.scored++;
  }

  return {
    primaryId, weekly, totals, hasTrends, alerts, risk, employee, apps, incidents, loadIncidents,
    pool, social, loadingSocial, benchPosts, benchByBrand, compWeekly, fc, profiles,
  };
}

export type DashboardData = ReturnType<typeof useDashboardData>;
