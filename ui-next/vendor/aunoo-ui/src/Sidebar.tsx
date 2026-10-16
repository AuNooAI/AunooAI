import { createContext, useContext, useEffect, useId, useState } from 'react';
import * as RadixCollapsible from '@radix-ui/react-collapsible';
import { Icon } from './Icon';
import { Menu } from './Menu';
import { Tooltip } from './Tooltip';
import type { IconName } from './icons';
import './Sidebar.css';

export interface SidebarProps {
  /** Accessible name for the navigation landmark, e.g. "Main". */
  label: string;
  /** Pinned to the bottom of the sidebar. */
  footer?: React.ReactNode;
  /** Show a toggle that collapses the sidebar to its 64px icon rail (§3.1). */
  collapsible?: boolean;
  /** Controlled collapsed state. Pair with `onCollapsedChange`. */
  collapsed?: boolean;
  defaultCollapsed?: boolean;
  /** `(collapsed) => void` — e.g. to remember the choice. */
  onCollapsedChange?: (collapsed: boolean) => void;
  className?: string;
  /** `<SidebarGroup>` elements. */
  children?: React.ReactNode;
}

const SidebarContext = createContext({ collapsed: false });

/** True below the medium breakpoint, where the sidebar is always the rail. */
function useNarrow() {
  const query = '(max-width: 860px)'; // --bp-medium
  const [narrow, setNarrow] = useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches);
  useEffect(() => {
    const mql = window.matchMedia(query);
    const update = () => setNarrow(mql.matches);
    mql.addEventListener('change', update);
    return () => mql.removeEventListener('change', update);
  }, []);
  return narrow;
}

/**
 * Left product nav on dark chrome (§3.1 Sidebar, §4.1 frame): 244px, `navBg`. With `collapsible`
 * a toggle collapses it to a 64px icon rail; under 860px it's always the rail. In the rail, items
 * show their name as a tooltip and nested items open as a menu.
 */
export function Sidebar({ label, footer, collapsible = false, collapsed, defaultCollapsed = false, onCollapsedChange, className, children }: SidebarProps) {
  const groupsId = useId();
  const narrow = useNarrow();
  const [inner, setInner] = useState(defaultCollapsed);
  const isCollapsed = collapsed ?? inner;
  const rail = narrow || (collapsible && isCollapsed);
  const toggle = () => {
    const next = !isCollapsed;
    if (collapsed === undefined) setInner(next);
    onCollapsedChange?.(next);
  };

  return (
    <SidebarContext.Provider value={{ collapsed: rail }}>
      <nav className={['sidebar', rail && 'sidebar--collapsed', className].filter(Boolean).join(' ')} aria-label={label}>
        {collapsible && !narrow && (
          <div className="sidebar__toggle-row">
            <Tooltip content={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'} side="right">
              <button
                type="button"
                className="sidebar__toggle"
                aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
                aria-expanded={!isCollapsed}
                aria-controls={groupsId}
                onClick={toggle}
              >
                <Icon name={isCollapsed ? 'CaretRight' : 'CaretLeft'} size="sm" />
              </button>
            </Tooltip>
          </div>
        )}
        <div id={groupsId} className="sidebar__groups">{children}</div>
        {footer && <div className="sidebar__footer">{footer}</div>}
      </nav>
    </SidebarContext.Provider>
  );
}

export interface SidebarGroupProps {
  /** Group label, e.g. "General". Omit for an unlabelled group. */
  label?: React.ReactNode;
  className?: string;
  /** `<SidebarItem>` elements. */
  children?: React.ReactNode;
}

/** Labelled list of nav items. */
export function SidebarGroup({ label, className, children }: SidebarGroupProps) {
  const labelId = useId();
  return (
    <div className={['sidebar-group', className].filter(Boolean).join(' ')}>
      {label && <div id={labelId} className="sidebar-group__label">{label}</div>}
      <ul className="sidebar-group__list" aria-labelledby={label ? labelId : undefined}>
        {children}
      </ul>
    </div>
  );
}

export interface SidebarSubItem {
  id: string;
  label: React.ReactNode;
  /** Phosphor name registered in Icon, shown small before the label. */
  icon?: IconName;
  href?: string;
  /** Another site: opens in a new tab and says so to screen readers. */
  external?: boolean;
  current?: boolean;
}

export interface SidebarItemProps {
  /** Phosphor name registered in Icon. Shown alone in the collapsed rail. */
  icon?: IconName;
  /** Renders a link. Without it (and without `items`) the item is a button. */
  href?: string;
  /** The current page — sets `aria-current="page"` and the active style. */
  current?: boolean;
  /** `() => void` — called on click (links and buttons). */
  onSelect?: () => void;
  /** Nested items. Makes the item a disclosure (Radix Collapsible) instead of a link. */
  items?: SidebarSubItem[];
  /** `(id) => void` — called when a nested item is chosen. */
  onSelectItem?: (id: string) => void;
  defaultOpen?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
  /** The label. */
  children: React.ReactNode;
}

/**
 * One nav item (§3.1 Nav item, dark): 40px, `textOnDark`; hover and current use `accentTint30`,
 * current text is `accentTextActive`. With `items` it expands to show nested links.
 */
export function SidebarItem({
  icon,
  href,
  current = false,
  onSelect,
  items,
  onSelectItem,
  defaultOpen,
  open,
  onOpenChange,
  className,
  children,
}: SidebarItemProps) {
  const classes = ['sidebar-item', className].filter(Boolean).join(' ');
  const content = (
    <>
      {icon && <Icon name={icon} size="md" className="sidebar-item__icon" />}
      <span className="sidebar-item__label">{children}</span>
    </>
  );

  const { collapsed: rail } = useContext(SidebarContext);
  const name = typeof children === 'string' ? children : undefined;

  // Rail: a nested group opens as a menu beside the icon (its sub-pages stay reachable)
  if (items && rail) {
    const hasCurrent = items.some((item) => item.current);
    return (
      <li className="sidebar-group__entry">
        <Menu
          side="right"
          align="start"
          label={name}
          // The open page is announced (and ticked) in the rail menu too
          items={items.map((item) => ({
            id: item.id,
            label: item.current ? <>{item.label}<span className="visually-hidden"> (current page)</span></> : item.label,
            icon: item.current ? 'Check' : item.icon,
          }))}
          onSelect={(id) => {
            const item = items.find((i) => i.id === id);
            onSelectItem?.(id);
            if (item?.href) {
              if (item.external) window.open(item.href, '_blank', 'noopener,noreferrer');
              else window.location.assign(item.href);
            }
          }}
          trigger={
            <button type="button" className={classes} aria-label={name} data-current={hasCurrent ? '' : undefined}>
              {content}
            </button>
          }
        />
      </li>
    );
  }

  if (items) {
    const hasCurrent = items.some((item) => item.current);
    return (
      <li className="sidebar-group__entry">
        <RadixCollapsible.Root
          open={open}
          defaultOpen={defaultOpen ?? hasCurrent}
          onOpenChange={onOpenChange}
        >
          <RadixCollapsible.Trigger className={classes} data-current={hasCurrent ? '' : undefined}>
            {content}
            <Icon name="CaretDown" size="sm" className="sidebar-item__chevron" />
          </RadixCollapsible.Trigger>
          <RadixCollapsible.Content className="sidebar-item__sub">
            <ul className="sidebar-item__sublist">
              {items.map((item) => (
                <li key={item.id}>
                  <SubLink item={item} onSelect={() => onSelectItem?.(item.id)} />
                </li>
              ))}
            </ul>
          </RadixCollapsible.Content>
        </RadixCollapsible.Root>
      </li>
    );
  }

  const control = href ? (
    <a className={classes} href={href} aria-current={current ? 'page' : undefined} onClick={onSelect}>
      {content}
    </a>
  ) : (
    <button type="button" className={classes} aria-current={current ? 'page' : undefined} onClick={onSelect}>
      {content}
    </button>
  );

  return (
    <li className="sidebar-group__entry">
      {/* Rail: the label is visually hidden, so show it as a tooltip */}
      {rail ? <Tooltip content={children} side="right">{control}</Tooltip> : control}
    </li>
  );
}

function SubLink({ item, onSelect }: { item: SidebarSubItem; onSelect: () => void }) {
  const props = {
    className: 'sidebar-item sidebar-item--sub',
    'aria-current': item.current ? ('page' as const) : undefined,
    onClick: onSelect,
  };
  const content = (
    <>
      {item.icon && <Icon name={item.icon} size="sm" className="sidebar-item__icon" />}
      <span className="sidebar-item__label">{item.label}</span>
      {item.external && (
        <>
          <Icon name="ArrowSquareOut" size="sm" className="sidebar-item__external" />
          <span className="visually-hidden"> (opens in new tab)</span>
        </>
      )}
    </>
  );
  if (!item.href) {
    return (
      <button type="button" {...props}>
        {content}
      </button>
    );
  }
  return (
    <a href={item.href} {...props} {...(item.external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}>
      {content}
    </a>
  );
}
