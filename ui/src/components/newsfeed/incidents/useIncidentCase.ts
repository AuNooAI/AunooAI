/**
 * Case-level state for the Brand Watcher incident workspace: the open
 * incident (detail + evidence + timeline), its enrichment state (run, review
 * queue, disposition history), chain verification, and every case mutation.
 *
 * Five Signals polling stays in BrandWatcherTab (the chip cache is shared
 * with the Articles/Overview tabs) — the workspace only calls the passed-in
 * `pollSignals` so a screen started here resolves everywhere.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  BWAccountProfile, listAccountProfiles,
} from '../../../services/socialProfileApi';
import {
  BWAttachSearchResult, BWEnrichmentState, BWIncidentDetail,
  addIncidentNote, attachEnrichmentBrief, attachIncidentEvidence,
  decideEnrichmentCandidates, getIncident, getIncidentEnrichment,
  incidentAttachSearch, startIncidentEnrichment, uploadIncidentFile,
  verifyIncidentChain,
} from '../../../services/brandWatcherApi';

export interface IncidentCase {
  detail: BWIncidentDetail | null;
  setDetail: (d: BWIncidentDetail | null) => void;
  chain: { intact: boolean; items: number; broken_ids: number[] } | null;
  enrich: BWEnrichmentState | null;
  enrichSel: Set<number>;
  setEnrichSel: React.Dispatch<React.SetStateAction<Set<number>>>;
  enrichBusy: boolean;
  briefOpen: boolean;
  setBriefOpen: React.Dispatch<React.SetStateAction<boolean>>;
  noteText: string;
  setNoteText: (s: string) => void;
  evidenceUrl: string;
  setEvidenceUrl: (s: string) => void;
  search: { open: boolean; q: string; kind: 'all' | 'news' | 'social'; results: BWAttachSearchResult[]; sel: Set<string>; busy: boolean; searched: boolean };
  setSearch: React.Dispatch<React.SetStateAction<IncidentCase['search']>>;
  profilePick: { open: boolean; filter: string; profiles: BWAccountProfile[] };
  setProfilePick: React.Dispatch<React.SetStateAction<IncidentCase['profilePick']>>;
  fileBusy: boolean;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  openIncident: (id: number) => void;
  closeIncident: () => void;
  refreshIncident: () => void;
  runVerifyChain: () => void;
  startEnrich: () => Promise<void>;
  decideEnrichSel: (action: 'attach' | 'dismiss') => Promise<void>;
  attachRecommended: () => Promise<void>;
  attachBrief: () => void;
  doAttachSearch: () => Promise<void>;
  attachSearchSelection: () => Promise<void>;
  openProfilePicker: () => void;
  attachProfile: (p: BWAccountProfile) => Promise<void>;
  onFilePicked: (f: globalThis.File | undefined) => Promise<void>;
  captureUrl: () => Promise<void>;
  saveNote: () => void;
}

export function useIncidentCase(opts: {
  reloadIncidents: () => void;
  pollSignals: (uri: string, brandId: number) => void;
}): IncidentCase {
  const { reloadIncidents, pollSignals } = opts;
  const [detail, setDetail] = useState<BWIncidentDetail | null>(null);
  const [chain, setChain] = useState<IncidentCase['chain']>(null);
  const [enrich, setEnrich] = useState<BWEnrichmentState | null>(null);
  const [enrichSel, setEnrichSel] = useState<Set<number>>(new Set());
  const [enrichBusy, setEnrichBusy] = useState(false);
  const [briefOpen, setBriefOpen] = useState(false);
  const [noteText, setNoteText] = useState('');
  const [evidenceUrl, setEvidenceUrl] = useState('');
  const [search, setSearch] = useState<IncidentCase['search']>({ open: false, q: '', kind: 'all', results: [], sel: new Set(), busy: false, searched: false });
  const [profilePick, setProfilePick] = useState<IncidentCase['profilePick']>({ open: false, filter: '', profiles: [] });
  const [fileBusy, setFileBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const openIncident = useCallback((id: number) => {
    setChain(null);
    getIncident(id).then(setDetail).catch(console.error);
  }, []);
  const closeIncident = useCallback(() => { setDetail(null); setChain(null); }, []);
  const refreshIncident = useCallback(() => {
    if (detail) getIncident(detail.id).then(setDetail).catch(console.error);
    reloadIncidents();
  }, [detail, reloadIncidents]);
  const loadEnrichment = useCallback((id: number) => {
    getIncidentEnrichment(id).then(setEnrich).catch(() => setEnrich(null));
  }, []);

  // Load enrichment whenever a case is opened (auto-runs from creation and
  // the monitor surface here without any manual action).
  useEffect(() => {
    setEnrichSel(new Set()); setBriefOpen(false);
    if (detail?.id) loadEnrichment(detail.id); else setEnrich(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail?.id]);

  // Screens the enrichment agent kicked off arrive mid-run: poll any attached
  // article whose Five Signals row is still running so its chip resolves live.
  useEffect(() => {
    if (!detail?.evidence) return;
    for (const ev of detail.evidence) {
      if (ev.evidence_type === 'article' && ev.source_ref
          && ev.signals_summary?.status === 'running') {
        pollSignals(ev.source_ref, detail.brand_id);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail]);

  // Poll while an enrichment run is in progress; refresh the incident once it
  // lands so the agent's timeline events and screens appear.
  useEffect(() => {
    if (!detail?.id || enrich?.run?.status !== 'running') return;
    const id = detail.id;
    const t = setInterval(() => {
      getIncidentEnrichment(id).then(state => {
        setEnrich(state);
        if (state.run && state.run.status !== 'running') getIncident(id).then(setDetail).catch(console.error);
      }).catch(() => {});
    }, 4000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail?.id, enrich?.run?.status]);

  const runVerifyChain = useCallback(() => {
    if (detail) verifyIncidentChain(detail.id).then(setChain).catch(console.error);
  }, [detail]);

  const startEnrich = useCallback(async () => {
    if (!detail) return;
    try {
      await startIncidentEnrichment(detail.id);
      loadEnrichment(detail.id);
    } catch (e) { alert(`${e instanceof Error ? e.message : e}`); }
  }, [detail, loadEnrichment]);

  const decideEnrichSel = useCallback(async (action: 'attach' | 'dismiss') => {
    if (!detail || !enrichSel.size) return;
    setEnrichBusy(true);
    try {
      const res = await decideEnrichmentCandidates(detail.id, Array.from(enrichSel), action);
      if (res.failed?.length) alert(`${res.failed.length} item(s) could not be attached (source no longer available)`);
      setEnrichSel(new Set());
      loadEnrichment(detail.id);
      refreshIncident();
    } catch (e) { console.error(e); alert(`Failed to ${action}: ` + e); }
    finally { setEnrichBusy(false); }
  }, [detail, enrichSel, loadEnrichment, refreshIncident]);

  const attachRecommended = useCallback(async () => {
    if (!detail || !enrich) return;
    const ids = (enrich.candidates || []).filter(c => c.recommendation === 'attach').map(c => c.id);
    if (!ids.length) return;
    setEnrichBusy(true);
    try {
      const res = await decideEnrichmentCandidates(detail.id, ids, 'attach');
      if (res.failed?.length) alert(`${res.failed.length} item(s) could not be attached (source no longer available)`);
      loadEnrichment(detail.id);
      refreshIncident();
    } catch (e) { alert(String(e)); }
    finally { setEnrichBusy(false); }
  }, [detail, enrich, loadEnrichment, refreshIncident]);

  const attachBrief = useCallback(() => {
    if (detail) attachEnrichmentBrief(detail.id).then(refreshIncident).catch(e => alert(String(e)));
  }, [detail, refreshIncident]);

  const doAttachSearch = useCallback(async () => {
    if (!search.q.trim()) return;
    setSearch(s => ({ ...s, busy: true }));
    try {
      const results = await incidentAttachSearch(search.q.trim(), { kind: search.kind, daysBack: 365 });
      setSearch(s => ({ ...s, results, sel: new Set(), busy: false, searched: true }));
    } catch (e) { console.error(e); setSearch(s => ({ ...s, busy: false, searched: true })); }
  }, [search.q, search.kind]);

  const attachSearchSelection = useCallback(async () => {
    if (!detail || !search.sel.size) return;
    setSearch(s => ({ ...s, busy: true }));
    try {
      for (const uri of search.sel) {
        const r = search.results.find(x => x.uri === uri);
        await attachIncidentEvidence(detail.id, { evidence_type: r?.is_social ? 'social_post' : 'article', source_ref: uri });
      }
      setSearch({ open: false, q: '', kind: 'all', results: [], sel: new Set(), busy: false, searched: false });
      refreshIncident();
    } catch (e) { console.error(e); alert('Failed to attach: ' + e); setSearch(s => ({ ...s, busy: false })); }
  }, [detail, search.sel, search.results, refreshIncident]);

  const openProfilePicker = useCallback(() => {
    setProfilePick({ open: true, filter: '', profiles: [] });
    listAccountProfiles().then(profiles => setProfilePick(p => ({ ...p, profiles }))).catch(console.error);
  }, []);

  const attachProfile = useCallback(async (p: BWAccountProfile) => {
    if (!detail) return;
    try {
      await attachIncidentEvidence(detail.id, { evidence_type: 'account_profile', source_ref: `${p.platform}:${p.handle_canonical || p.handle}` });
      setProfilePick({ open: false, filter: '', profiles: [] });
      refreshIncident();
    } catch (e) { console.error(e); alert('Failed to attach profile: ' + e); }
  }, [detail, refreshIncident]);

  const onFilePicked = useCallback(async (f: globalThis.File | undefined) => {
    if (!detail || !f) return;
    setFileBusy(true);
    try {
      await uploadIncidentFile(detail.id, f);
      refreshIncident();
    } catch (e) { alert(`File upload failed: ${e instanceof Error ? e.message : e}`); }
    finally { setFileBusy(false); if (fileInputRef.current) fileInputRef.current.value = ''; }
  }, [detail, refreshIncident]);

  const captureUrl = useCallback(async () => {
    if (!detail || !evidenceUrl.trim()) return;
    const ref = evidenceUrl.trim();
    try {
      try { await attachIncidentEvidence(detail.id, { evidence_type: 'article', source_ref: ref }); }
      catch { await attachIncidentEvidence(detail.id, { evidence_type: 'url', source_ref: ref, title: ref }); }
      setEvidenceUrl(''); refreshIncident();
    } catch (e) { console.error(e); alert('Failed to capture evidence'); }
  }, [detail, evidenceUrl, refreshIncident]);

  const saveNote = useCallback(() => {
    if (!detail || !noteText.trim()) return;
    addIncidentNote(detail.id, noteText.trim()).then(() => { setNoteText(''); refreshIncident(); }).catch(console.error);
  }, [detail, noteText, refreshIncident]);

  return {
    detail, setDetail, chain, enrich, enrichSel, setEnrichSel, enrichBusy,
    briefOpen, setBriefOpen, noteText, setNoteText, evidenceUrl, setEvidenceUrl,
    search, setSearch, profilePick, setProfilePick, fileBusy, fileInputRef,
    openIncident, closeIncident, refreshIncident, runVerifyChain, startEnrich,
    decideEnrichSel, attachRecommended, attachBrief, doAttachSearch,
    attachSearchSelection, openProfilePicker, attachProfile, onFilePicked,
    captureUrl, saveNote,
  };
}
