import { useCallback, useEffect, useState } from 'react';
import type { ConsoleLayoutToast, IconName } from '@aunoo/ui';

const TOAST_MS = 3000;

export type Notify = (message: string, icon?: IconName) => void;

/** Toast queue for `<AppShell toasts>`; `notify` adds one that clears itself. */
export function useToasts() {
  const [toasts, setToasts] = useState<ConsoleLayoutToast[]>([]);
  const notify = useCallback<Notify>((message, icon) => {
    const id = `${Date.now()}-${Math.random()}`;
    setToasts((c) => [...c, { id, message, icon }]);
    window.setTimeout(() => setToasts((c) => c.filter((t) => t.id !== id)), TOAST_MS);
  }, []);
  return { toasts, notify };
}

/** Current time, refreshed every `ms`. */
export function useNow(ms = 30000) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = window.setInterval(() => setNow(new Date()), ms);
    return () => window.clearInterval(t);
  }, [ms]);
  return now;
}

/** localStorage that fails quietly (private windows, blocked storage). */
export const storage = {
  get(key: string) {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  set(key: string, value: string) {
    try {
      localStorage.setItem(key, value);
    } catch {
      // storage unavailable — the choice lasts for this visit
    }
  },
};

/** Active tab kept in the URL hash (`#rss`), so every tab has a direct link and Back works. */
export function useHashTab(values: string[], fallback: string) {
  const read = () => {
    const hash = decodeURIComponent(window.location.hash.slice(1));
    return values.includes(hash) ? hash : fallback;
  };
  const [tab, setTab] = useState(read);
  useEffect(() => {
    const onHash = () => setTab(read());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, [values.join('|')]);
  const select = useCallback((value: string) => {
    setTab(value);
    if (window.location.hash.slice(1) !== value) window.history.pushState(null, '', `#${value}`);
  }, []);
  return [tab, select] as const;
}
