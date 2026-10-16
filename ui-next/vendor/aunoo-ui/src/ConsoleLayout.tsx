import { AreaPanel } from './AreaPanel';
import { Logo } from './Logo';
import { PageHeader } from './PageHeader';
import { ToastHost } from './Toast';
import { TopNav } from './TopNav';
import { UserMenu } from './UserMenu';
import type { IconName } from './icons';
import './ConsoleLayout.css';

export interface ConsoleLayoutMenuItem {
  id: string;
  label: React.ReactNode;
  icon?: IconName;
}

export interface ConsoleLayoutToast {
  id: string;
  message: React.ReactNode;
  icon?: IconName;
}

export interface ConsoleLayoutProps {
  /** Small label above the title, e.g. the parent section. */
  headerEyebrow?: React.ReactNode;
  /** Page h1. */
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  /** Right of the title, e.g. the plan `<StatusPill>`. */
  headerAside?: React.ReactNode;
  /** Show the page title to screen readers only — for pages whose breadcrumb already names them. */
  hideTitle?: boolean;
  /** `<Tabs>` with its `<TabPanel>`s inside — the whole tabbed page body. */
  tabs?: React.ReactNode;
  /** In the top bar next to the logo, usually `<Breadcrumbs surface="dark">`. With a `sidebar`, it lines up with the area panel's left edge. */
  breadcrumbs?: React.ReactNode;
  /** Top bar, right side, e.g. dark `<IconButton>`s and a primary `<Button>`. Rendered before the UserMenu. */
  navActions?: React.ReactNode;
  /** `{ initial, name, subtitle }` for the UserMenu in the top bar. Omit to hide it (e.g. when it's in the Sidebar footer). */
  user?: { initial: string; name: string; subtitle?: string };
  /** `[{ id, label, icon }]` */
  menuItems?: ConsoleLayoutMenuItem[];
  /** `(id) => void` */
  onMenuSelect?: (id: string) => void;
  /** `[{ id, message, icon? }]` — the app owns adding/removing. */
  toasts?: ConsoleLayoutToast[];
  logo?: React.ReactNode;
  /** Product nav left of the area panel, usually `<Sidebar>`. */
  sidebar?: React.ReactNode;
  /** default = centred 940px column · wide = full panel width (dashboards). */
  pageWidth?: 'default' | 'wide';
  /** Id of `<main>` (skip-link target). */
  mainId?: string;
  className?: string;
  /** Page content (under the tabs, or on its own for pages without tabs). */
  children?: React.ReactNode;
}

/**
 * Shared frame for console pages: skip link, TopNav (logo + UserMenu), optional Sidebar, AreaPanel with
 * PageHeader, optional tabs, the page content, and the toast stack. All content via props.
 */
export function ConsoleLayout({
  headerEyebrow,
  breadcrumbs,
  navActions,
  title,
  subtitle,
  headerAside,
  hideTitle = false,
  tabs,
  user,
  menuItems = [],
  onMenuSelect,
  toasts = [],
  logo = <Logo />,
  sidebar,
  mainId = 'main',
  pageWidth = 'default',
  className,
  children,
}: ConsoleLayoutProps) {
  return (
    <div className={['console-layout', sidebar && 'console-layout--with-sidebar', hideTitle && !headerAside && 'console-layout--no-header', className].filter(Boolean).join(' ')}>
      <a className="console-layout__skip" href={`#${mainId}`}>Skip to content</a>
      <TopNav logo={logo} lead={breadcrumbs} alignLead={Boolean(sidebar)}>
        {(navActions || user) && (
          <>
            {navActions}
            {user && <UserMenu {...user} items={menuItems} onSelect={onMenuSelect} />}
          </>
        )}
      </TopNav>
      <div className="console-layout__body">
        {sidebar}
        <AreaPanel id={mainId} width={pageWidth}>
          <PageHeader eyebrow={headerEyebrow} title={title} subtitle={subtitle} aside={headerAside} hideTitle={hideTitle} />
          {tabs && <div className="console-layout__tabs">{tabs}</div>}
          {children && <div className="console-layout__content">{children}</div>}
        </AreaPanel>
      </div>
      <ToastHost toasts={toasts} />
    </div>
  );
}
