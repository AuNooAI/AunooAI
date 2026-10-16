import { Icon } from './Icon';
import { type IconName } from './icons';
import './Toast.css';

export interface ToastProps {
  message: React.ReactNode;
  /** Phosphor name registered in Icon; `null` for none. */
  icon?: IconName;
  className?: string;
}

/** One confirmation message on dark chrome. */
export function Toast({ message, icon = 'Check', className }: ToastProps) {
  return (
    <div className={['toast', className].filter(Boolean).join(' ')}>
      {icon && <Icon name={icon} size="sm" className="toast__icon" />}
      <span>{message}</span>
    </div>
  );
}

export interface ToastItem {
  id: string | number;
  message: React.ReactNode;
  icon?: IconName;
}

export interface ToastHostProps {
  /** `[{ id, message, icon? }]` */
  toasts?: ToastItem[];
  label?: string;
}

/**
 * Fixed stack of toasts, bottom-right (full width on small screens). A polite live region:
 * new toasts are announced. The app owns the queue and removes toasts (reference: after ~2.6s).
 */
export function ToastHost({ toasts = [], label = 'Notifications' }: ToastHostProps) {
  return (
    <div className="toast-host" role="status" aria-live="polite" aria-label={label}>
      {toasts.map((t) => (
        <Toast key={t.id} message={t.message} icon={t.icon} />
      ))}
    </div>
  );
}
