/**
 * Toast Notification Utility
 * Provides user-visible status messages with auto-dismiss
 */

export type ToastType = 'success' | 'error' | 'warning' | 'info';

/**
 * Show a toast notification
 * @param message - The message to display
 * @param type - Toast type (success, error, warning, info)
 * @param duration - Auto-dismiss duration in milliseconds (default: 5000)
 */
export function showToast(message: string, type: ToastType = 'info', duration: number = 5000): void {
  // Get or create toast container
  let container = document.getElementById('toastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toastContainer';
    document.body.appendChild(container);
  }

  // Create toast element
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;

  // Icon mapping
  const iconMap: Record<ToastType, string> = {
    success: 'fas fa-check-circle',
    error: 'fas fa-exclamation-circle',
    warning: 'fas fa-exclamation-triangle',
    info: 'fas fa-info-circle',
  };

  toast.innerHTML = `
    <i class="${iconMap[type]}"></i>
    <span>${message}</span>
  `;

  // Add to container
  container.appendChild(toast);

  // Trigger animation
  setTimeout(() => toast.classList.add('show'), 10);

  // Auto-dismiss
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

/**
 * Show success toast
 */
export function showSuccess(message: string, duration?: number): void {
  showToast(message, 'success', duration);
}

/**
 * Show error toast
 */
export function showError(message: string, duration?: number): void {
  showToast(message, 'error', duration);
}

/**
 * Show warning toast
 */
export function showWarning(message: string, duration?: number): void {
  showToast(message, 'warning', duration);
}

/**
 * Show info toast
 */
export function showInfo(message: string, duration?: number): void {
  showToast(message, 'info', duration);
}
