import type { ReactNode } from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import * as RadixTabs from '@radix-ui/react-tabs';
import { Icon } from './Icon';
import { IconButton } from './IconButton';
import { StickyHeader } from './StickyHeader';
import { Tooltip } from './Tooltip';
import './Tabs.css';

export interface TabItem {
  value: string;
  label: ReactNode;
  icon?: ReactNode;
  /** Screen-reader text for the dot, e.g. "updated" (read as "Billing updated"). */
  badge?: string;
  /** Number shown in a small chip after the label, e.g. unread items. */
  count?: number;
  /** Screen-reader wording for the count, e.g. "12 new". Defaults to the number. */
  countLabel?: string;
  /** Short explanation shown as a tooltip on hover / keyboard focus. */
  description?: string;
  disabled?: boolean;
  className?: string;
}

export interface TabsProps {
  /** `[{ value, label, icon?, badge?, count?, disabled? }]`. */
  items: TabItem[];
  /** Controlled active tab. Pair with `onValueChange`. */
  value?: string;
  /** Uncontrolled initial tab. Defaults to the first item. */
  defaultValue?: string;
  /** `(value) => void` */
  onValueChange?: (value: string) => void;
  /** Accessible name for the tab list, e.g. "Console sections". */
  label: string;
  /** Tabs share the full width equally (e.g. two tabs in a popover). */
  stretch?: boolean;
  /**
   * One scrolling row instead of overflowing the page: chevron buttons appear when tabs are
   * hidden, and the active tab is scrolled into view.
   */
  scrollable?: boolean;
  /** Pinned at the right end of the tab row, e.g. a tab-settings IconButton. */
  listAside?: ReactNode;
  /** Content above the tab row, e.g. a section title with its controls. */
  header?: ReactNode;
  /** Content under the tab row (e.g. a context row and toolbar). Pinned with it when `sticky`. */
  subheader?: ReactNode;
  /** Keep `header` and the tab row pinned to the top of the area panel while the panels scroll. */
  sticky?: boolean;
  className?: string;
  /** `<TabPanel>` elements. */
  children?: ReactNode;
}

/**
 * Underlined section tabs (Radix Tabs: arrow keys move between tabs, Home/End jump).
 * Pass one `<TabPanel value="…">` per item as children.
 */
export function Tabs({
  items,
  value,
  defaultValue,
  onValueChange,
  label,
  stretch = false,
  scrollable = false,
  listAside,
  header,
  subheader,
  sticky = false,
  className,
  children,
}: TabsProps) {
  const [inner, setInner] = useState(defaultValue ?? items[0]?.value);
  const active = value ?? inner;
  const listRef = useRef<HTMLDivElement>(null);
  const [overflow, setOverflow] = useState({ start: false, end: false });

  const measure = useCallback(() => {
    const list = listRef.current;
    if (!list) return;
    setOverflow({
      start: list.scrollLeft > 1,
      end: list.scrollLeft + list.clientWidth < list.scrollWidth - 1,
    });
  }, []);

  useEffect(() => {
    if (!scrollable || !listRef.current) return;
    const list = listRef.current;
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(list);
    list.addEventListener('scroll', measure, { passive: true });
    return () => {
      observer.disconnect();
      list.removeEventListener('scroll', measure);
    };
  }, [scrollable, measure, items.length]);

  // Keep the active tab fully visible (only this row scrolls — never the page). Re-checked when a
  // chevron appears or disappears, since that narrows the row and can hide part of the tab again.
  useEffect(() => {
    const list = listRef.current;
    if (!scrollable || !list) return;
    const tab = list.querySelector<HTMLElement>('[data-state="active"]');
    if (!tab) return;
    const row = list.getBoundingClientRect();
    const rect = tab.getBoundingClientRect();
    if (rect.left < row.left) list.scrollBy({ left: rect.left - row.left });
    else if (rect.right > row.right) list.scrollBy({ left: rect.right - row.right });
  }, [scrollable, active, overflow.start, overflow.end]);

  const scrollBy = (direction: 1 | -1) => {
    const list = listRef.current;
    if (list) list.scrollBy({ left: direction * list.clientWidth * 0.75, behavior: 'smooth' });
  };

  const list = (
    <RadixTabs.List
      ref={listRef}
      className={['tabs__list', stretch && 'tabs__list--stretch', scrollable && 'tabs__list--scroll'].filter(Boolean).join(' ')}
      aria-label={label}
    >
      {items.map((item) => {
        const trigger = (
        <RadixTabs.Trigger
          key={item.value}
          value={item.value}
          disabled={item.disabled}
          className={['tabs__tab', item.className].filter(Boolean).join(' ')}
        >
          {item.icon}
          {item.label}
          {item.count !== undefined && (
            <>
              <span className="tabs__count" aria-hidden="true">{item.count}</span>
              <span className="visually-hidden">, {item.countLabel ?? item.count}</span>
            </>
          )}
          {item.badge && (
            <>
              <span className="tabs__badge" aria-hidden="true" />
              <span className="visually-hidden">{item.badge}</span>
            </>
          )}
        </RadixTabs.Trigger>
        );
        return item.description ? (
          <Tooltip key={item.value} content={item.description}>{trigger}</Tooltip>
        ) : (
          trigger
        );
      })}
    </RadixTabs.List>
  );

  const bar = scrollable || listAside ? (
        <div className="tabs__bar">
          {scrollable && overflow.start && (
            <IconButton className="tabs__scroll" icon={<Icon name="CaretLeft" size="sm" />} label="Scroll tabs left" onClick={() => scrollBy(-1)} />
          )}
          {list}
          {scrollable && overflow.end && (
            <IconButton className="tabs__scroll" icon={<Icon name="CaretRight" size="sm" />} label="Scroll tabs right" onClick={() => scrollBy(1)} />
          )}
          {listAside && <div className="tabs__aside">{listAside}</div>}
        </div>
      ) : (
        list
      );

  return (
    <RadixTabs.Root
      className={['tabs', className].filter(Boolean).join(' ')}
      value={active}
      onValueChange={(next) => {
        if (value === undefined) setInner(next);
        onValueChange?.(next);
      }}
    >
      {sticky ? (
        <StickyHeader>
          {header}
          {bar}
          {subheader}
        </StickyHeader>
      ) : (
        <>
          {header && <div className="tabs__header">{header}</div>}
          {bar}
          {subheader}
        </>
      )}
      {children}
    </RadixTabs.Root>
  );
}

export interface TabPanelProps {
  value: string;
  className?: string;
  children?: ReactNode;
}

/** Content for one tab. Only the active panel renders. */
export function TabPanel({ value, className, children }: TabPanelProps) {
  return (
    <RadixTabs.Content value={value} className={['tabs__panel', className].filter(Boolean).join(' ')}>
      {children}
    </RadixTabs.Content>
  );
}
