import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { Icon } from './Icon';
import type { IconName } from './icons';
import './Menu.css';

export interface MenuItem {
  id: string;
  label: React.ReactNode;
  icon?: IconName;
  /** danger = destructive (Hide, Delete…) */
  tone?: 'default' | 'danger';
  disabled?: boolean;
  /** Draw a hairline above this item to start a new group. */
  separatorBefore?: boolean;
}

export interface MenuProps {
  /** The opener: a single button element, e.g. `<IconButton icon={<Icon name="DotsThreeOutlineVertical" />} label="More actions" />`. */
  trigger: React.ReactElement;
  /** `[{ id, label, icon?, tone?, disabled?, separatorBefore? }]` */
  items: MenuItem[];
  /** `(id) => void` */
  onSelect: (id: string) => void;
  align?: 'start' | 'center' | 'end';
  /** Which side of the trigger it opens on (default below). */
  side?: 'top' | 'right' | 'bottom' | 'left';
  /** Heading inside the menu, e.g. the section name when opened from an icon-only trigger. */
  label?: string;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
}

/** Action menu (Radix DropdownMenu: arrow keys, typeahead, Escape, focus returns to the trigger). */
export function Menu({ trigger, items, onSelect, align = 'end', side = 'bottom', label, open, onOpenChange, className }: MenuProps) {
  return (
    <DropdownMenu.Root open={open} onOpenChange={onOpenChange} modal={false}>
      <DropdownMenu.Trigger asChild>{trigger}</DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content className={['menu', className].filter(Boolean).join(' ')} align={align} side={side}>
          {label && <DropdownMenu.Label className="menu__label">{label}</DropdownMenu.Label>}
          {items.map((item) => [
            item.separatorBefore && <DropdownMenu.Separator key={`${item.id}-sep`} className="menu__separator" />,
            <DropdownMenu.Item
              key={item.id}
              className={['menu__item', item.tone === 'danger' && 'menu__item--danger'].filter(Boolean).join(' ')}
              disabled={item.disabled}
              onSelect={() => onSelect(item.id)}
            >
              {item.icon && <Icon name={item.icon} size="sm" />}
              {item.label}
            </DropdownMenu.Item>,
          ])}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
