import { useRef, useState } from 'react';
import { Button, EmptyState, Grid, Icon, IconButton, NotificationItem, Popover, PopoverClose, Stack } from '@aunoo/ui';
import { notifications as initialNotifications } from './mock';

const relative = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });

/** "Just now", "5 minutes ago", "3 hours ago", "yesterday"… */
function timeAgo(date: Date, now: Date) {
  const minutes = Math.round((now.getTime() - date.getTime()) / 60000);
  if (minutes < 1) return 'Just now';
  if (minutes < 60) return relative.format(-minutes, 'minute');
  const hours = Math.round(minutes / 60);
  if (hours < 24) return relative.format(-hours, 'hour');
  return relative.format(-Math.round(hours / 24), 'day');
}

interface NotificationsProps {
  /** Ticks every second; keeps "5 minutes ago" current. */
  now: Date;
  /** Toast helper from the page. */
  notify: (message: string) => void;
}

/** Top-bar bell + notifications panel. Owns read/unread state for the demo data. */
export function Notifications({ now, notify }: NotificationsProps) {
  const [loadedAt] = useState(() => Date.now());
  const [items, setItems] = useState(() =>
    initialNotifications.map((n) => ({ ...n, createdAt: new Date(loadedAt - n.minutesAgo * 60000) })),
  );
  const [open, setOpen] = useState(false);
  const footerRef = useRef<HTMLDivElement>(null);
  const unreadCount = items.filter((n) => n.unread).length;

  const markRead = (id: string) => setItems((current) => current.map((n) => (n.id === id ? { ...n, unread: false } : n)));

  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      title="Notifications"
      width="wide"
      trigger={
        <IconButton
          surface="dark"
          icon={<Icon name="Bell" size="md" />}
          label="Notifications"
          badge={unreadCount > 0 ? `${unreadCount} unread` : undefined}
        />
      }
      footer={
        items.length > 0 && (
          // Unstyled wrapper: lets focus move to "View all" once "Mark all read" disables itself
          <div ref={footerRef}>
            <Grid columns={2} stackAt="never">
              <Button
                variant="secondary"
                iconStart={<Icon name="Check" size="sm" />}
                disabled={unreadCount === 0}
                onClick={() => {
                  setItems((current) => current.map((n) => ({ ...n, unread: false })));
                  requestAnimationFrame(() => footerRef.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus());
                }}
              >
                Mark all read
              </Button>
              <PopoverClose>
                <Button variant="secondary" onClick={() => notify('Notification history isn’t built yet')}>
                  View all
                </Button>
              </PopoverClose>
            </Grid>
          </div>
        )
      }
    >
      {items.length > 0 ? (
        <Stack as="ul" gap="sm" label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : 'Notifications'}>
          {items.map((n) => (
            <NotificationItem
              key={n.id}
              as="li"
              icon={n.icon}
              title={n.title}
              description={n.description}
              timestamp={timeAgo(n.createdAt, now)}
              dateTime={n.createdAt.toISOString()}
              unread={n.unread}
              onOpen={() => {
                markRead(n.id);
                notify('Opening the feed run isn’t built yet');
              }}
              openLabel={`Open ${n.title}: ${n.description}`}
            />
          ))}
        </Stack>
      ) : (
        <EmptyState>You’re all caught up.</EmptyState>
      )}
    </Popover>
  );
}
