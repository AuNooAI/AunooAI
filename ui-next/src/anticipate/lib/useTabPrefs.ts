// Manage Tabs: order + visibility, saved per browser.
import { useEffect, useState } from 'react';
import { TABS } from './tabs';

const KEY = 'aunoo.anticipate.tabs';
interface Prefs { order: string[]; hidden: string[] }

function load(): Prefs {
  const ids = TABS.map((t) => t.id);
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? 'null') as Prefs | null;
    if (!saved) return { order: ids, hidden: [] };
    const known = saved.order.filter((id) => ids.includes(id));
    return { order: [...known, ...ids.filter((id) => !known.includes(id))], hidden: saved.hidden.filter((id) => ids.includes(id)) };
  } catch {
    return { order: ids, hidden: [] };
  }
}

export function useTabPrefs() {
  const [prefs, setPrefs] = useState(load);
  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(prefs));
    } catch {
      // storage unavailable — prefs last for this visit
    }
  }, [prefs]);
  return {
    prefs,
    setOrder: (order: string[]) => setPrefs((p) => ({ ...p, order })),
    setVisible: (id: string, visible: boolean) =>
      setPrefs((p) => ({ ...p, hidden: visible ? p.hidden.filter((h) => h !== id) : [...p.hidden, id] })),
  };
}
