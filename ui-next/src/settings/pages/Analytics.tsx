import { useEffect, useState } from 'react';
import { Banner, TabPanel, Tabs } from '@aunoo/ui';
import { errorText } from '../../shell';
import { fetchTopics } from '../analytics/api';
import { ChartsTab } from '../analytics/ChartsTab';
import { FlowTab } from '../analytics/FlowTab';
import type { SettingsPageProps } from '../types';
import '../analytics/analytics.css';

/*
 * Analytics, rebuilt from templates/analytics.html: the Charts tab (one topic broken down by
 * sentiment, future signal, time to impact and category) and "Follow the flow" (outlet → category →
 * sentiment). Everything here only reads; there is nothing to save or run.
 */

const TAB_KEY = 'aunoo.settings.analytics.tab';

export function Analytics({ notify }: SettingsPageProps) {
  const [topics, setTopics] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState(() => {
    try {
      return localStorage.getItem(TAB_KEY) === 'flow' ? 'flow' : 'charts';
    } catch {
      return 'charts';
    }
  });

  useEffect(() => {
    fetchTopics().then(setTopics, (e) => setError(errorText(e)));
  }, []);
  const pick = (v: string) => {
    setTab(v);
    try {
      localStorage.setItem(TAB_KEY, v);
    } catch {
      // per visit only
    }
  };

  return (
    <>
      {error && <Banner tone="error" title="Topics didn’t load" description={error} />}
      <Tabs label="Analytics views" value={tab} onValueChange={pick} items={[{ value: 'charts', label: 'Charts' }, { value: 'flow', label: 'Follow the flow' }]}>
        <TabPanel value="charts">{tab === 'charts' && <ChartsTab topics={topics} notify={notify} />}</TabPanel>
        <TabPanel value="flow">{tab === 'flow' && <FlowTab topics={topics} notify={notify} />}</TabPanel>
      </Tabs>
    </>
  );
}
