import { useState } from 'react';
import { ConfirmDialog, type Confirm, useToasts } from '@aunoo/shell';
import { AppShell } from '../shell';
import type { NavId } from '../shell/routes';
import { Analytics } from './pages/Analytics';
import { AppConfig } from './pages/AppConfig';
import { BiasArena } from './pages/BiasArena';
import { DatabaseEditor } from './pages/DatabaseEditor';
import { Exploratory } from './pages/Exploratory';
import { PromptManager } from './pages/PromptManager';
import { TopicEditor } from './pages/TopicEditor';
import type { SettingsPageProps } from './types';

/*
 * The Settings pages rebuilt on the aunoo design, served at /settings/<page>. Each page is its own
 * component; the frame only picks it from the path and gives it the shell, toasts and confirm dialog.
 * The old addresses (/config, /create_topic, …) send readers here when AUNOO_UI_NEXT is on
 * (app/middleware/ui_next_redirect.py).
 */

const PAGES: Record<string, { nav: NavId; title: string; Page: (p: SettingsPageProps) => React.ReactNode }> = {
  config: { nav: 'app-configuration', title: 'App Configuration', Page: AppConfig },
  'topic-editor': { nav: 'topic-editor', title: 'Topic Editor', Page: TopicEditor },
  prompts: { nav: 'prompt-engineering', title: 'Prompt Engineering', Page: PromptManager },
  'bias-arena': { nav: 'model-bias-arena', title: 'Model Bias Arena', Page: BiasArena },
  exploratory: { nav: 'exploratory-analysis', title: 'Exploratory Analysis', Page: Exploratory },
  database: { nav: 'database-editor', title: 'Database Editor', Page: DatabaseEditor },
  analytics: { nav: 'analytics', title: 'Analytics', Page: Analytics },
};

export function Settings() {
  const id = window.location.pathname.replace(/^\/settings\/?/, '').split('/')[0] || 'config';
  const page = PAGES[id] ?? PAGES.config;
  const { toasts, notify } = useToasts();
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const { Page } = page;
  return (
    <AppShell current={page.nav} page={page.title} title="Settings" toasts={toasts}>
      <Page notify={notify} askConfirm={setConfirm} />
      <ConfirmDialog confirm={confirm} onClose={() => setConfirm(null)} />
    </AppShell>
  );
}
