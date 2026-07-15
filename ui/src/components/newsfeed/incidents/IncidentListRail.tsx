/**
 * Left rail of the incident workspace: client-side status filter with live
 * counts, compact case cards, and a bulk-action bar that appears when any
 * card is checkbox-selected.
 */
import { Bell, ChevronDown, ChevronRight, Lock, Plus } from 'lucide-react';
import { BWAlertEvent, BWIncident } from '../../../services/brandWatcherApi';
import { INCIDENT_STATUSES } from './StatusStepper';

const SEV_DOT: Record<string, string> = {
  low: 'bg-gray-400', medium: 'bg-amber-400', high: 'bg-red-500', critical: 'bg-red-700',
};
const STATUS_BADGE: Record<string, string> = {
  open: 'bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400',
  investigating: 'bg-amber-50 text-amber-600 dark:bg-amber-900/20 dark:text-amber-400',
  contained: 'bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400',
  resolved: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400',
  closed: 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400',
};

function ago(iso?: string | null): string {
  if (!iso) return '';
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  return d <= 0 ? 'today' : d === 1 ? '1d ago' : `${d}d ago`;
}

export function IncidentListRail(props: {
  incidents: BWIncident[];
  loading: boolean;
  statusFilter: string;
  setStatusFilter: (s: string) => void;
  activeId: number | null;
  onOpen: (id: number) => void;
  onNew: () => void;
  selected: Set<number>;
  setSelected: React.Dispatch<React.SetStateAction<Set<number>>>;
  bulk: { status: string; severity: string; owner: string };
  setBulk: React.Dispatch<React.SetStateAction<{ status: string; severity: string; owner: string }>>;
  bulkBusy: boolean;
  applyBulk: (action: 'update' | 'delete') => void;
  alertEvents: BWAlertEvent[];
  onAckAlert: (id: number) => void;
  onCaseAlert: (ev: BWAlertEvent) => void;
  alertsOpen: boolean;
  setAlertsOpen: (open: boolean) => void;
}) {
  const { incidents, loading, statusFilter, setStatusFilter, activeId, onOpen, onNew,
          selected, setSelected, bulk, setBulk, bulkBusy, applyBulk,
          alertEvents, onAckAlert, onCaseAlert, alertsOpen, setAlertsOpen } = props;
  const ACTIVE = ['open', 'investigating', 'contained'];
  const counts: Record<string, number> = {
    active: incidents.filter(i => ACTIVE.includes(i.status)).length,
    '': incidents.length,
  };
  for (const st of INCIDENT_STATUSES) counts[st] = incidents.filter(i => i.status === st).length;
  const shown = statusFilter === 'active' ? incidents.filter(i => ACTIVE.includes(i.status))
    : statusFilter ? incidents.filter(i => i.status === statusFilter) : incidents;

  return (
    <div className="space-y-3">
      {alertEvents.length > 0 && (
        <div className="rounded-lg border border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 overflow-hidden">
          <button onClick={() => setAlertsOpen(!alertsOpen)} className="w-full flex items-center gap-2 px-2.5 py-2 text-left">
            <Bell className="w-4 h-4 text-amber-600 flex-shrink-0" />
            <span className="text-xs font-medium text-amber-800 dark:text-amber-200 flex-1">
              {alertEvents.length} new alert{alertEvents.length > 1 ? 's' : ''} — triage
            </span>
            {alertsOpen ? <ChevronDown className="w-4 h-4 text-amber-500" /> : <ChevronRight className="w-4 h-4 text-amber-500" />}
          </button>
          {alertsOpen && (
            <div className="px-2 pb-2 space-y-1.5">
              {alertEvents.map(ev => (
                <div key={`inc-ev-${ev.id}`} className="rounded-md border border-amber-200 dark:border-amber-800 bg-white dark:bg-gray-800 p-2">
                  <div className="flex items-start gap-1.5">
                    <span className={`w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${ev.severity === 'high' ? 'bg-red-500' : 'bg-amber-400'}`} />
                    <span className="text-xs text-gray-800 dark:text-gray-100 flex-1">{ev.title}</span>
                  </div>
                  <div className="flex items-center gap-1.5 mt-1.5 pl-3">
                    <button onClick={() => onCaseAlert(ev)}
                      title="Open a case from this alert (or add it to an existing one)"
                      className="text-[10px] px-1.5 py-0.5 rounded border border-blue-300 dark:border-blue-700 text-blue-600 dark:text-blue-400 hover:bg-blue-50">Open case</button>
                    <button onClick={() => onAckAlert(ev.id)}
                      title="Acknowledge — no case needed"
                      className="text-[10px] px-1.5 py-0.5 rounded border border-gray-300 dark:border-gray-600 text-gray-500 hover:text-gray-700">Dismiss</button>
                    <span className="text-[10px] text-gray-400 ml-auto">{(ev.created_at || '').slice(5, 16).replace('T', ' ')}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      <button onClick={onNew}
        className="w-full text-sm px-3 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 inline-flex items-center justify-center gap-1.5 font-medium">
        <Plus className="w-4 h-4" /> New incident
      </button>
      <div className="flex items-center gap-1 flex-wrap">
        {['active', '', ...INCIDENT_STATUSES].map(st => (
          <button key={st || 'all'} onClick={() => setStatusFilter(st)}
            className={`text-xs px-2 py-0.5 rounded-full border ${statusFilter === st
              ? 'bg-blue-600 text-white border-blue-600'
              : 'bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400 border-gray-300 dark:border-gray-600 hover:border-blue-300'}`}>
            {st === 'active' ? 'active' : st || 'all'}{counts[st] ? ` ${counts[st]}` : st === 'active' || !st ? ' 0' : ''}
          </button>
        ))}
      </div>

      {selected.size > 0 && (
        <div className="p-2 rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50/50 dark:bg-blue-900/10 space-y-1.5 text-xs">
          <div className="flex items-center justify-between">
            <span className="font-medium text-gray-700 dark:text-gray-200">{selected.size} selected</span>
            <button onClick={() => setSelected(new Set())} className="text-gray-400 hover:text-gray-600">clear</button>
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            <select value={bulk.status} onChange={e => setBulk(b => ({ ...b, status: e.target.value }))}
              className="px-1.5 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 dark:text-gray-200">
              <option value="">status…</option>
              {INCIDENT_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <select value={bulk.severity} onChange={e => setBulk(b => ({ ...b, severity: e.target.value }))}
              className="px-1.5 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 dark:text-gray-200">
              <option value="">severity…</option>
              {['low', 'medium', 'high', 'critical'].map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <input type="text" value={bulk.owner} placeholder="owner…"
              onChange={e => setBulk(b => ({ ...b, owner: e.target.value }))}
              className="w-20 px-1.5 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 dark:text-gray-200" />
          </div>
          <div className="flex items-center gap-1.5">
            <button onClick={() => applyBulk('update')}
              disabled={bulkBusy || (!bulk.status && !bulk.severity && !bulk.owner.trim())}
              title="Apply the chosen status/severity/owner to every selected incident (each change lands in the incident timeline)"
              className="px-2.5 py-1 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40">
              {bulkBusy ? 'Applying…' : 'Apply'}
            </button>
            <button onClick={() => applyBulk('delete')} disabled={bulkBusy}
              title="Delete every selected incident, including its timeline and evidence"
              className="px-2.5 py-1 rounded border border-red-300 dark:border-red-700 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-40">
              Delete
            </button>
          </div>
        </div>
      )}

      {loading && <p className="text-xs text-gray-400 py-4 text-center">Loading…</p>}
      {!loading && shown.length === 0 && (
        <p className="text-xs text-gray-400 py-4 text-center px-2">
          {statusFilter ? `No ${statusFilter} incidents.` : 'No incidents yet.'}
        </p>
      )}
      <div className="space-y-1.5">
        {shown.map(inc => (
          <div key={inc.id}
            className={`relative rounded-lg border transition-colors ${activeId === inc.id
              ? 'border-blue-400 bg-blue-50/60 dark:bg-blue-900/15'
              : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:border-blue-300'}`}>
            <button onClick={() => onOpen(inc.id)} className="w-full text-left p-2.5 pr-8">
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full flex-shrink-0 ${SEV_DOT[inc.severity] || SEV_DOT.medium}`}
                  title={`severity: ${inc.severity}`} />
                <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">#{inc.id} {inc.title}</span>
              </div>
              <div className="flex items-center gap-2 mt-1 text-xs text-gray-400">
                <span className={`px-1.5 py-0.5 rounded-full text-[10px] ${STATUS_BADGE[inc.status] || STATUS_BADGE.closed}`}>{inc.status}</span>
                <span className="truncate">{inc.brand_name}</span>
                <span className="flex-1" />
                <span className="inline-flex items-center gap-0.5" title={`${inc.evidence_count} evidence item(s)`}>
                  <Lock className="w-3 h-3" /> {inc.evidence_count}</span>
                <span>{ago(inc.updated_at)}</span>
              </div>
            </button>
            <input type="checkbox" checked={selected.has(inc.id)}
              onChange={e => setSelected(prev => {
                const next = new Set(prev);
                if (e.target.checked) next.add(inc.id); else next.delete(inc.id);
                return next;
              })}
              onClick={e => e.stopPropagation()}
              className="absolute top-2.5 right-2.5" title="Select for bulk action" />
          </div>
        ))}
      </div>
    </div>
  );
}
