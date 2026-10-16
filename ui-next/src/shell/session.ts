/** Set by the page template (ui-next/deploy.sh): the signed-in user and site flags. */
export interface AunooSession {
  user: { username: string; email: string };
  /** Dedicated Brand Watcher site: only Explore (as "Brand Watcher") and App Configuration in the nav. */
  dedicatedBw: boolean;
}

declare global {
  interface Window {
    aunoo?: AunooSession;
  }
}

export const session: AunooSession = window.aunoo ?? { user: { username: 'User', email: '' }, dedicatedBw: false };
