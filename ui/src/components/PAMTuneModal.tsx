/**
 * PAM Tune Modal
 *
 * Configuration modal for Power, Attention & Money analysis parameters.
 * Follows the same pattern as NewsletterTuneModal, EOSTuneModal, etc.
 *
 * Note: Organizational Profile is configured via the global "Configure" button,
 * not in this modal.
 */

import React from 'react';
import { Settings, Zap, Eye, DollarSign, Clock, Target, Info } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from './ui/dialog';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Checkbox } from './ui/checkbox';

interface PAMTuneModalProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  // Analysis type
  analysisType: string;
  onAnalysisTypeChange: (value: 'comprehensive' | 'power' | 'attention' | 'money') => void;
  // Time horizon
  timeHorizon: string;
  onTimeHorizonChange: (value: 'current' | '6_months' | '1_year' | '5_years' | '2030') => void;
  // Trend focus
  trendFocus: string[];
  onTrendFocusChange: (trends: string[]) => void;
  // Days back
  daysBack: number;
  onDaysBackChange: (days: number) => void;
  // Article limit
  articleLimit: number;
  onArticleLimitChange: (limit: number) => void;
}

const TREND_OPTIONS = [
  { id: 'T1', name: 'Invisible LLM Ecosystems', description: 'AI assistants as primary gateway, brand visibility decline' },
  { id: 'T2', name: 'Agentic AI Workflows', description: 'AI agents automating research and literature review' },
  { id: 'T3', name: 'SEO to GEO Shift', description: 'Generative engine optimization replaces traditional SEO' },
  { id: 'T4', name: 'Regulatory Pressures', description: 'AI regulations, copyright, and provenance requirements' },
  { id: 'T5', name: 'Market Consolidation', description: 'Concentration around compute, data, and AI giants' },
];

export const PAMTuneModal: React.FC<PAMTuneModalProps> = ({
  isOpen,
  onOpenChange,
  analysisType,
  onAnalysisTypeChange,
  timeHorizon,
  onTimeHorizonChange,
  trendFocus,
  onTrendFocusChange,
  daysBack,
  onDaysBackChange,
  articleLimit,
  onArticleLimitChange,
}) => {
  const handleTrendToggle = (trendId: string) => {
    if (trendFocus.includes(trendId)) {
      onTrendFocusChange(trendFocus.filter(t => t !== trendId));
    } else {
      onTrendFocusChange([...trendFocus, trendId]);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Settings className="w-5 h-5 text-pink-500" />
            PAM Analysis Settings
          </DialogTitle>
          <DialogDescription>
            Configure the Power, Attention & Money analysis parameters.
            Use the Configure button to set your organizational profile.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Analysis Type Row */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label className="flex items-center gap-2">
                <Target className="w-4 h-4 text-gray-500" />
                Analysis Type
              </Label>
              <Select value={analysisType} onValueChange={onAnalysisTypeChange}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="comprehensive">
                    <div className="flex items-center gap-2">
                      <span>Comprehensive</span>
                      <span className="text-xs text-gray-500">All dimensions</span>
                    </div>
                  </SelectItem>
                  <SelectItem value="power">
                    <div className="flex items-center gap-2">
                      <Zap className="w-4 h-4 text-yellow-500" />
                      <span>Power Focus</span>
                    </div>
                  </SelectItem>
                  <SelectItem value="attention">
                    <div className="flex items-center gap-2">
                      <Eye className="w-4 h-4 text-blue-500" />
                      <span>Attention Focus</span>
                    </div>
                  </SelectItem>
                  <SelectItem value="money">
                    <div className="flex items-center gap-2">
                      <DollarSign className="w-4 h-4 text-green-500" />
                      <span>Money Focus</span>
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label className="flex items-center gap-2">
                <Clock className="w-4 h-4 text-gray-500" />
                Outlook Horizon
              </Label>
              <Select value={timeHorizon} onValueChange={onTimeHorizonChange}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="current">Current State</SelectItem>
                  <SelectItem value="6_months">6 Months</SelectItem>
                  <SelectItem value="1_year">1 Year</SelectItem>
                  <SelectItem value="5_years">5 Years</SelectItem>
                  <SelectItem value="2030">2030 Horizon</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Data Range and Article Limit */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Data Range (Days Back)</Label>
              <Select value={daysBack.toString()} onValueChange={(v) => onDaysBackChange(parseInt(v))}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="30">Last 30 days</SelectItem>
                  <SelectItem value="60">Last 60 days</SelectItem>
                  <SelectItem value="90">Last 90 days</SelectItem>
                  <SelectItem value="180">Last 180 days</SelectItem>
                  <SelectItem value="365">Last year</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Article Limit</Label>
              <Select value={articleLimit.toString()} onValueChange={(v) => onArticleLimitChange(parseInt(v))}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="50">50 articles</SelectItem>
                  <SelectItem value="100">100 articles</SelectItem>
                  <SelectItem value="200">200 articles</SelectItem>
                  <SelectItem value="500">500 articles</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Trend Focus */}
          <div className="space-y-3">
            <Label className="flex items-center gap-2">
              <Target className="w-4 h-4 text-gray-500" />
              2030 Trend Focus
            </Label>
            <div className="bg-gray-50 rounded-lg p-4 space-y-3">
              {TREND_OPTIONS.map((trend) => (
                <label
                  key={trend.id}
                  className="flex items-start gap-3 cursor-pointer"
                >
                  <Checkbox
                    checked={trendFocus.includes(trend.id)}
                    onCheckedChange={() => handleTrendToggle(trend.id)}
                    className="mt-0.5"
                  />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-pink-600 bg-pink-100 px-1.5 py-0.5 rounded">
                        {trend.id}
                      </span>
                      <span className="font-medium text-gray-900">{trend.name}</span>
                    </div>
                    <p className="text-sm text-gray-500">{trend.description}</p>
                  </div>
                </label>
              ))}
            </div>
            {trendFocus.length === 0 && (
              <p className="text-sm text-amber-600 flex items-center gap-1">
                <Info className="w-4 h-4" />
                Select at least one trend for focused analysis
              </p>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => onOpenChange(false)} className="bg-pink-500 hover:bg-pink-600">
            Apply Settings
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default PAMTuneModal;
