/**
 * Saved Podcasts Section - Display generated podcasts
 * Shows in the Saved tab alongside saved incidents
 */

import { useState, useEffect, useRef } from 'react';
import {
  Volume2,
  Play,
  Pause,
  Download,
  Trash2,
  Clock,
  Calendar,
  Loader2,
  Headphones,
  MoreVertical,
  AlertCircle,
} from 'lucide-react';
import { Skeleton } from '../ui/skeleton';

interface Podcast {
  podcast_id: string;
  title: string;
  status: string;
  audio_url: string | null;
  created_at: string;
  completed_at: string | null;
  error: string | null;
  transcript: string;
  metadata: {
    duration?: number;
    podcast_name?: string;
    episode_title?: string;
    mode?: string;
    topic?: string;
  };
}

interface SavedPodcastsSectionProps {
  className?: string;
}

export function SavedPodcastsSection({ className }: SavedPodcastsSectionProps) {
  const [podcasts, setPodcasts] = useState<Podcast[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [playingId, setPlayingId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Fetch podcasts on mount
  useEffect(() => {
    fetchPodcasts();
  }, []);

  const fetchPodcasts = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/podcast/list', {
        credentials: 'include',
      });
      if (!res.ok) {
        throw new Error('Failed to fetch podcasts');
      }
      const data = await res.json();
      // Sort by created_at descending (newest first)
      const sorted = data.sort((a: Podcast, b: Podcast) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
      setPodcasts(sorted);
    } catch (err) {
      console.error('Error fetching podcasts:', err);
      setError(err instanceof Error ? err.message : 'Failed to load podcasts');
    } finally {
      setLoading(false);
    }
  };

  const handlePlay = (podcast: Podcast) => {
    if (!podcast.audio_url) return;

    if (playingId === podcast.podcast_id) {
      // Pause current
      audioRef.current?.pause();
      setPlayingId(null);
    } else {
      // Play new
      if (audioRef.current) {
        audioRef.current.pause();
      }
      const audio = new Audio(podcast.audio_url);
      audio.onended = () => setPlayingId(null);
      audio.onerror = () => setPlayingId(null);
      audio.play();
      audioRef.current = audio;
      setPlayingId(podcast.podcast_id);
    }
  };

  const handleDownload = (podcast: Podcast) => {
    if (!podcast.audio_url) return;
    const link = document.createElement('a');
    link.href = podcast.audio_url;
    link.download = `${podcast.title.replace(/[^a-z0-9]/gi, '_')}.mp3`;
    link.click();
  };

  const handleDelete = async (podcastId: string) => {
    if (!confirm('Are you sure you want to delete this podcast?')) return;

    try {
      const res = await fetch(`/api/podcast/${podcastId}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      if (res.ok) {
        setPodcasts(prev => prev.filter(p => p.podcast_id !== podcastId));
        if (playingId === podcastId) {
          audioRef.current?.pause();
          setPlayingId(null);
        }
      }
    } catch (err) {
      console.error('Error deleting podcast:', err);
    }
  };

  const formatDate = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString('en-GB', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
      }).replace(/\//g, '.');
    } catch {
      return dateStr;
    }
  };

  const formatDuration = (minutes?: number) => {
    if (!minutes) return '--:--';
    const mins = Math.floor(minutes);
    const secs = Math.round((minutes - mins) * 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Filter to only completed podcasts
  const completedPodcasts = podcasts.filter(p => p.status === 'completed' && p.audio_url);
  const processingPodcasts = podcasts.filter(p => p.status === 'processing');

  return (
    <div className={className}>
      {/* Section Header */}
      <div className="flex items-center gap-3 mb-4">
        <Headphones className="w-5 h-5 text-pink-500" />
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          Your Podcasts
        </h2>
        <span className="text-sm text-gray-500 bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded-full">
          {completedPodcasts.length} saved
        </span>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-[140px] rounded-lg" />
          ))}
        </div>
      )}

      {/* Error State */}
      {error && !loading && (
        <div className="flex items-center gap-2 p-4 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 rounded-lg">
          <AlertCircle className="w-5 h-5" />
          <span>{error}</span>
          <button
            onClick={fetchPodcasts}
            className="ml-auto text-sm underline hover:no-underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* Processing Podcasts */}
      {processingPodcasts.length > 0 && (
        <div className="mb-4">
          {processingPodcasts.map(podcast => (
            <div
              key={podcast.podcast_id}
              className="flex items-center gap-3 p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg"
            >
              <Loader2 className="w-5 h-5 animate-spin text-amber-500" />
              <div className="flex-1">
                <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {podcast.title}
                </p>
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  Generating podcast...
                </p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty State */}
      {!loading && !error && completedPodcasts.length === 0 && processingPodcasts.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <Volume2 className="w-12 h-12 text-gray-300 dark:text-gray-600 mb-3" />
          <h3 className="text-lg font-medium text-gray-700 dark:text-gray-300 mb-1">
            No Podcasts Yet
          </h3>
          <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xs">
            Generate podcasts from your briefings by clicking the speaker icon in the Your Briefing section.
          </p>
        </div>
      )}

      {/* Podcasts Grid */}
      {!loading && completedPodcasts.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {completedPodcasts.map(podcast => (
            <PodcastCard
              key={podcast.podcast_id}
              podcast={podcast}
              isPlaying={playingId === podcast.podcast_id}
              onPlay={() => handlePlay(podcast)}
              onDownload={() => handleDownload(podcast)}
              onDelete={() => handleDelete(podcast.podcast_id)}
              formatDate={formatDate}
              formatDuration={formatDuration}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface PodcastCardProps {
  podcast: Podcast;
  isPlaying: boolean;
  onPlay: () => void;
  onDownload: () => void;
  onDelete: () => void;
  formatDate: (date: string) => string;
  formatDuration: (mins?: number) => string;
}

function PodcastCard({
  podcast,
  isPlaying,
  onPlay,
  onDownload,
  onDelete,
  formatDate,
  formatDuration,
}: PodcastCardProps) {
  const [showMenu, setShowMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false);
      }
    };
    if (showMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showMenu]);

  return (
    <div className="bg-pink-50 dark:bg-pink-900/20 border border-pink-200 dark:border-pink-700 rounded-lg p-4 hover:shadow-md transition-shadow">
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
          <Calendar className="w-3.5 h-3.5" />
          <span>{formatDate(podcast.created_at)}</span>
        </div>
        <div className="flex items-center gap-1">
          {podcast.metadata?.duration && (
            <span className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
              <Clock className="w-3.5 h-3.5" />
              {formatDuration(podcast.metadata.duration)}
            </span>
          )}
          {/* Menu */}
          <div ref={menuRef} className="relative">
            <button
              onClick={() => setShowMenu(!showMenu)}
              className="p-1 hover:bg-pink-100 dark:hover:bg-pink-800/50 rounded transition-colors"
            >
              <MoreVertical className="w-4 h-4 text-gray-500 dark:text-gray-400" />
            </button>
            {showMenu && (
              <div className="absolute right-0 top-full mt-1 w-32 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-20 py-1">
                <button
                  onClick={() => {
                    onDownload();
                    setShowMenu(false);
                  }}
                  className="w-full px-3 py-2 text-left text-sm text-gray-900 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                >
                  <Download className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                  Download
                </button>
                <button
                  onClick={() => {
                    onDelete();
                    setShowMenu(false);
                  }}
                  className="w-full px-3 py-2 text-left text-sm text-red-600 dark:text-red-400 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                >
                  <Trash2 className="w-4 h-4" />
                  Delete
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Title */}
      <h4 className="font-semibold text-gray-900 dark:text-gray-100 text-sm mb-2 line-clamp-2">
        {podcast.metadata?.episode_title || podcast.title}
      </h4>

      {/* Mode badge */}
      {podcast.metadata?.mode && (
        <span className="text-xs bg-pink-100 dark:bg-pink-800/50 text-pink-700 dark:text-pink-300 px-2 py-0.5 rounded mb-3 inline-block">
          {podcast.metadata.mode}
        </span>
      )}

      {/* Play Button */}
      <button
        onClick={onPlay}
        className={`w-full mt-3 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-medium transition-colors ${
          isPlaying
            ? 'bg-pink-500 text-white hover:bg-pink-600'
            : 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600'
        }`}
      >
        {isPlaying ? (
          <>
            <Pause className="w-4 h-4" />
            Pause
          </>
        ) : (
          <>
            <Play className="w-4 h-4" />
            Play
          </>
        )}
      </button>
    </div>
  );
}
