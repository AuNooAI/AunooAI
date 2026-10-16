import { useEffect, useState } from 'react';
import {
  collapseSentimentTrends, getBrandAlerts, getEmployeeRisk, getRiskAssessment, getRiskSummary, getSentimentTrends, listIncidents,
  type BWAlert, type BWEmployeeRisk, type BWIncident, type BWRiskAssessment, type BWRiskSummary, type BWSentimentBucket, type BWSentimentTrend,
} from '@monolith/brandWatcherApi';
import type { Brand } from '@monolith/brandWatcherApi';

/*
 * What Brand analysis reads for one brand, all stored data (no AI): weekly sentiment, category
 * spikes, risk findings and assessment, incidents, the workforce picture, and competitors' weekly
 * sentiment for the benchmark line. The employee-risk read refreshes a Glassdoor overview older
 * than a day, as on the old page.
 */
export function useAnalysisData(brandId: number | null, daysBack: number, competitors: Brand[]) {
  const [trends, setTrends] = useState<BWSentimentTrend[]>([]);
  const [weekly, setWeekly] = useState<BWSentimentBucket[]>([]);
  const [alerts, setAlerts] = useState<BWAlert[]>([]);
  const [compWeekly, setCompWeekly] = useState<BWSentimentBucket[][]>([]);
  const [employee, setEmployee] = useState<BWEmployeeRisk | null>(null);
  const [riskSummary, setRiskSummary] = useState<BWRiskSummary | null>(null);
  const [assessment, setAssessment] = useState<BWRiskAssessment | null | undefined>(undefined);
  const [incidents, setIncidents] = useState<BWIncident[]>([]);
  const compKey = competitors.map((b) => b.id).join(',');

  useEffect(() => {
    if (!brandId) return;
    let stale = false;
    const set = <T,>(f: (v: T) => void) => (v: T) => !stale && f(v);
    setAssessment(undefined);
    getSentimentTrends(brandId, daysBack).then(
      set((d) => {
        setTrends(d.trends ?? []);
        setWeekly(d.weekly ?? collapseSentimentTrends(d.trends ?? []).weekly);
      }),
      () => undefined,
    );
    getBrandAlerts(brandId).then(set((d) => setAlerts(d.alerts ?? [])), () => setAlerts([]));
    getRiskSummary(brandId, daysBack).then(set(setRiskSummary), () => setRiskSummary(null));
    getRiskAssessment(brandId).then(set(setAssessment), () => setAssessment(null));
    // Only this brand's cases (the old view counted every brand's open incidents)
    listIncidents(undefined, brandId).then(set(setIncidents), () => setIncidents([]));
    getEmployeeRisk(brandId, daysBack).then(set(setEmployee), () => setEmployee(null));
    return () => {
      stale = true;
    };
  }, [brandId, daysBack]);

  useEffect(() => {
    if (!brandId || !competitors.length) {
      setCompWeekly([]);
      return;
    }
    let stale = false;
    Promise.all(
      competitors.map((b) =>
        getSentimentTrends(b.id, daysBack).then((r) => r.weekly ?? collapseSentimentTrends(r.trends ?? []).weekly, () => [] as BWSentimentBucket[]),
      ),
    ).then((w) => !stale && setCompWeekly(w));
    return () => {
      stale = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [brandId, daysBack, compKey]);

  return { trends, weekly, alerts, compWeekly, employee, riskSummary, setRiskSummary, assessment, incidents };
}
