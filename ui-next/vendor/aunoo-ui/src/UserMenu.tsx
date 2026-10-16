import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { Icon } from './Icon';
import { type IconName } from './icons';
import './UserMenu.css';

export interface UserMenuItem {
  id: string;
  label: React.ReactNode;
  icon?: IconName;
}

export interface UserMenuProps {
  /** Avatar letter, e.g. "m". */
  initial: string;
  /** Name or email. Hidden in the pill under 860px (still in the menu header). */
  name: string;
  /** Menu header subline, e.g. "Free plan · workspace mariam". */
  subtitle?: string;
  /** `[{ id, label, icon? }]` — `icon` is a Phosphor name registered in Icon. */
  items: UserMenuItem[];
  /** `(id) => void` */
  onSelect?: (id: string) => void;
  /** Controlled open state (for stories / tests). */
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** topnav = pill in the top bar, menu below · sidebar = full-width row at the bottom of `<Sidebar>`, menu above (avatar only in the collapsed rail) */
  placement?: 'topnav' | 'sidebar';
  className?: string;
}

/**
 * User pill in the top nav that opens an account menu (Radix DropdownMenu:
 * arrow keys, Escape, focus returns to the pill). Calls `onSelect(id)`.
 */
export function UserMenu({
  initial,
  name,
  subtitle,
  items,
  onSelect,
  open,
  defaultOpen,
  onOpenChange,
  placement = 'topnav',
  className,
}: UserMenuProps) {
  const inSidebar = placement === 'sidebar';
  return (
    <DropdownMenu.Root open={open} defaultOpen={defaultOpen} onOpenChange={onOpenChange} modal={false}>
      <DropdownMenu.Trigger className={['user-menu__trigger', `user-menu__trigger--${placement}`, className].filter(Boolean).join(' ')} aria-label={`Account: ${name}`}>
        <span className="user-menu__avatar" aria-hidden="true">{initial}</span>
        <span className="user-menu__name">{name}</span>
        <Icon name="CaretDown" size="sm" className="user-menu__caret" />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          className="user-menu__content"
          side={inSidebar ? 'top' : 'bottom'}
          align={inSidebar ? 'start' : 'end'}
          sideOffset={0}
        >
          <div className="user-menu__head">
            <span className="user-menu__head-name">{name}</span>
            {subtitle && <span className="user-menu__head-sub">{subtitle}</span>}
          </div>
          {items.map((item) => (
            <DropdownMenu.Item key={item.id} className="user-menu__item" onSelect={() => onSelect?.(item.id)}>
              {item.icon && <Icon name={item.icon} size="sm" />}
              {item.label}
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
