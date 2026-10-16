import { useRef } from 'react';
import * as RadixDialog from '@radix-ui/react-dialog';
import { Icon } from './Icon';
import { IconButton } from './IconButton';
import { restoreFocus } from './restoreFocus';
import './Dialog.css';

export interface DialogProps {
  /** Controlled open state. Pair with `onOpenChange`. */
  open?: boolean;
  defaultOpen?: boolean;
  /** `(open) => void` — also called on Escape, backdrop click and the close button. */
  onOpenChange?: (open: boolean) => void;
  /** Dialog heading (its accessible name). */
  title: React.ReactNode;
  /** Line under the title (its accessible description). */
  description?: React.ReactNode;
  /** Optional opener, a single button element. Omit when the app controls `open`. */
  trigger?: React.ReactElement;
  /** Bottom actions, right-aligned, e.g. Cancel (`<DialogClose>`) + a primary Button. */
  footer?: React.ReactNode;
  /** md = forms and confirmations · lg = dense editors (prompt tuning, previews) · xl = side-by-side comparisons */
  size?: 'md' | 'lg' | 'xl';
  /** Accessible name of the ✕ button. */
  closeLabel?: string;
  className?: string;
  /** Body. Scrolls when it's taller than the window. */
  children?: React.ReactNode;
}

/**
 * Modal dialog (Radix Dialog: focus is trapped inside, Escape / backdrop / ✕ close it, focus
 * returns to the opener). Overlay surface per §3.1; header and footer stay put, the body scrolls.
 */
export function Dialog({
  open,
  defaultOpen,
  onOpenChange,
  title,
  description,
  trigger,
  footer,
  closeLabel = 'Close',
  size = 'md',
  className,
  children,
}: DialogProps) {
  // Radix returns focus only to its own Trigger. When the app opens the dialog itself (no
  // `trigger`), remember what had focus at open and put focus back there on close.
  const returnFocusRef = useRef<HTMLElement | null>(null);
  return (
    <RadixDialog.Root open={open} defaultOpen={defaultOpen} onOpenChange={onOpenChange}>
      {trigger && <RadixDialog.Trigger asChild>{trigger}</RadixDialog.Trigger>}
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="dialog__overlay" />
        <RadixDialog.Content
          className={['dialog', size !== 'md' && `dialog--${size}`, className].filter(Boolean).join(' ')}
          onOpenAutoFocus={(event) => {
            returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
            // If the ✕ is the only control, focusing it would show its tooltip and the first Escape
            // would only close that — focus the dialog itself instead
            const content = event.currentTarget as HTMLElement | null;
            const controls = content?.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
            const onlyClose = controls && Array.from(controls).every((el) => el.closest('.dialog__close'));
            if (content && onlyClose) {
              event.preventDefault();
              content.focus();
            }
          }}
          onCloseAutoFocus={(event) => {
            if (trigger) return;
            event.preventDefault();
            restoreFocus(returnFocusRef.current, event.currentTarget as HTMLElement | null);
          }}
          {...(description ? {} : { 'aria-describedby': undefined })}
        >
          <div className="dialog__header">
            <RadixDialog.Title className="dialog__title">{title}</RadixDialog.Title>
            {description && <RadixDialog.Description className="dialog__description">{description}</RadixDialog.Description>}
          </div>
          <div className="dialog__body">{children}</div>
          {footer && <div className="dialog__footer">{footer}</div>}
          {/* Last in the DOM so initial focus lands on the first control in the body */}
          <div className="dialog__close">
            <RadixDialog.Close asChild>
              <IconButton icon={<Icon name="X" size="sm" />} label={closeLabel} tooltipSide="left" />
            </RadixDialog.Close>
          </div>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}

export interface DialogCloseProps {
  /** A single button element, e.g. `<Button variant="secondary">Cancel</Button>`. */
  children: React.ReactElement;
}

/** Closes the nearest Dialog when its child is clicked. */
export function DialogClose({ children }: DialogCloseProps) {
  return <RadixDialog.Close asChild>{children}</RadixDialog.Close>;
}
