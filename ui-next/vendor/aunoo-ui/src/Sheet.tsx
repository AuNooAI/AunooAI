import { useRef } from 'react';
import * as RadixDialog from '@radix-ui/react-dialog';
import { Icon } from './Icon';
import { IconButton } from './IconButton';
import { restoreFocus } from './restoreFocus';
import './Sheet.css';

export interface SheetProps {
  /** Controlled open state. Pair with `onOpenChange`. */
  open?: boolean;
  /** `(open) => void` — also called on Escape, backdrop click and the close button. */
  onOpenChange?: (open: boolean) => void;
  /** Sheet heading (its accessible name). */
  title: React.ReactNode;
  /** Line under the title (its accessible description). */
  description?: React.ReactNode;
  /** Under the title and description, e.g. a topic `<Chip>`. */
  meta?: React.ReactNode;
  /** Optional opener, a single button element. Omit when the app controls `open`. */
  trigger?: React.ReactElement;
  /** Pinned at the bottom, e.g. a destructive "Delete" button. */
  footer?: React.ReactNode;
  /** md = details (--sheet-w) · lg = edit forms (--sheet-w-lg) */
  size?: 'md' | 'lg';
  /** Accessible name of the ✕ button. */
  closeLabel?: string;
  className?: string;
  /** Body. Scrolls when it's taller than the window. */
  children?: React.ReactNode;
}

/**
 * Modal side panel from the right edge (Radix Dialog: focus trapped, Escape / backdrop / ✕
 * close it, focus returns to the opener). For record details next to the list they came from.
 * Same overlay surface as Dialog (§3.1), full height, --sheet-w wide.
 */
export function Sheet({ open, onOpenChange, title, description, meta, trigger, footer, size = 'md', closeLabel = 'Close', className, children }: SheetProps) {
  const returnFocusRef = useRef<HTMLElement | null>(null);
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      {trigger && <RadixDialog.Trigger asChild>{trigger}</RadixDialog.Trigger>}
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="sheet__overlay" />
        <RadixDialog.Content
          className={['sheet', size === 'lg' && 'sheet--lg', className].filter(Boolean).join(' ')}
          onOpenAutoFocus={() => {
            returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
          }}
          onCloseAutoFocus={(event) => {
            if (trigger) return;
            event.preventDefault();
            restoreFocus(returnFocusRef.current, event.currentTarget as HTMLElement | null);
          }}
          {...(description ? {} : { 'aria-describedby': undefined })}
        >
          <div className="sheet__header">
            <RadixDialog.Title className="sheet__title">{title}</RadixDialog.Title>
            {description && <RadixDialog.Description className="sheet__description">{description}</RadixDialog.Description>}
            {meta && <div className="sheet__meta">{meta}</div>}
          </div>
          <div className="sheet__body">{children}</div>
          {footer && <div className="sheet__footer">{footer}</div>}
          <div className="sheet__close">
            <RadixDialog.Close asChild>
              <IconButton icon={<Icon name="X" size="sm" />} label={closeLabel} tooltipSide="left" />
            </RadixDialog.Close>
          </div>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
