/**
 * Podcast Script Editor Modal
 * Allows users to review and edit the podcast transcript before generating audio
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
import { Label } from './ui/label';
import { Badge } from './ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
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
  Eye,
  Edit2,
  Volume2,
  Mic,
  Clock
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';

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
  onGenerateAudio: (editedScript: string, voiceId: string, duration: string) => void;
  // Audio generation state
  isGeneratingAudio: boolean;
  // Podcast settings
  mode?: 'conversation' | 'bulletin';
  duration?: 'short' | 'medium' | 'long';
  topic?: string;
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
  topic = ''
}: PodcastScriptModalProps) {
  const [editedScript, setEditedScript] = useState(script);
  const [activeTab, setActiveTab] = useState<'edit' | 'preview'>('edit');
  const [hasEdits, setHasEdits] = useState(false);

  // Voice and duration state
  const [voices, setVoices] = useState<Voice[]>([]);
  const [selectedVoiceId, setSelectedVoiceId] = useState<string>('');
  const [selectedDuration, setSelectedDuration] = useState<string>(initialDuration);
  const [loadingVoices, setLoadingVoices] = useState(false);

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

  // Count words and estimate duration
  const wordCount = editedScript.trim().split(/\s+/).length;
  const estimatedMinutes = Math.round(wordCount / 150); // ~150 words per minute for natural speech

  const durationOptions = [
    { value: 'short', label: 'Short (~2-3 min)', description: 'Brief overview' },
    { value: 'medium', label: 'Medium (~5-7 min)', description: 'Standard length' },
    { value: 'long', label: 'Long (~10-15 min)', description: 'In-depth coverage' },
  ];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Mic className="w-5 h-5 text-pink-500" />
            Podcast Script Editor
          </DialogTitle>
          <DialogDescription className="flex items-center gap-4">
            <span>Review and edit your podcast script before generating audio</span>
            {topic && <Badge className="bg-pink-100 text-pink-700">{topic}</Badge>}
          </DialogDescription>
        </DialogHeader>

        {/* Voice and Duration Settings */}
        <div className="grid grid-cols-2 gap-4 py-3 border-b">
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
                        <span className="text-xs text-gray-400">({voice.category})</span>
                      )}
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label htmlFor="duration-select" className="text-xs text-gray-500 mb-1 block">Duration</Label>
            <Select
              value={selectedDuration}
              onValueChange={setSelectedDuration}
            >
              <SelectTrigger id="duration-select" className="w-full">
                <SelectValue placeholder="Select duration" />
              </SelectTrigger>
              <SelectContent>
                {durationOptions.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    <div className="flex items-center gap-2">
                      <Clock className="w-3 h-3" />
                      <span>{opt.label}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Script stats */}
        <div className="flex items-center gap-4 text-sm text-gray-500 border-b pb-2">
          <span className="flex items-center gap-1">
            <FileText className="w-4 h-4" />
            {wordCount} words
          </span>
          <span className="flex items-center gap-1">
            <Volume2 className="w-4 h-4" />
            ~{estimatedMinutes} min estimated
          </span>
          {hasEdits && (
            <Badge variant="outline" className="text-amber-600 border-amber-300">
              Unsaved edits
            </Badge>
          )}
        </div>

        {/* Tabs for Edit/Preview */}
        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'edit' | 'preview')} className="flex-1 flex flex-col min-h-0">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="edit" className="flex items-center gap-2">
              <Edit2 className="w-4 h-4" />
              Edit Script
            </TabsTrigger>
            <TabsTrigger value="preview" className="flex items-center gap-2">
              <Eye className="w-4 h-4" />
              Preview
            </TabsTrigger>
          </TabsList>

          <TabsContent value="edit" className="flex-1 min-h-0 mt-4">
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
                  Script Content
                </Label>
                <Textarea
                  id="script-editor"
                  value={editedScript}
                  onChange={(e) => handleScriptChange(e.target.value)}
                  className="flex-1 min-h-[350px] font-mono text-sm resize-none"
                  placeholder="Your podcast script will appear here..."
                />
              </div>
            )}
          </TabsContent>

          <TabsContent value="preview" className="flex-1 min-h-0 overflow-auto mt-4">
            <div className="prose prose-sm max-w-none p-4 bg-gray-50 rounded-lg min-h-[350px]">
              {isGeneratingScript ? (
                <div className="h-full flex items-center justify-center">
                  <Loader2 className="w-8 h-8 animate-spin text-pink-500" />
                </div>
              ) : editedScript ? (
                <ReactMarkdown>
                  {editedScript}
                </ReactMarkdown>
              ) : (
                <p className="text-gray-400 text-center">No script content to preview</p>
              )}
            </div>
          </TabsContent>
        </Tabs>

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
                Regenerate
              </Button>

              <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>

              <Button
                size="sm"
                onClick={() => onGenerateAudio(editedScript, selectedVoiceId, selectedDuration)}
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
