import type { IconName } from '@aunoo/ui';

export type NavGroup = 'general' | 'settings' | 'app-info';

export interface NavRoute {
  id: string;
  label: string;
  icon: IconName;
  group: NavGroup;
  path: string;
  external?: boolean;
  /** Hidden on a dedicated Brand Watcher site. */
  fullOnly?: boolean;
}

/**
 * Sidebar for the monolith, as in vendor/aunoo-shell/src/routes.ts but with the live paths
 * (Anticipate is /trend-convergence; the Topic Setup wizard lives on that page) and the
 * dedicated Brand Watcher filter that ui/src/components/SharedNavigation.tsx applies.
 */
export const NAV: NavRoute[] = [
  { id: 'operations-hq', label: 'Operations HQ', icon: 'House', group: 'general', path: '/', fullOnly: true },
  { id: 'anticipate', label: 'Anticipate', icon: 'TrendUp', group: 'general', path: '/trend-convergence', fullOnly: true },
  { id: 'explore', label: 'Explore', icon: 'MagnifyingGlass', group: 'general', path: '/explore' },
  { id: 'gather', label: 'Gather', icon: 'DownloadSimple', group: 'general', path: '/gather', fullOnly: true },

  { id: 'app-configuration', label: 'App Configuration', icon: 'SlidersHorizontal', group: 'settings', path: '/config' },
  { id: 'ai-topic-setup', label: 'AI-guided Topic Setup', icon: 'Sparkle', group: 'settings', path: '?onboarding=true', fullOnly: true },
  { id: 'topic-editor', label: 'Topic Editor', icon: 'NotePencil', group: 'settings', path: '/create_topic', fullOnly: true },
  { id: 'prompt-engineering', label: 'Prompt Engineering', icon: 'Terminal', group: 'settings', path: '/promptmanager', fullOnly: true },
  { id: 'model-bias-arena', label: 'Model Bias Arena', icon: 'Scales', group: 'settings', path: '/model-bias-arena', fullOnly: true },
  { id: 'exploratory-analysis', label: 'Exploratory Analysis', icon: 'ChartScatter', group: 'settings', path: '/vector-analysis-improved', fullOnly: true },
  { id: 'database-editor', label: 'Database Editor', icon: 'Database', group: 'settings', path: '/database-editor', fullOnly: true },
  { id: 'analytics', label: 'Analytics', icon: 'ChartBar', group: 'settings', path: '/analytics', fullOnly: true },

  { id: 'knowledge-base', label: 'Knowledge Base', icon: 'BookOpen', group: 'app-info', path: 'https://aunoo-ai.gitbook.io/aunoo-ai-kb', external: true },
  { id: 'discord', label: 'Discord Community', icon: 'ChatCentered', group: 'app-info', path: 'https://discord.gg/hEUNYDm5KH', external: true },
  {
    id: 'chrome-extension', label: 'Chrome Extension', icon: 'GoogleChromeLogo', group: 'app-info',
    path: 'https://chromewebstore.google.com/detail/fjgiomiceklnoaefnhliablhgoodceji', external: true,
  },
];

export type NavId = (typeof NAV)[number]['id'];
export const routeById = (id: string) => NAV.find((r) => r.id === id);
