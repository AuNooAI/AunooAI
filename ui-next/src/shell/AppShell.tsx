import { lazy, Suspense, useEffect, useState } from 'react';
import {
  type BreadcrumbItem, Breadcrumbs, Button, ConsoleLayout, type ConsoleLayoutToast, FloatingActionButton, Icon, Logo, Sidebar, SidebarGroup,
  SidebarItem, UserMenu,
} from '@aunoo/ui';
import { storage, useNow, useToasts } from '@aunoo/shell';
import { Notifications } from './Notifications';
import { NAV, routeById, type NavGroup, type NavId, type NavRoute } from './routes';
import { session } from './session';
import { TopicSetupWizard } from './TopicSetupWizard';

// The chat loads on first open, so it stays out of every page's first download
const AuspexPanel = lazy(() => import('./auspex/AuspexPanel'));
type AuspexRequest = { query: string; autoSend?: boolean; topic?: string; nonce: number };

const SIDEBAR_KEY = 'aunoo.sidebar.collapsed';
const GROUPS_KEY = 'aunoo.sidebar.groups';

export interface AppShellProps {
  current: NavId;
  page?: string;
  title?: React.ReactNode;
  headerAside?: React.ReactNode;
  pageWidth?: 'default' | 'wide';
  navActions?: React.ReactNode;
  toasts: ConsoleLayoutToast[];
  children?: React.ReactNode;
}

const readGroups = (): Record<string, boolean> => {
  try {
    return JSON.parse(storage.get(GROUPS_KEY) ?? '{}');
  } catch {
    return {};
  }
};

/**
 * Page frame for the rebuilt monolith pages: vendor/aunoo-shell's AppShell with live data.
 * The user comes from the session, notifications from /api/notifications, "Set up topic"
 * opens the existing wizard on /trend-convergence, and a dedicated Brand Watcher site
 * gets the short nav. The Auspex assistant button is left out until Auspex is rebuilt.
 */
export function AppShell({ current, page, title, headerAside, pageWidth = 'wide', navActions, toasts, children }: AppShellProps) {
  const now = useNow();
  // Topic setup opens from "Set up topic", the sidebar item, or ?onboarding=true on any page
  const [wizardOpen, setWizardOpen] = useState(false);
  const [auspexOpen, setAuspexOpen] = useState(false);
  const [auspexLoaded, setAuspexLoaded] = useState(false);
  const [auspexRequest, setAuspexRequest] = useState<AuspexRequest | null>(null);
  const openAuspex = (req?: Omit<AuspexRequest, 'nonce'>) => {
    setAuspexLoaded(true);
    setAuspexOpen(true);
    if (req?.query) setAuspexRequest({ ...req, nonce: Date.now() });
  };
  // "Ask Auspex" buttons dispatch `auspex:open` {query, autoSend?, topic?} (the old pages' event);
  // ?auspex_query= opens it from a link
  useEffect(() => {
    const onOpen = (e: Event) => openAuspex((e as CustomEvent<Omit<AuspexRequest, 'nonce'>>).detail);
    window.addEventListener('auspex:open', onOpen);
    const url = new URL(window.location.href);
    const q = url.searchParams.get('auspex_query');
    if (q) {
      openAuspex({ query: q, topic: url.searchParams.get('auspex_topic') ?? undefined });
      url.searchParams.delete('auspex_query');
      url.searchParams.delete('auspex_topic');
      window.history.replaceState(null, '', url);
    }
    return () => window.removeEventListener('auspex:open', onOpen);
  }, []);
  const wizard = useToasts();
  useEffect(() => {
    if (!session.dedicatedBw && new URLSearchParams(window.location.search).get('onboarding') === 'true') setWizardOpen(true);
  }, []);
  const setWizard = (open: boolean) => {
    setWizardOpen(open);
    if (!open && window.location.search.includes('onboarding')) {
      const url = new URL(window.location.href);
      url.searchParams.delete('onboarding');
      window.history.replaceState(null, '', url);
    }
  };
  const route = routeById(current);
  const [groups, setGroups] = useState(readGroups);
  const nav = NAV.filter((r) => !(session.dedicatedBw && r.fullOnly));

  const label = (r: NavRoute) => (r.id === 'explore' && session.dedicatedBw ? 'Brand Watcher' : r.label);
  const toItem = (r: NavRoute) => ({ id: r.id, label: label(r), icon: r.icon, href: r.path, external: r.external, current: r.id === current });
  const groupOpen = (g: NavGroup) => groups[g] ?? nav.some((r) => r.group === g && r.id === current);
  const setGroupOpen = (g: NavGroup, open: boolean) =>
    setGroups((c) => {
      const next = { ...c, [g]: open };
      storage.set(GROUPS_KEY, JSON.stringify(next));
      return next;
    });
  const nested = (g: NavGroup, text: string, icon: 'GearSix' | 'Info') => (
    <SidebarItem icon={icon} items={nav.filter((r) => r.group === g).map(toItem)} open={groupOpen(g)} onOpenChange={(o) => setGroupOpen(g, o)}>
      {text}
    </SidebarItem>
  );

  const breadcrumbs: BreadcrumbItem[] = !route
    ? []
    : route.group === 'general'
      ? [{ label: label(route), href: route.path }, ...(page ? [{ label: page }] : [])]
      : [{ label: 'Settings' }, { label: page ?? route.label }];

  const name = session.user.username || 'User';

  return (
    <ConsoleLayout
      pageWidth={pageWidth}
      breadcrumbs={<Breadcrumbs surface="dark" items={breadcrumbs} />}
      navActions={
        <>
          {navActions}
          <Notifications now={now} />
          {!session.dedicatedBw && (
            <Button size="lg" iconStart={<Icon name="Plus" size="sm" />} onClick={() => setWizard(true)}>
              Set up topic
            </Button>
          )}
        </>
      }
      title={title ?? route?.label}
      hideTitle
      headerAside={headerAside}
      sidebar={
        <Sidebar
          collapsible
          defaultCollapsed={storage.get(SIDEBAR_KEY) === '1'}
          onCollapsedChange={(c) => storage.set(SIDEBAR_KEY, c ? '1' : '0')}
          label="Main"
          footer={
            <UserMenu
              placement="sidebar"
              initial={name.charAt(0).toLowerCase()}
              name={name}
              subtitle={session.user.email || undefined}
              items={[
                { id: 'settings', label: 'Settings', icon: 'GearSix' },
                { id: 'logout', label: 'Log out', icon: 'SignOut' },
              ]}
              onSelect={(id) => window.location.assign(id === 'logout' ? '/logout' : '/config')}
            />
          }
        >
          <SidebarGroup label="General">
            {nav.filter((r) => r.group === 'general').map((r) => (
              <SidebarItem key={r.id} icon={r.icon} href={r.path} current={r.id === current}>
                {label(r)}
              </SidebarItem>
            ))}
          </SidebarGroup>
          <SidebarGroup label="Support">
            {nested('settings', 'Settings', 'GearSix')}
            {nested('app-info', 'App Info', 'Info')}
          </SidebarGroup>
        </Sidebar>
      }
      logo={<Logo collapsible />}
      toasts={[...toasts, ...wizard.toasts]}
    >
      {children}
      {!session.dedicatedBw && <TopicSetupWizard open={wizardOpen} onOpenChange={setWizard} notify={wizard.notify} />}
      <FloatingActionButton icon="Robot" label="Open Auspex AI Assistant" onClick={() => openAuspex()} />
      {auspexLoaded && (
        <Suspense fallback={null}>
          <AuspexPanel open={auspexOpen} onOpenChange={setAuspexOpen} notify={wizard.notify} request={auspexRequest} />
        </Suspense>
      )}
    </ConsoleLayout>
  );
}
