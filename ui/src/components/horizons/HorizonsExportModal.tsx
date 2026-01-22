/**
 * HorizonsExportModal Component
 * Export options modal for Future Horizons analysis
 */

import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { X, Download, Loader2, FileImage, FileText } from 'lucide-react';
import { FutureHorizonsExportOptions } from '@/types/horizonsExecutiveSummary';

interface HorizonsExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onExport: (options: FutureHorizonsExportOptions) => Promise<void>;
  hasExecutiveSummary: boolean;
  topic: string;
}

const HorizonsExportModal: React.FC<HorizonsExportModalProps> = ({
  isOpen,
  onClose,
  onExport,
  hasExecutiveSummary,
  topic,
}) => {
  const [options, setOptions] = useState<FutureHorizonsExportOptions>({
    includeChart: true,
    includeExecutiveSummary: hasExecutiveSummary,
    includeDetailedCards: true,
    format: 'pdf',
  });
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleExport = async () => {
    // Validate at least one section is selected
    if (!options.includeChart && !options.includeExecutiveSummary && !options.includeDetailedCards) {
      setError('Please select at least one section to export.');
      return;
    }

    setError(null);
    setIsExporting(true);

    try {
      await onExport(options);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed. Please try again.');
    } finally {
      setIsExporting(false);
    }
  };

  const handleOptionChange = (key: keyof FutureHorizonsExportOptions, value: boolean | 'pdf' | 'image') => {
    setOptions((prev) => ({ ...prev, [key]: value }));
    setError(null);
  };

  if (!isOpen) return null;

  const modalContent = (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />

      {/* Modal */}
      <div className="relative bg-white dark:bg-gray-900 border border-border rounded-lg shadow-xl w-full max-w-md mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div>
            <h2 className="text-lg font-semibold">Export Future Horizons</h2>
            <p className="text-sm text-muted-foreground">{topic}</p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            className="h-8 w-8"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Content */}
        <div className="px-6 py-5 space-y-5">
          {/* Sections to Include */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">Sections to Include</Label>

            <div className="space-y-3 pl-1">
              <div className="flex items-center gap-3">
                <Checkbox
                  id="include-chart"
                  checked={options.includeChart}
                  onCheckedChange={(checked) =>
                    handleOptionChange('includeChart', Boolean(checked))
                  }
                />
                <Label
                  htmlFor="include-chart"
                  className="text-sm font-normal cursor-pointer"
                >
                  Three Horizons Chart (SVG visualization)
                </Label>
              </div>

              <div className="flex items-center gap-3">
                <Checkbox
                  id="include-summary"
                  checked={options.includeExecutiveSummary}
                  disabled={!hasExecutiveSummary}
                  onCheckedChange={(checked) =>
                    handleOptionChange('includeExecutiveSummary', Boolean(checked))
                  }
                />
                <Label
                  htmlFor="include-summary"
                  className={`text-sm font-normal cursor-pointer ${
                    !hasExecutiveSummary ? 'text-muted-foreground' : ''
                  }`}
                >
                  Executive Summary
                  {!hasExecutiveSummary && (
                    <span className="text-xs ml-2">(Generate first)</span>
                  )}
                </Label>
              </div>

              <div className="flex items-center gap-3">
                <Checkbox
                  id="include-cards"
                  checked={options.includeDetailedCards}
                  onCheckedChange={(checked) =>
                    handleOptionChange('includeDetailedCards', Boolean(checked))
                  }
                />
                <Label
                  htmlFor="include-cards"
                  className="text-sm font-normal cursor-pointer"
                >
                  Detailed Scenario Cards
                </Label>
              </div>
            </div>
          </div>

          {/* Export Format */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">Export Format</Label>

            <div className="flex gap-3">
              <Button
                variant={options.format === 'pdf' ? 'default' : 'outline'}
                size="sm"
                onClick={() => handleOptionChange('format', 'pdf')}
                className="flex-1 gap-2"
              >
                <FileText className="h-4 w-4" />
                PDF
              </Button>
              <Button
                variant={options.format === 'image' ? 'default' : 'outline'}
                size="sm"
                onClick={() => handleOptionChange('format', 'image')}
                className="flex-1 gap-2"
              >
                <FileImage className="h-4 w-4" />
                Image (PNG)
              </Button>
            </div>
          </div>

          {/* Error Message */}
          {error && (
            <div className="bg-destructive/10 text-destructive text-sm px-3 py-2 rounded-md">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-border bg-gray-50 dark:bg-gray-800">
          <Button variant="outline" onClick={onClose} disabled={isExporting}>
            Cancel
          </Button>
          <Button onClick={handleExport} disabled={isExporting} className="gap-2">
            {isExporting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Exporting...
              </>
            ) : (
              <>
                <Download className="h-4 w-4" />
                Export
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
};

export default HorizonsExportModal;
