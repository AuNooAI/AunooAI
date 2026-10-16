// Tab in the URL: /anticipate/:tab — deep links and the back button work (spec bug 2).
import { useCallback, useEffect, useState } from 'react';
import { DEFAULT_TAB, tabById } from './tabs';

const BASE = '/anticipate/';

function tabFromLocation() {
  const id = window.location.pathname.startsWith(BASE) ? window.location.pathname.slice(BASE.length).split('/')[0] : '';
  return tabById(id) ? id : null;
}

export function useTabRoute() {
  const [tab, setTab] = useState(() => tabFromLocation() ?? DEFAULT_TAB);

  useEffect(() => {
    // Normalise "/" or an unknown tab to a real URL without adding a history entry
    if (tabFromLocation() !== tab) window.history.replaceState(null, '', `${BASE}${tab}${window.location.search}`);
    const onPop = () => setTab(tabFromLocation() ?? DEFAULT_TAB);
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
