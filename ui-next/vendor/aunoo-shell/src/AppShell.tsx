import { useEffect, useState } from 'react';
import {
  type BreadcrumbItem, Breadcrumbs, Button, ConsoleLayout, type ConsoleLayoutToast, FloatingActionButton, Icon, Logo, Sidebar,
  SidebarGroup, SidebarItem, UserMenu,
} from '@aunoo/ui';
import { storage, useNow, type Notify } from './hooks';
import { user, userMenuItems } from './mock';
import { Notifications } from './Notifications';
import { NAV, hrefFor, routeById, type NavGroup, type NavId, type NavRoute } from './routes';
import { TopicSetupWizard, type NewTopic } from './TopicSetupWizard';

const SIDEBAR_KEY = 'aunoo.sidebar.collapsed';
const GROUPS_KEY = 'aunoo.sidebar.groups';

export interface AppShellProps {
  /** Nav item of this page — drives the active item, the open group and the breadcrumb. */
  current: NavId;
  /** Breadcrumb after the section, e.g. the active tab. Settings pages default to their nav label. */
  page?: string;
  /** Page h1, for screen readers only — the breadcrumb shows the page visually. Defaults to the nav label. */
  title?: React.ReactNode;
  headerAside?: React.ReactNode;
  pageWidth?: 'default' | 'wide';
  /** Extra top-bar controls, before the bell (e.g. page settings). */
  navActions?: React.ReactNode;
  /** From `useToasts()`. */
  toasts: ConsoleLayoutToast[];
  notify: Notify;
  /** Called after the Topic Setup wizard creates a topic. */
  onTopicCreated?: (topic: NewTopic) => void;
  /** The Auspex assistant (out of scope — defaults to a toast). */
  onOpenAssistant?: () => void;
  children?: React.ReactNode;
}

const readGroups = (): Record<string, boolean> => {
  try {
    return JSON.parse(storage.get(GROUPS_KEY) ?? '{}');
  } catch {
    return {};
  }
};

/** Shared page frame for every app: sidebar from the route table, top bar, Topic Setup wizard and assistant button. */
export function AppShell({
  current, page, title, headerAside, pageWidth = 'wide', navActions, toasts, notify, onTopicCreated, onOpenAssistant, children,
}: AppShellProps) {
  const now = useNow();
  const route = routeById(current);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [groups, setGroups] = useState(readGroups);

  // `?onboarding=true` opens the wizard on any page; closing it strips the flag (as live does)
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get('onboarding') === 'true') setWizardOpen(true);
  }, []);
  const setWizard = (open: boolean) => {
    setWizardOpen(open);
    if (!open && window.location.search.includes('onboarding')) {
      const url = new URL(window.location.href);
      url.searchParams.delete('onboarding');
      window.history.replaceState(null, '', url);
    }
  };

  const toItem = (r: NavRoute) => ({
    id: r.id,
    label: r.label,
    icon: r.icon,
    href: r.opensWizard ? undefined : hrefFor(r),
    external: r.external,
    current: r.id === current,
  });

  // The group holding the current page opens; other toggles are remembered per browser
  const groupOpen = (g: NavGroup) => groups[g] ?? NAV.some((r) => r.group === g && r.id === current);
  const setGroupOpen = (g: NavGroup, open: boolean) =>
    setGroups((current) => {
      const next = { ...current, [g]: open };
      storage.set(GROUPS_KEY, JSON.stringify(next));
      return next;
    });
  const nested = (g: NavGroup, label: string, icon: 'GearSix' | 'Info') => (
    <SidebarItem
      icon={icon}
      items={NAV.filter((r) => r.group === g).map(toItem)}
      open={groupOpen(g)}
      onOpenChange={(o) => setGroupOpen(g, o)}
      onSelectItem={(id) => routeById(id)?.opensWizard && setWizard(true)}
    >
      {label}
    </SidebarItem>
  );

  const breadcrumbs: BreadcrumbItem[] = !route
    ? []
    : route.group === 'general'
      ? [{ label: route.label, href: hrefFor(route) }, ...(page ? [{ label: page }] : [])]
      : [{ label: 'Settings' }, { label: page ?? route.label }];

  return (
    <ConsoleLayout
      pageWidth={pageWidth}
      breadcrumbs={<Breadcrumbs surface="dark" items={breadcrumbs} />}
      navActions={
        <>
          {navActions}
          <Notifications now={now} notify={notify} />
          <Button size="lg" iconStart={<Icon name="Plus" size="sm" />} onClick={() => setWizard(true)}>Set up topic</Button>
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
              {...user}
              items={userMenuItems}
              onSelect={(id) => (id === 'logout' ? notify('Logged out (demo)') : window.location.assign(hrefFor(routeById('app-configuration')!)))}
            />
          }
        >
          <SidebarGroup label="General">
            {NAV.filter((r) => r.group === 'general').map((r) => (
              <SidebarItem key={r.id} icon={r.icon} href={hrefFor(r)} current={r.id === current}>
                {r.label}
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
      toasts={toasts}
    >
      {children}
      <FloatingActionButton icon="Robot" label="Open Auspex AI Assistant" onClick={onOpenAssistant ?? (() => notify('The Auspex assistant isn’t connected here yet', 'Robot'))} />
      <TopicSetupWizard
        open={wizardOpen}
        onOpenChange={setWizard}
        notify={notify}
        onComplete={(topic) => {
          notify(`Topic “${topic.name}” created — collection starts in a few minutes`, 'CheckCircle');
          onTopicCreated?.(topic);
        }}
      />
    </ConsoleLayout>
  );
}
