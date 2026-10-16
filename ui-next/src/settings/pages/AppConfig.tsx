import { useEffect, useState } from 'react';
import { Icon, TabPanel, Tabs } from '@aunoo/ui';
import { ConnectorsTab } from '../config/ConnectorsTab';
import { DatabaseTab } from '../config/DatabaseTab';
import { DatasetsTab } from '../config/DatasetsTab';
import { ModelsTab } from '../config/ModelsTab';
import { ProvidersTab } from '../config/ProvidersTab';
import { SecurityTab } from '../config/SecurityTab';
import { UsersTab } from '../config/UsersTab';
import type { SettingsPageProps } from '../types';

/*
 * App Configuration, rebuilt from templates/config.html: providers, AI models, the database,
 * datasets, your password, user accounts and connectors, one tab each. The open tab is remembered
 * under the old page's key (configActiveTab, stored as "#<tab>"), and #mcp in the address opens
 * Connectors, as before. Each tab loads its data only while it's open.
 */

const TABS = [
  { value: 'providers', label: 'Providers', icon: 'Newspaper' },
  { value: 'ai-models', label: 'AI models', icon: 'Brain' },
  { value: 'database', label: 'Database', icon: 'Database' },
  { value: 'datasets', label: 'Datasets', icon: 'Table' },
  { value: 'security', label: 'Security', icon: 'Lock' },
  { value: 'users', label: 'Users', icon: 'Users' },
  { value: 'mcp', label: 'Connectors', icon: 'Plug' },
] as const;
type TabId = (typeof TABS)[number]['value'];
const KEY = 'configActiveTab';
const isTab = (v: string): v is TabId => TABS.some((t) => t.value === v);

function initialTab(): TabId {
  const hash = window.location.hash.replace('#', '');
  if (isTab(hash)) return hash;
  try {
    const saved = (localStorage.getItem(KEY) || '').replace('#', '');
    if (isTab(saved)) return saved;
  } catch {
    // per visit only
  }
  return 'database';
}

export function AppConfig({ notify, askConfirm }: SettingsPageProps) {
  const [tab, setTab] = useState<TabId>(initialTab);
  useEffect(() => {
    try {
      localStorage.setItem(KEY, `#${tab}`);
    } catch {
      // per visit only
    }
  }, [tab]);
  const props = { notify, askConfirm };
  return (
    <Tabs
      label="App configuration sections"
      scrollable
      value={tab}
      onValueChange={(v) => isTab(v) && setTab(v)}
      items={TABS.map((t) => ({ value: t.value, label: t.label, icon: <Icon name={t.icon} size="sm" /> }))}
    >
      {TABS.map((t) => (
        <TabPanel key={t.value} value={t.value}>
          {t.value === tab && (
            <>
              {tab === 'providers' && <ProvidersTab {...props} />}
              {tab === 'ai-models' && <ModelsTab {...props} />}
              {tab === 'database' && <DatabaseTab {...props} />}
              {tab === 'datasets' && <DatasetsTab {...props} />}
              {tab === 'security' && <SecurityTab notify={notify} />}
              {tab === 'users' && <UsersTab {...props} />}
              {tab === 'mcp' && <ConnectorsTab {...props} />}
            </>
          )}
        </TabPanel>
      ))}
    </Tabs>
  );
}
