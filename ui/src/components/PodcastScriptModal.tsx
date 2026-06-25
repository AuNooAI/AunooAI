/**
 * Podcast Instructions Modal
 * Allows users to review articles/instructions before generating podcast script and audio
 */

import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import { Button } from './ui/button';
import { Textarea } from './ui/textarea';
import { Input } from './ui/input';
import { Label } from './ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './ui/select';
import {
  Loader2,
  RefreshCw,
  Play,
  FileText,
  Mic,
} from 'lucide-react';

interface Voice {
  voice_id: string;
  name: string;
  category?: string;
  description?: string;
  preview_url?: string;
}

interface PodcastScriptModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // Script data
  script: string;
  isGeneratingScript: boolean;
  // Callbacks
  onRegenerateScript: () => void;
  onGenerateAudio: (editedScript: string, voiceId: string, duration: string, title: string) => void;
  // Audio generation state
  isGeneratingAudio: boolean;
  // Podcast settings
  mode?: 'conversation' | 'bulletin';
  duration?: 'short' | 'medium' | 'long';
  topic?: string;
  // Episode title
  episodeTitle?: string;
}

export function PodcastScriptModal({
  open,
  onOpenChange,
  script,
  isGeneratingScript,
  onRegenerateScript,
  onGenerateAudio,
  isGeneratingAudio,
  mode = 'bulletin',
  duration: initialDuration = 'medium',
  topic = '',
  episodeTitle = ''
}: PodcastScriptModalProps) {
  const [editedScript, setEditedScript] = useState(script);
  const [hasEdits, setHasEdits] = useState(false);
  const [title, setTitle] = useState(episodeTitle);

  // Voice state
  const [voices, setVoices] = useState<Voice[]>([]);
  const [selectedVoiceId, setSelectedVoiceId] = useState<string>('');
  const [loadingVoices, setLoadingVoices] = useState(false);

  // Update title when prop changes
  useEffect(() => {
    setTitle(episodeTitle);
  }, [episodeTitle]);

  // Load voices when modal opens
  useEffect(() => {
    if (open && voices.length === 0) {
      loadVoices();
    }
  }, [open]);

  const loadVoices = async () => {
    setLoadingVoices(true);
    try {
      const response = await fetch('/api/available_voices', {
        credentials: 'include'
      });
      if (response.ok) {
        const data = await response.json();
        setVoices(data);
        // Set default voice if not already set
        if (!selectedVoiceId && data.length > 0) {
          // Try to find a good default voice (prefer "premade" category)
          const defaultVoice = data.find((v: Voice) => v.category === 'premade') || data[0];
          setSelectedVoiceId(defaultVoice.voice_id);
        }
      }
    } catch (err) {
      console.error('Failed to load voices:', err);
    } finally {
      setLoadingVoices(false);
    }
  };

  // Update local state when script prop changes
  useEffect(() => {
    setEditedScript(script);
    setHasEdits(false);
  }, [script]);

  // Track edits
  const handleScriptChange = (value: string) => {
    setEditedScript(value);
    setHasEdits(value !== script);
  };

  // Reset to original
  const handleReset = () => {
    setEditedScript(script);
    setHasEdits(false);
  };

  // Count words
  const wordCount = editedScript.trim().split(/\s+/).length;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Mic className="w-5 h-5 text-pink-500" />
            Podcast Instructions
          </DialogTitle>
          <DialogDescription>
            Review the articles that will be used to generate your podcast
          </DialogDescription>
        </DialogHeader>

        {/* Title and Voice Settings */}
        <div className="grid grid-cols-2 gap-4 py-3 border-b">
          <div>
            <Label htmlFor="title-input" className="text-xs text-gray-500 mb-1 block">Title</Label>
            <Input
              id="title-input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Episode title..."
              className="w-full"
            />
          </div>
          <div>
            <Label htmlFor="voice-select" className="text-xs text-gray-500 mb-1 block">Voice</Label>
            <Select
              value={selectedVoiceId}
              onValueChange={setSelectedVoiceId}
              disabled={loadingVoices}
            >
              <SelectTrigger id="voice-select" className="w-full">
                <SelectValue placeholder={loadingVoices ? "Loading voices..." : "Select voice"} />
              </SelectTrigger>
              <SelectContent>
                {voices.map((voice) => (
                  <SelectItem key={voice.voice_id} value={voice.voice_id}>
                    <div className="flex items-center gap-2">
                      <span>{voice.name}</span>
                      {voice.category && (
                        <span className="text-xs text-gray-500">({voice.category})</span>
                      )}
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Word count */}
        <div className="flex items-center gap-4 text-sm text-gray-500 pb-2">
          <span className="flex items-center gap-1">
            <FileText className="w-4 h-4" />
            {wordCount} words
          </span>
        </div>

        {/* Instructions Editor */}
        <div className="flex-1 flex flex-col min-h-0">
          {isGeneratingScript ? (
            <div className="h-full flex items-center justify-center">
              <div className="text-center">
                <Loader2 className="w-8 h-8 animate-spin text-pink-500 mx-auto mb-2" />
                <p className="text-gray-500">Generating script...</p>
              </div>
            </div>
          ) : (
            <div className="h-full flex flex-col">
              <Label htmlFor="script-editor" className="mb-2">
                Instructions
              </Label>
              <Textarea
                id="script-editor"
                value={editedScript}
                onChange={(e) => handleScriptChange(e.target.value)}
                className="flex-1 min-h-[350px] font-mono text-sm resize-none"
                placeholder="Articles and instructions for your podcast..."
              />
            </div>
          )}
        </div>

        <DialogFooter className="flex-shrink-0 border-t pt-4">
          <div className="flex flex-wrap items-center justify-between gap-2 w-full">
            {/* Left side - Reset button */}
            <div>
              {hasEdits && (
                <Button variant="ghost" size="sm" onClick={handleReset}>
                  Reset
                </Button>
              )}
            </div>

            {/* Right side - Action buttons */}
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={onRegenerateScript}
                disabled={isGeneratingScript || isGeneratingAudio}
              >
                {isGeneratingScript ? (
                  <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                ) : (
                  <RefreshCw className="w-4 h-4 mr-1" />
                )}
                Generate Script
              </Button>

              <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>

              <Button
                size="sm"
                onClick={() => onGenerateAudio(editedScript, selectedVoiceId, 'medium', title)}
                disabled={isGeneratingAudio || isGeneratingScript || !editedScript.trim() || !selectedVoiceId}
                className="bg-pink-500 hover:bg-pink-600"
              >
                {isGeneratingAudio ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                    Generating...
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 mr-1" />
                    Generate Audio
                  </>
                )}
              </Button>
            </div>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default PodcastScriptModal;
