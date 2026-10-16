import { api } from '../../shell';

/*
 * The site's own scheduled jobs (emerging topics, the news feed dashboard, article collection,
 * GeoHotSpots), shown beside the agents' schedules, as on the old section. Each read only reports
 * the schedule's state. A dedicated Brand Watcher site skips them: they're plumbing a brand team
 * doesn't act on.
 */

export type SystemType = 'emerging_topics' | 'newsfeed' | 'autoprocessing' | 'geopolitical';

export interface SystemSchedule {
  name: string;
  type: SystemType;
  next_run_at: string | null;
  last_run_at: string | null;
  last_run_status: string | null;
}

interface EtStatus { settings?: { schedule_enabled?: boolean }; status?: { next_check_time?: string; last_check_time?: string; last_error?: string; topics_detected?: number | null } }
interface NfStatus { settings?: { schedule_enabled?: boolean }; status?: { next_run_time?: string; last_run_time?: string; last_run_status?: string } }
interface KmSettings { is_enabled?: boolean; next_run_time?: string; last_run_time?: string }
interface GeoSchedules { schedules?: { name?: string; schedule_enabled?: boolean; next_run_at?: string; last_run_at?: string; last_run_status?: string }[] }

const quiet = <T,>(p: Promise<T>) => p.catch(() => null);

export async function loadSystemSchedules(): Promise<SystemSchedule[]> {
  const [et, nf, km, geo] = await Promise.all([
    quiet(api<EtStatus>('/api/emerging-topics/schedule/status')),
    quiet(api<NfStatus>('/api/news-feed/dashboard/schedule/status')),
    quiet(api<KmSettings>('/api/keyword-monitor/settings')),
    quiet(api<GeoSchedules>('/api/geopolitical-hotspots/schedules')),
  ]);
  const out: SystemSchedule[] = [];
  if (et?.settings?.schedule_enabled) {
    out.push({
      name: 'Emerging topics', type: 'emerging_topics',
      next_run_at: et.status?.next_check_time ?? null, last_run_at: et.status?.last_check_time ?? null,
      last_run_status: et.status?.last_error ? 'error' : et.status?.topics_detected != null ? 'success' : null,
    });
  }
  if (nf?.settings?.schedule_enabled) {
    out.push({
      name: 'News feed dashboard', type: 'newsfeed',
      next_run_at: nf.status?.next_run_time ?? null, last_run_at: nf.status?.last_run_time ?? null, last_run_status: nf.status?.last_run_status ?? null,
    });
  }
  if (km?.is_enabled) {
    out.push({ name: 'Article collection', type: 'autoprocessing', next_run_at: km.next_run_time ?? null, last_run_at: km.last_run_time ?? null, last_run_status: null });
  }
  for (const s of geo?.schedules ?? []) {
    if (s.schedule_enabled) {
      out.push({ name: s.name || 'GeoHotSpots', type: 'geopolitical', next_run_at: s.next_run_at ?? null, last_run_at: s.last_run_at ?? null, last_run_status: s.last_run_status ?? null });
    }
  }
  return out;
}

/** "in 3 h", "14:30", "12 Oct, 09:00" or "5 days ago", as the old table did */
export function when(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const diffH = (d.getTime() - Date.now()) / 3_600_000;
  if (diffH < 0) {
    const ago = -diffH;
    if (ago < 1) return `${Math.max(1, Math.round(ago * 60))} min ago`;
    if (ago < 48) return `${Math.round(ago)} h ago`;
    return `${Math.round(ago / 24)} days ago`;
  }
  const time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  return diffH < 24 ? time : `${d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}, ${time}`;
}
