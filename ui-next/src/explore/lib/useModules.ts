import { useCallback, useEffect, useState } from 'react';
import { api } from '../../shell';

/** One analysis module from /api/modules (app/routes/module_routes.py). */
export interface ModuleInfo {
  id: string;
  name: string;
  description?: string;
  tab_id: string | null;
  tab_label: string | null;
  has_model: boolean;
  model_available: boolean | null;
  enabled: boolean;
}

interface ModulesResponse {
  modules: ModuleInfo[];
  dedicated_mode: boolean;
  features?: Record<string, boolean>;
}

/**
 * Which analysis modules are on, and whether this is a dedicated Brand Watcher site.
 * When the list can't be loaded every module tab shows, as on the old page.
 */
export function useModules() {
  const [data, setData] = useState<ModulesResponse | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    api<ModulesResponse>('/api/modules').then(setData, () => setFailed(true));
  }, []);

  const isEnabled = useCallback(
    (tabId: string) => (data ? data.modules.some((m) => m.tab_id === tabId && m.enabled) : true),
    [data],
  );

  const toggle = useCallback(async (id: string, enabled: boolean) => {
    const next = await api<ModulesResponse>(`/api/modules/${encodeURIComponent(id)}/toggle`, { method: 'PUT', json: { enabled } });
    setData(next);
  }, []);

  return {
    modules: data?.modules ?? [],
    /** null until known */
    dedicated: data ? data.dedicated_mode : failed ? false : null,
    features: data?.features ?? {},
    isEnabled,
    toggle,
  };
}
