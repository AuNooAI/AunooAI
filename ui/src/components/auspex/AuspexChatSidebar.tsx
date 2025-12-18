/**
 * AuspexChatSidebar - Chat history sidebar
 * Supports both overlay mode (compact) and workbench mode (full panel)
 */

import { useState } from 'react';
import {
  History,
  MessageSquare,
  Trash2,
  ChevronLeft,
  ChevronRight,
  Plus,
  Search,
  Filter
} from 'lucide-react';
import { cn } from '../ui/utils';

interface ChatSession {
  id: number;
  topic: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count?: number;
}

interface AuspexChatSidebarProps {
  sessions: ChatSession[];
  currentChatId: number | null;
  isOpen: boolean;
  onToggle: () => void;
  onSelectSession: (chatId: number) => void;
  onDeleteSession: (chatId: number) => void;
  onNewChat?: () => void;
  isWorkbenchMode?: boolean;
}

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } else if (diffDays === 1) {
    return 'Yesterday';
  } else if (diffDays < 7) {
    return date.toLocaleDateString([], { weekday: 'short' });
  } else {
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }
}

function SessionItem({
  session,
  isActive,
  onSelect,
  onDelete,
  isCompact = false
}: {
  session: ChatSession;
  isActive: boolean;
  onSelect: () => void;
  onDelete: () => void;
  isCompact?: boolean;
}) {
  return (
    <div
      className={cn(
        'group relative px-3 py-2 rounded-lg cursor-pointer transition-colors',
        isActive
          ? 'bg-pink-50 dark:bg-pink-900/20 border border-pink-200 dark:border-pink-800'
          : 'hover:bg-gray-50 dark:hover:bg-gray-800'
      )}
      onClick={onSelect}
    >
      <div className="flex items-start gap-2">
        <MessageSquare
          className={cn(
            'w-4 h-4 mt-0.5 flex-shrink-0',
            isActive ? 'text-pink-500' : 'text-gray-400'
          )}
        />
        <div className="flex-1 min-w-0">
          <p
            className={cn(
              'text-sm font-medium truncate',
              isActive ? 'text-pink-700 dark:text-pink-300' : 'text-gray-700 dark:text-gray-300'
            )}
          >
            {session.title || `Chat ${session.id}`}
          </p>
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <span>{formatDate(session.updated_at || session.created_at)}</span>
            {session.message_count && (
              <>
                <span>·</span>
                <span>{session.message_count} msgs</span>
              </>
            )}
          </div>
        </div>

        {/* Delete button */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className={cn(
            'absolute right-2 top-1/2 -translate-y-1/2',
            'p-1 rounded opacity-0 group-hover:opacity-100',
            'text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20',
            'transition-all'
          )}
          title="Delete chat"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}

export function AuspexChatSidebar({
  sessions,
  currentChatId,
  isOpen,
  onToggle,
  onSelectSession,
  onDeleteSession,
  onNewChat,
  isWorkbenchMode = false
}: AuspexChatSidebarProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [filterTopic, setFilterTopic] = useState<string | null>(null);

  // Get unique topics from sessions
  const topics = Array.from(new Set(sessions.map(s => s.topic).filter(Boolean)));

  // Filter sessions
  const filteredSessions = sessions.filter(session => {
    const matchesSearch = !searchQuery ||
      session.title?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesTopic = !filterTopic || session.topic === filterTopic;
    return matchesSearch && matchesTopic;
  });

  // Group sessions by date
  const groupedSessions = groupSessionsByDate(filteredSessions);

  const panelWidth = isWorkbenchMode ? 'w-72' : 'w-60';

  return (
    <>
      {/* Toggle button */}
      <button
        onClick={onToggle}
        className={cn(
          'absolute left-0 top-1/2 -translate-y-1/2 z-10',
          'p-1.5 rounded-r-lg',
          'bg-gray-100 dark:bg-gray-800',
          'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300',
          'hover:bg-gray-200 dark:hover:bg-gray-700',
          'transition-all',
          isOpen && (isWorkbenchMode ? 'left-72' : 'left-60')
        )}
        title={isOpen ? 'Hide chat history' : 'Show chat history'}
      >
        {isOpen ? (
          <ChevronLeft className="w-4 h-4" />
        ) : (
          <ChevronRight className="w-4 h-4" />
        )}
      </button>

      {/* Sidebar panel */}
      <div
        className={cn(
          'absolute left-0 top-0 bottom-0 z-0',
          panelWidth,
          'bg-white dark:bg-gray-900',
          'border-r border-gray-200 dark:border-gray-700',
          'transition-transform duration-300',
          'flex flex-col',
          isOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        {/* Header */}
        <div className="flex-shrink-0 p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between mb-3">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
              <History className="w-4 h-4" />
              Chat History
            </h3>
            {onNewChat && (
              <button
                onClick={onNewChat}
                className="p-1.5 rounded-lg bg-pink-500 hover:bg-pink-600 text-white transition-colors"
                title="New chat"
              >
                <Plus className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* Search */}
          {isWorkbenchMode && (
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search chats..."
                className={cn(
                  'w-full pl-9 pr-3 py-2 text-sm rounded-lg',
                  'bg-gray-100 dark:bg-gray-800',
                  'border border-gray-200 dark:border-gray-700',
                  'text-gray-900 dark:text-gray-100',
                  'placeholder:text-gray-400',
                  'focus:outline-none focus:ring-2 focus:ring-pink-500/50'
                )}
              />
            </div>
          )}

          {/* Topic filter */}
          {isWorkbenchMode && topics.length > 1 && (
            <div className="flex items-center gap-2 mt-2">
              <Filter className="w-3.5 h-3.5 text-gray-400" />
              <div className="flex flex-wrap gap-1">
                <button
                  onClick={() => setFilterTopic(null)}
                  className={cn(
                    'px-2 py-0.5 text-xs rounded-full transition-colors',
                    !filterTopic
                      ? 'bg-pink-500 text-white'
                      : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
                  )}
                >
                  All
                </button>
                {topics.slice(0, 3).map(topic => (
                  <button
                    key={topic}
                    onClick={() => setFilterTopic(topic === filterTopic ? null : topic)}
                    className={cn(
                      'px-2 py-0.5 text-xs rounded-full transition-colors truncate max-w-[80px]',
                      filterTopic === topic
                        ? 'bg-pink-500 text-white'
                        : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
                    )}
                    title={topic}
                  >
                    {topic}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Sessions list */}
        <div className="flex-1 overflow-y-auto p-2">
          {filteredSessions.length === 0 ? (
            <div className="text-center py-8 text-gray-400">
              <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">
                {searchQuery || filterTopic ? 'No matching chats' : 'No chat history'}
              </p>
              <p className="text-xs mt-1">
                {searchQuery || filterTopic
                  ? 'Try adjusting your filters'
                  : 'Start a conversation to see it here'}
              </p>
            </div>
          ) : isWorkbenchMode ? (
            // Grouped view for workbench mode
            <div className="space-y-4">
              {Object.entries(groupedSessions).map(([group, groupSessions]) => (
                <div key={group}>
                  <h4 className="text-xs font-medium text-gray-400 uppercase tracking-wider px-2 mb-2">
                    {group}
                  </h4>
                  <div className="space-y-1">
                    {groupSessions.map((session) => (
                      <SessionItem
                        key={session.id}
                        session={session}
                        isActive={session.id === currentChatId}
                        onSelect={() => onSelectSession(session.id)}
                        onDelete={() => onDeleteSession(session.id)}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            // Simple list for compact mode
            <div className="space-y-1">
              {filteredSessions.map((session) => (
                <SessionItem
                  key={session.id}
                  session={session}
                  isActive={session.id === currentChatId}
                  onSelect={() => onSelectSession(session.id)}
                  onDelete={() => onDeleteSession(session.id)}
                  isCompact
                />
              ))}
            </div>
          )}
        </div>

        {/* Footer with stats */}
        {isWorkbenchMode && sessions.length > 0 && (
          <div className="flex-shrink-0 px-4 py-2 border-t border-gray-200 dark:border-gray-700 text-xs text-gray-400">
            {sessions.length} conversation{sessions.length !== 1 ? 's' : ''}
          </div>
        )}
      </div>
    </>
  );
}

function groupSessionsByDate(sessions: ChatSession[]): Record<string, ChatSession[]> {
  const groups: Record<string, ChatSession[]> = {};
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000);
  const lastWeek = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);

  sessions.forEach(session => {
    const date = new Date(session.updated_at || session.created_at);
    const sessionDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());

    let group: string;
    if (sessionDate >= today) {
      group = 'Today';
    } else if (sessionDate >= yesterday) {
      group = 'Yesterday';
    } else if (sessionDate >= lastWeek) {
      group = 'This Week';
    } else {
      group = 'Older';
    }

    if (!groups[group]) {
      groups[group] = [];
    }
    groups[group].push(session);
  });

  return groups;
}
