/**
 * Brand Watcher incident workspace: alert-triage banner + master-detail
 * layout (list rail left, case file right). Replaces the old incidents tab
 * body that lived inline in BrandWatcherTab.tsx.
 *
 * Shared concerns stay in the parent and arrive as props: the incidents
 * list itself (the dashboard KPI reads it), the global Add-to-incident
 * picker (five other tabs open it), Five Signals chips/polling (cache is
 * shared with the Articles tab), and alert data (feeds the header bell).
 */
import { useCallback, useState } from 'react';
import { ShieldAlert } from 'lucide-react';
import {
  BWAlertEvent, BWIncident, createIncident, deleteIncident, updateIncident,
} from '../../../services/brandWatcherApi';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../ui/dialog';
import { useIncidentCase } from './useIncidentCase';
import { IncidentListRail } from './IncidentListRail';
import { IncidentCaseFile } from './IncidentCaseFile';
import { AttachSearchDialog, ProfilePickerDialog } from './AttachModals';

const WORKFLOW_STEPS: [string, string][] = [
  ['Open', 'Start a case from an alert, article or post — or from scratch'],
  ['Investigate', 'AI sweeps for coverage, checks who is spreading it and how credible it is'],
  ['Accept', 'One click folds the AI findings into the case; reject anything off-target'],
  ['Assess', 'Coverage, reach, accounts and credibility in one view — set severity accordingly'],
  ['Resolve', 'Close it out and export the case file (HTML / PDF / Markdown)'],
];

export function IncidentsWorkspace(props: {
  incidents: BWIncident[];
  incidentsLoading: boolean;
  reloadIncidents: () => void;
  brands: { id: number; display_name: string }[];
  defaultBrandId: number | null;
  alertEvents: BWAlertEvent[];
  onAckAlert: (id: number) => void;
  onCaseAlert: (ev: BWAlertEvent) => void;
  renderSignalsChips: (article: any) => React.ReactNode;
  pollSignals: (uri: string, brandId: number) => void;
}) {
  const { incidents, incidentsLoading, reloadIncidents, brands, defaultBrandId,
          alertEvents, onAckAlert, onCaseAlert, renderSignalsChips, pollSignals } = props;

  const c = useIncidentCase({ reloadIncidents, pollSignals });
  const [statusFilter, setStatusFilter] = useState('');
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulk, setBulk] = useState({ status: '', severity: '', owner: '' });
  const [bulkBusy, setBulkBusy] = useState(false);
  const [create, setCreate] = useState({ open: false, title: '', description: '', severity: 'medium', brandId: null as number | null });
  const [alertsOpen, setAlertsOpen] = useState<boolean | null>(null); // alerts strip in the rail

  const applyBulk = useCallback(async (action: 'update' | 'delete') => {
    const ids = Array.from(selected);
    if (!ids.length) return;
    if (action === 'delete' && !window.confirm(`Delete ${ids.length} incident${ids.length > 1 ? 's' : ''}? Events and evidence are removed with them.`)) return;
    setBulkBusy(true);
    try {
      for (const id of ids) {
        if (action === 'delete') {
          await deleteIncident(id);
          if (c.detail?.id === id) c.setDetail(null);
        } else {
          const updates: Record<string, string> = {};
          if (bulk.status) updates.status = bulk.status;
          if (bulk.severity) updates.severity = bulk.severity;
          if (bulk.owner.trim()) updates.owner = bulk.owner.trim();
          if (Object.keys(updates).length) await updateIncident(id, updates);
        }
      }
      setSelected(new Set());
      setBulk({ status: '', severity: '', owner: '' });
      reloadIncidents();
      if (action === 'update' && c.detail && ids.includes(c.detail.id)) c.openIncident(c.detail.id);
    } catch (err) {
      console.error('Bulk incident action failed:', err);
    } finally {
      setBulkBusy(false);
    }
  }, [selected, bulk, c, reloadIncidents]);

  const doCreate = useCallback(async () => {
    if (!create.title.trim() || !create.brandId) return;
    try {
      const r = await createIncident(create.brandId, create.title.trim(), create.description || undefined, create.severity);
      setCreate(cr => ({ ...cr, open: false }));
      reloadIncidents();
      c.openIncident(r.id);
    } catch (e) { console.error(e); alert('Failed to create incident'); }
  }, [create, reloadIncidents, c]);

  return (
    <div className="space-y-4">
      <div className="flex gap-4 items-start">
        <div className={`w-full lg:w-[340px] lg:shrink-0 ${c.detail ? 'hidden lg:block' : ''}`}>
          <IncidentListRail
            incidents={incidents} loading={incidentsLoading}
            statusFilter={statusFilter} setStatusFilter={setStatusFilter}
            activeId={c.detail?.id ?? null} onOpen={c.openIncident}
            onNew={() => setCreate({ open: true, title: '', description: '', severity: 'medium', brandId: defaultBrandId })}
            selected={selected} setSelected={setSelected}
            bulk={bulk} setBulk={setBulk} bulkBusy={bulkBusy} applyBulk={applyBulk}
            alertEvents={alertEvents} onAckAlert={onAckAlert} onCaseAlert={onCaseAlert}
            alertsOpen={alertsOpen ?? false} setAlertsOpen={setAlertsOpen} />
        </div>

        <div className={`flex-1 min-w-0 ${!c.detail ? 'hidden lg:block' : ''}`}>
          {c.detail ? (
            <IncidentCaseFile c={c} renderSignalsChips={renderSignalsChips} showBack />
          ) : (
            <div className="rounded-lg border border-dashed border-gray-300 dark:border-gray-600 p-8">
              {incidents.length === 0 && !incidentsLoading ? (
                <div className="max-w-md mx-auto space-y-4">
                  <h3 className="text-base font-semibold text-gray-800 dark:text-gray-100 inline-flex items-center gap-2">
                    <ShieldAlert className="w-5 h-5 text-red-400" /> Incident case management
                  </h3>
                  <div className="space-y-2.5">
                    {WORKFLOW_STEPS.map(([step, blurb]) => (
                      <div key={step} className="flex items-start gap-3">
                        <span className="text-xs font-semibold text-blue-600 dark:text-blue-400 w-20 flex-shrink-0">{step}</span>
                        <span className="text-xs text-gray-500 dark:text-gray-400">{blurb}</span>
                      </div>
                    ))}
                  </div>
                  <p className="text-xs text-gray-400">Start with “New incident” on the left, or promote any article, post, profile or alert via its “Add to incident” action.</p>
                </div>
              ) : (
                <p className="text-sm text-gray-400 text-center py-10">Select a case to work it — evidence, agent findings and timeline live there.</p>
              )}
            </div>
          )}
        </div>
      </div>

      <AttachSearchDialog c={c} />
      <ProfilePickerDialog c={c} />

      <Dialog open={create.open} onOpenChange={open => setCreate(cr => ({ ...cr, open }))}>
        <DialogContent className="max-w-md z-[1100]">
          <DialogHeader><DialogTitle className="text-base">New incident</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <select value={create.brandId ?? ''} onChange={e => setCreate(cr => ({ ...cr, brandId: Number(e.target.value) }))}
              className="w-full text-sm px-2 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200">
              {brands.map(b => <option key={b.id} value={b.id}>{b.display_name}</option>)}
            </select>
            <input type="text" value={create.title} onChange={e => setCreate(cr => ({ ...cr, title: e.target.value }))} placeholder="Title"
              className="w-full text-sm px-2 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200" />
            <textarea value={create.description} onChange={e => setCreate(cr => ({ ...cr, description: e.target.value }))} placeholder="Description — what is this incident? (leave blank and the agent drafts one from the evidence)" rows={3}
              className="w-full text-sm px-2 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200" />
            <div className="flex items-center gap-2">
              <label className="text-xs text-gray-500">Severity</label>
              <select value={create.severity} onChange={e => setCreate(cr => ({ ...cr, severity: e.target.value }))}
                className="text-sm px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200">
                {['low', 'medium', 'high', 'critical'].map(sv => <option key={sv} value={sv}>{sv}</option>)}
              </select>
              <span className="flex-1" />
              <button disabled={!create.title.trim() || !create.brandId} onClick={doCreate}
                className="text-sm px-4 py-1.5 rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50">Create</button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
