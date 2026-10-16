import type { ChartColor } from '@aunoo/ui';
import type { ActorType, SeverityLevel } from './api';

/* Labels and colours shared by the Threat Intelligence views, from the old threatIntelligenceApi.ts */

export const THREAT_CATEGORIES = [
  'malware', 'ransomware', 'apt', 'phishing', 'vulnerability', 'data_breach', 'botnet', 'ddos',
  'supply_chain', 'credential_theft', 'cryptojacking', 'insider_threat', 'iot_ot', 'mobile',
] as const;

const CATEGORY_LABELS: Record<string, string> = {
  malware: 'Malware', ransomware: 'Ransomware', apt: 'APT (state-backed group)', phishing: 'Phishing',
  vulnerability: 'Vulnerability', data_breach: 'Data breach', botnet: 'Botnet', ddos: 'DDoS',
  supply_chain: 'Supply chain', credential_theft: 'Credential theft', cryptojacking: 'Cryptojacking',
  insider_threat: 'Insider threat', iot_ot: 'IoT and industrial systems', mobile: 'Mobile',
};
export const categoryLabel = (c: string | null | undefined) => (c ? CATEGORY_LABELS[c] ?? c.replace(/_/g, ' ') : 'Unknown type');

export const SEVERITY_LEVELS: SeverityLevel[] = ['critical', 'high', 'medium', 'low', 'info'];
export const SEVERITY_LABELS: Record<SeverityLevel, string> = { critical: 'Critical', high: 'High', medium: 'Medium', low: 'Low', info: 'Information only' };
export const severityLabel = (s: string | null | undefined) => (s ? SEVERITY_LABELS[s as SeverityLevel] ?? s : 'Unknown');

type ChipTone = 'error' | 'warning' | 'info' | 'muted' | 'neutral';
export const SEVERITY_TONE: Record<SeverityLevel, ChipTone> = { critical: 'error', high: 'warning', medium: 'neutral', low: 'muted', info: 'info' };
export const severityTone = (s: string | null | undefined): ChipTone => SEVERITY_TONE[s as SeverityLevel] ?? 'muted';
export const SEVERITY_CHART: Record<SeverityLevel, ChartColor> = { critical: 'negative', high: 'caution', medium: 3, low: 'positive', info: 1 };

/** The score bands the old page used to name a 0-100 average severity */
export function scoreBand(score: number): SeverityLevel {
  if (score >= 80) return 'critical';
  if (score >= 60) return 'high';
  if (score >= 40) return 'medium';
  if (score >= 20) return 'low';
  return 'info';
}

export const ACTOR_TYPES: ActorType[] = ['nation_state', 'cybercrime', 'hacktivist', 'insider', 'script_kiddie', 'unknown'];
export const ACTOR_TYPE_LABELS: Record<ActorType, string> = {
  nation_state: 'Nation state', cybercrime: 'Cybercrime', hacktivist: 'Hacktivist', insider: 'Insider',
  script_kiddie: 'Low-skill attacker', unknown: 'Unknown',
};
export const actorTypeLabel = (t: string | null | undefined) => (t ? ACTOR_TYPE_LABELS[t as ActorType] ?? t : 'Unknown');

export const IOC_TYPE_LABELS: Record<string, string> = {
  ip: 'IP address', domain: 'Domain', hash_md5: 'MD5 hash', hash_sha256: 'SHA-256 hash', hash_sha1: 'SHA-1 hash',
  url: 'URL', email: 'Email address', cve: 'CVE',
};
export const iocTypeLabel = (t: string) => IOC_TYPE_LABELS[t] ?? t;

export const TREND_LABELS: Record<string, string> = { escalating: 'Escalating', stable: 'Stable', declining: 'Declining' };

export const PERIOD_OPTIONS = [
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
  { value: '180', label: 'Last 6 months' },
  { value: '365', label: 'Last year' },
];

export const fmtDate = (d: string | null | undefined) => {
  if (!d) return '—';
  const t = new Date(d);
  return Number.isNaN(t.getTime()) ? d : t.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
};
export const fmtDay = (d: string) => {
  const t = new Date(d);
  return Number.isNaN(t.getTime()) ? d : t.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
};
export const fmtDateTime = (d: string | null | undefined) => {
  if (!d) return 'never';
  const t = new Date(d);
  return Number.isNaN(t.getTime()) ? d : t.toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
};
