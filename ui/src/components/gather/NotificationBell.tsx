/**
 * Notification Bell - Shows unread notification count and slide-out panel
 */
import React, { useState } from 'react';
import { Bell, Check, ExternalLink, X, Trash2 } from 'lucide-react';
import { Button } from '../ui/button';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '../ui/sheet';
import { useNotifications } from '../../hooks/useNotifications';
import './NotificationBell.css';

interface NotificationBellProps {
  className?: string;
}

export function NotificationBell({ className = '' }: NotificationBellProps) {
  const [isOpen, setIsOpen] = useState(false);
  const {
    notifications,
    unreadCount,
    isLoading,
    markRead,
    markAllRead,
    refresh,
  } = useNotifications({
    pollInterval: 10000,
    enabled: true,
  });

  const handleNotificationClick = async (notification: typeof notifications[0]) => {
    if (!notification.read) {
      await markRead(notification.id);
    }
    if (notification.link) {
      window.location.href = notification.link;
    }
  };

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  const getNotificationIcon = (type: string) => {
    switch (type) {
      case 'auto_ingest_complete':
        return '🔄';
      case 'keyword_alert':
        return '🔔';
      case 'error':
        return '⚠️';
      default:
        return '📬';
    }
  };

  return (
    <>
      <button
        className={`gather-top-bar-icon-btn ${className}`}
        onClick={() => setIsOpen(true)}
        title="Notifications"
      >
        <Bell className="w-5 h-5" />
        {unreadCount > 0 && (
          <span className="gather-notification-count">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      <Sheet open={isOpen} onOpenChange={setIsOpen}>
        <SheetContent side="right" className="gather-notification-sheet">
          <SheetHeader className="gather-notification-sheet-header">
            <SheetTitle>Notifications</SheetTitle>
          </SheetHeader>

          <div className="gather-notification-sheet-content">
            {isLoading && notifications.length === 0 ? (
              <div className="gather-notification-empty">
                <Bell className="h-12 w-12 opacity-20" />
                <p>Loading notifications...</p>
              </div>
            ) : notifications.length === 0 ? (
              <div className="gather-notification-empty">
                <Bell className="h-12 w-12 opacity-20" />
                <p>No notifications</p>
              </div>
            ) : (
              notifications.map((notification) => (
                <div
                  key={notification.id}
                  className={`gather-notification-sheet-item ${!notification.read ? 'unread' : ''}`}
                  onClick={() => handleNotificationClick(notification)}
                >
                  <div className="gather-notification-sheet-item-icon">
                    {getNotificationIcon(notification.type)}
                  </div>
                  <div className="gather-notification-sheet-item-content">
                    <div className="gather-notification-sheet-item-header">
                      <span className="gather-notification-sheet-item-title">
                        {notification.title}
                      </span>
                      {!notification.read && <span className="gather-notification-unread-dot" />}
                    </div>
                    <p className="gather-notification-sheet-item-message">
                      {notification.message}
                    </p>
                    <span className="gather-notification-sheet-item-time">
                      {formatTime(notification.created_at)}
                    </span>
                  </div>
                  {notification.link && (
                    <ExternalLink className="h-4 w-4 gather-notification-sheet-item-link" />
                  )}
                </div>
              ))
            )}
          </div>

          <div className="gather-notification-sheet-footer">
            <Button
              variant="outline"
              size="sm"
              onClick={() => markAllRead()}
              disabled={unreadCount === 0}
            >
              <Check className="h-4 w-4 mr-2" />
              Mark all read
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => window.location.href = '/gather'}
            >
              View all
            </Button>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
