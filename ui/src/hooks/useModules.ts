/**
 * Hook to fetch enabled analysis modules from the backend.
 * Falls back to showing all tabs if the API is unavailable (backwards compat).
 */

import { useState, useEffect, useCallback } from 'react';

export interface ModuleInfo {
  id: string;
  name: string;
  description?: string;
  tab_id: string | null;
  tab_label: string | null;
  tab_icon: string | null;
  has_model: boolean;
  model_available: boolean | null;
  enabled: boolean;
}

export function useModules() {
  const [modules, setModules] = useState<ModuleInfo[] | null>(null);

  const fetchModules = useCallback(() => {
    fetch('/api/modules')
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(data => setModules(data.modules))
      .catch(err => {
        console.warn('Failed to fetch modules, showing all tabs:', err);
        setModules(null); // null = fallback (show all)
      });
  }, []);

  useEffect(() => {
    fetchModules();
  }, [fetchModules]);

  const isEnabled = (tabId: string): boolean => {
    if (modules === null) return true; // fallback: show all
    return modules.some(m => m.tab_id === tabId && m.enabled);
  };

  const toggleModule = useCallback(async (moduleId: string, enabled: boolean) => {
    try {
      const res = await fetch(`/api/modules/${moduleId}/toggle`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setModules(data.modules);
    } catch (err) {
      console.error('Failed to toggle module:', err);
      // Refetch to get actual state
      fetchModules();
    }
  }, [fetchModules]);

  return { modules, isEnabled, toggleModule };
}
