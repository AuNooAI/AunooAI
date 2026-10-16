import type { IconName } from '@aunoo/ui';

/** Apps in the workspace and their dev-server ports (see each app's vite.config.ts). */
export const APP_PORTS = {
  operationshq: 5174,
  explore: 5175,
  anticipate: 5176,
  gather: 5178,
  settings: 5179,
} as const;
export type AppId = keyof typeof APP_PORTS;

export type NavGroup = 'general' | 'settings' | 'app-info';

export interface NavRoute {
  id: string;
  label: string;
  icon: IconName;
  group: NavGroup;
  /** The app that serves the page; omit for external links. */
  app?: AppId;
  /** Production path, or the URL of an external link. */
  path: string;
  /** Path inside the app's own dev server, when it differs from `path`. */
  devPath?: string;
  external?: boolean;
  /** Opens the Topic Setup wizard in place instead of navigating. */
  opensWizard?: boolean;
}

/** SHELL_NAV_SPEC §1 — the single source for every app's sidebar, active item and breadcrumb. */
export const NAV: NavRoute[] = [
  { id: 'operations-hq', label: 'Operations HQ', icon: 'House', group: 'general', app: 'operationshq', path: '/' },
  // Live path is /trend-convergence; the rebuilt app routes its tabs under /anticipate
  { id: 'anticipate', label: 'Anticipate', icon: 'TrendUp', group: 'general', app: 'anticipate', path: '/anticipate/strategic-recommendations' },
  { id: 'explore', label: 'Explore', icon: 'MagnifyingGlass', group: 'general', app: 'explore', path: '/explore', devPath: '/' },
  { id: 'gather', label: 'Gather', icon: 'DownloadSimple', group: 'general', app: 'gather', path: '/gather', devPath: '/' },

  { id: 'app-configuration', label: 'App Configuration', icon: 'SlidersHorizontal', group: 'settings', app: 'settings', path: '/config' },
  { id: 'ai-topic-setup', label: 'AI-guided Topic Setup', icon: 'Sparkle', group: 'settings', path: '?onboarding=true', opensWizard: true },
  { id: 'topic-editor', label: 'Topic Editor', icon: 'NotePencil', group: 'settings', app: 'settings', path: '/create_topic' },
  { id: 'prompt-engineering', label: 'Prompt Engineering', icon: 'Terminal', group: 'settings', app: 'settings', path: '/promptmanager' },
  { id: 'model-bias-arena', label: 'Model Bias Arena', icon: 'Scales', group: 'settings', app: 'settings', path: '/model-bias-arena' },
  { id: 'exploratory-analysis', label: 'Exploratory Analysis', icon: 'ChartScatter', group: 'settings', app: 'settings', path: '/vector-analysis-improved' },
  { id: 'database-editor', label: 'Database Editor', icon: 'Database', group: 'settings', app: 'settings', path: '/database-editor' },
  { id: 'analytics', label: 'Analytics', icon: 'ChartBar', group: 'settings', app: 'settings', path: '/analytics' },

  { id: 'knowledge-base', label: 'Knowledge Base', icon: 'BookOpen', group: 'app-info', path: 'https://aunoo-ai.gitbook.io/aunoo-ai-kb', external: true },
  { id: 'discord', label: 'Discord Community', icon: 'ChatCentered', group: 'app-info', path: 'https://discord.gg/hEUNYDm5KH', external: true },
  {
    id: 'chrome-extension', label: 'Chrome Extension', icon: 'GoogleChromeLogo', group: 'app-info',
    path: 'https://chromewebstore.google.com/detail/fjgiomiceklnoaefnhliablhgoodceji', external: true,
  },
];

export type NavId = (typeof NAV)[number]['id'];

export const routeById = (id: string) => NAV.find((r) => r.id === id);

/** Each app runs on its own port in dev, so cross-app links need the full origin there. */
const isDev = () => typeof window !== 'undefined' && /^(localhost|127\.0\.0\.1)$/.test(window.location.hostname);

export function hrefFor(route: NavRoute) {
  if (route.external || !route.app) return route.path;
  return isDev() ? `http://localhost:${APP_PORTS[route.app]}${route.devPath ?? route.path}` : route.path;
}

/** Settings pages served by the Settings app, matched on the current pathname. */
export const routeForPath = (pathname: string) =>
  NAV.find((r) => r.app === 'settings' && r.path === pathname.replace(/\/+$/, ''));
