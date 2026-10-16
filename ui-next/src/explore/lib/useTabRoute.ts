// Tab in the URL: /explore/next/:tab, so deep links and the back button work.
import { useCallback, useEffect, useState } from 'react';
import { tabById } from './tabs';

const BASE = '/explore/next/';
/** The old page remembered the last tab here; read once so a user lands where they left off */
const OLD_LAST_TAB = 'explore_last_tab';

function tabFromLocation() {
  const id = window.location.pathname.startsWith(BASE) ? window.location.pathname.slice(BASE.length).split('/')[0] : '';
  if (tabById(id)) return id;
  // Notification links name the old page's tab: ?tab=swiss_disinfo, #emerging-topics
  const old = new URLSearchParams(window.location.search).get('tab');
  if (old && tabByOldId(old)) return tabByOldId(old);
  const hash = window.location.hash.slice(1);
  return tabById(hash) ? hash : null;
}

function lastTab() {
  try {
    const old = localStorage.getItem(OLD_LAST_TAB);
    return old ? tabByOldId(old) : null;
  } catch {
    return null;
  }
}

const tabByOldId = (old: string) => {
  const map: Record<string, string> = {
    overview: 'overview', feed: 'news-feed', geopolitical: 'geohotspots', policy: 'us-crisis-tracker', science: 'sciencewatch',
    brand_watcher: 'brand-watcher', market_monitor: 'market-monitor', threat_intel: 'threat-intelligence', swiss_disinfo: 'swiss-election',
    emerging: 'emerging-topics', agents: 'observer-agents', timeline: 'timeline', 'briefing-desk': 'briefing-desk', saved: 'saved',
  };
  return map[old] ?? null;
};

/** `fallback` applies when neither the URL nor the last visit names a tab. */
export function useTabRoute(fallback: string) {
  const [tab, setTab] = useState(() => tabFromLocation() ?? lastTab() ?? fallback);

  useEffect(() => {
    const onPath = window.location.pathname === `${BASE}${tab}`;
    if (!onPath) {
      const search = new URLSearchParams(window.location.search);
      search.delete('tab');
      const q = search.toString();
      window.history.replaceState(null, '', `${BASE}${tab}${q ? `?${q}` : ''}`);
    }
    const onPop = () => setTab(tabFromLocation() ?? fallback);
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const navigate = useCallback((next: string) => {
    setTab(next);
    if (tabFromLocation() !== next) window.history.pushState(null, '', `${BASE}${next}${window.location.search}`);
  }, []);

  return [tab, navigate] as const;
}

/** Opens a tab that isn't rebuilt yet on the old page, which reads its last tab from storage. */
export function openOnOldPage(oldId: string) {
  try {
    localStorage.setItem(OLD_LAST_TAB, oldId);
  } catch {
    // the old page then opens on its default tab
  }
  window.location.assign('/explore');
}
