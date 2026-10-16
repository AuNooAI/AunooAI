import { useCallback, useEffect, useState } from 'react';
import {
  acknowledgeAlert, acknowledgeAllAlerts, createResearchAgent, deleteResearchAgent, getResearchAgents, getSignalAlerts,
  getSignalRunStatus, runResearchAgents, updateResearchAgent,
  type CreateAgentRequest, type PodcastSummary, type ResearchAgent, type SignalAlert, type UpdateAgentRequest,
} from '@monolith/researchAgentsApi';
import { errorText } from '../../shell';

/*
 * Observer agents and their unread matches, as the old ui/src/hooks/useResearchAgents.ts. Loading
 * only reads. Running an agent calls the AI and is started by the reader; a run happens in the
 * background on the server and this polls its status until it finishes.
 */

export interface RunOptions {
  topic?: string;
  daysBack?: number;
  tagArticles?: boolean;
  generateUnifiedReport?: boolean;
}

const POLL_MS = 3000;
const MAX_WAIT_MS = 15 * 60 * 1000;
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const messageOf = (m: unknown, fallback: string) => (typeof m === 'string' && m ? m : fallback);

export function useResearchAgents(topic: string | undefined, notify: (m: string) => void) {
  const [agents, setAgents] = useState<ResearchAgent[]>([]);
  const [alerts, setAlerts] = useState<SignalAlert[]>([]);
  const [podcasts, setPodcasts] = useState<PodcastSummary[]>([]);
  const [saving, setSaving] = useState(false);
  const [loadingAgents, setLoadingAgents] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [running, setRunning] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const fetchAgents = useCallback(async () => {
    setLoadingAgents(true);
    try {
      const r = await getResearchAgents({ topic, activeOnly: false });
      setAgents(r.instructions || []);
    } catch (e) {
      setError(`Agents didn’t load: ${errorText(e)}`);
    } finally {
      setLoadingAgents(false);
      setLoaded(true);
    }
  }, [topic]);

  // Only unread matches; they're secondary, so a failure here stays quiet as before
  const fetchAlerts = useCallback(async () => {
    try {
      const r = await getSignalAlerts({ topic, acknowledged: false, limit: 100 });
      setAlerts(r.alerts || []);
    } catch {
      // keep what we have
    }
  }, [topic]);

  useEffect(() => {
    void fetchAgents();
    void fetchAlerts();
  }, [fetchAgents, fetchAlerts]);

  const save = async (work: () => Promise<unknown>, what: string) => {
    setSaving(true);
    setError(null);
    try {
      await work();
      await fetchAgents();
      return true;
    } catch (e) {
      setError(`${what}: ${errorText(e)}`);
      return false;
    } finally {
      setSaving(false);
    }
  };
  const addAgent = (a: CreateAgentRequest) => save(() => createResearchAgent(a), 'The agent wasn’t created');
  const updateAgent = (id: number, u: UpdateAgentRequest) => save(() => updateResearchAgent(id, u), 'The agent wasn’t saved');

  const removeAgent = async (id: number) => {
    setError(null);
    try {
      await deleteResearchAgent(id);
      setAgents((p) => p.filter((a) => a.id !== id));
      setAlerts((p) => p.filter((a) => a.instruction_id !== id));
      return true;
    } catch (e) {
      setError(`The agent wasn’t deleted: ${errorText(e)}`);
      return false;
    }
  };

  // A run keeps going on the server even if this stops polling; matches arrive by email too
  const pollRun = async (runId: string) => {
    const start = Date.now();
    while (Date.now() - start < MAX_WAIT_MS) {
      try {
        const s = await getSignalRunStatus(runId);
        if (s.status === 'completed') {
          await Promise.all([fetchAlerts(), fetchAgents()]);
          return s.result?.success ?? true;
        }
        if (s.status === 'failed') {
          setError(s.error || 'The run failed');
          return false;
        }
      } catch {
        // one failed poll isn't a failed run
      }
      await wait(POLL_MS);
    }
    await fetchAlerts();
    notify('The run is still going on the server. New matches will show here and arrive by email.');
    return true;
  };

  const run = async (ids: number[], opts: RunOptions, unified: boolean) => {
    setRunning(new Set(ids));
    setError(null);
    try {
      const r = await runResearchAgents({
        instruction_ids: ids,
        topic: opts.topic,
        days_back: opts.daysBack || 7,
        tag_flagged_articles: opts.tagArticles !== false,
        ...(unified ? { generate_report: !!opts.generateUnifiedReport } : {}),
      });
      if (!r.success) {
        setError(messageOf(r.message, 'The run didn’t start'));
        return false;
      }
      if (r.status === 'running' && r.run_id) return await pollRun(r.run_id);
      // Older servers answer in one go
      if (r.podcast_summaries?.length) setPodcasts((p) => [...r.podcast_summaries!, ...p]);
      await Promise.all([fetchAlerts(), fetchAgents()]);
      if (r.report) notify(`Report “${r.report.name}” written from ${r.report.articles_used} articles. It’s under Saved reports below.`);
      return true;
    } catch (e) {
      setError(`The run didn’t start: ${errorText(e)}`);
      return false;
    } finally {
      setRunning(new Set());
    }
  };

  const runAgent = (id: number, opts: RunOptions) => run([id], opts, false);
  const runAll = (opts: RunOptions) => {
    const ids = agents.filter((a) => a.is_active).map((a) => a.id);
    if (!ids.length) {
      setError('No active agents to run');
      return Promise.resolve(false);
    }
    return run(ids, opts, true);
  };

  const dismiss = async (alertId: number) => {
    try {
      await acknowledgeAlert(alertId);
      setAlerts((p) => p.filter((a) => a.id !== alertId));
    } catch (e) {
      notify(`Not dismissed: ${errorText(e)}`);
    }
  };
  // Only this agent's matches. The old "Dismiss all" inside one agent dismissed every agent's matches.
  const dismissAllFor = async (instructionId: number) => {
    try {
      const r = await acknowledgeAllAlerts({ instructionId, topic });
      setAlerts((p) => p.filter((a) => a.instruction_id !== instructionId));
      notify(`${r.acknowledged_count} match${r.acknowledged_count === 1 ? '' : 'es'} dismissed`);
    } catch (e) {
      notify(`Not dismissed: ${errorText(e)}`);
    }
  };

  return {
    agents, alerts, podcasts, saving, loadingAgents, loaded, running, error,
    clearError: () => setError(null),
    dismissPodcast: (i: number) => setPodcasts((p) => p.filter((_, k) => k !== i)),
    refresh: () => Promise.all([fetchAgents(), fetchAlerts()]),
    addAgent, updateAgent, removeAgent, runAgent, runAll, dismiss, dismissAllFor,
  };
}
