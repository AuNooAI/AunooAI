import { useCallback, useEffect, useState } from 'react';
import { Button, EmptyState, Icon, IconButton, type IconName, NotificationItem, Popover, Stack } from '@aunoo/ui';
import { getNotifications, markAllNotificationsRead, markNotificationRead, type Notification } from '@monolith/gatherApi';

const POLL_MS = 10000;
const LIMIT = 20;
const relative = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });

function timeAgo(date: Date, now: Date) {
  const minutes = Math.round((now.getTime() - date.getTime()) / 60000);
  if (minutes < 1) return 'Just now';
  if (minutes < 60) return relative.format(-minutes, 'minute');
  const hours = Math.round(minutes / 60);
  if (hours < 24) return relative.format(-hours, 'hour');
  return relative.format(-Math.round(hours / 24), 'day');
}

const ICON: Record<string, IconName> = { auto_ingest_complete: 'ArrowsClockwise', keyword_alert: 'Bell', error: 'WarningCircle' };

/** Top-bar bell: /api/notifications, polled every 10 s as on the old Gather page. */
export function Notifications({ now }: { now: Date }) {
  const [items, setItems] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);
  const unread = items.filter((n) => !n.read).length;

  const load = useCallback(() => getNotifications(LIMIT).then((r) => setItems(r.notifications ?? []), () => undefined), []);
  useEffect(() => {
    void load();
    const t = window.setInterval(load, POLL_MS);
    return () => window.clearInterval(t);
  }, [load]);

  const markRead = (id: number) => {
    setItems((c) => c.map((n) => (n.id === id ? { ...n, read: true } : n)));
    void markNotificationRead(id).catch(() => undefined);
  };

  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      title="Notifications"
      width="wide"
      trigger={
        <IconButton surface="dark" icon={<Icon name="Bell" size="md" />} label="Notifications" badge={unread > 0 ? `${unread} unread` : undefined} />
      }
      footer={
        items.length > 0 && (
          <div>
              <Button
                variant="secondary"
                iconStart={<Icon name="Check" size="sm" />}
                disabled={unread === 0}
                onClick={() => {
                  setItems((c) => c.map((n) => ({ ...n, read: true })));
                  void markAllNotificationsRead().catch(() => undefined);
                }}
              >
                Mark all read
              </Button>
          </div>
        )
      }
    >
      {items.length > 0 ? (
        <Stack as="ul" gap="sm" label={unread > 0 ? `Notifications, ${unread} unread` : 'Notifications'}>
          {items.map((n) => {
            const created = new Date(n.created_at);
            return (
              <NotificationItem
                key={n.id}
                as="li"
                icon={ICON[n.type] ?? 'Bell'}
                title={n.title}
                description={n.message}
                timestamp={timeAgo(created, now)}
                dateTime={created.toISOString()}
                unread={!n.read}
                onOpen={() => {
                  if (!n.read) markRead(n.id);
                  if (n.link) window.location.assign(n.link);
                }}
                openLabel={n.link ? `Open ${n.title}` : `Mark ${n.title} as read`}
              />
            );
          })}
        </Stack>
      ) : (
        <EmptyState>You’re all caught up.</EmptyState>
      )}
    </Popover>
  );
}
