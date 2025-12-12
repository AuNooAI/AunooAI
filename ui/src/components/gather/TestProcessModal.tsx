/**
 * TestProcessModal - Modal for testing LLM processing on a single article
 * Shows step-by-step workflow progress for troubleshooting
 */

import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import { Loader2, FlaskConical, CheckCircle, AlertCircle, AlertTriangle, Info } from 'lucide-react';
import { testProcessArticle, type KeywordGroup, type TestProcessResult, type TestProcessStep } from '../../services/gatherApi';

interface TestProcessModalProps {
  isOpen: boolean;
  onClose: () => void;
  groups: KeywordGroup[];
  onSuccess?: () => void;
  preloadArticle?: { uri: string; groupId: number } | null;
}

function StepIcon({ status }: { status: TestProcessStep['status'] }) {
  switch (status) {
    case 'success':
      return <CheckCircle className="h-4 w-4 text-green-600" />;
    case 'error':
      return <AlertCircle className="h-4 w-4 text-red-600" />;
    case 'warning':
      return <AlertTriangle className="h-4 w-4 text-amber-600" />;
    case 'info':
    default:
      return <Info className="h-4 w-4 text-blue-600" />;
  }
}

function StepDisplay({ step }: { step: TestProcessStep }) {
  const statusColors = {
    success: 'border-green-200 bg-green-50',
    error: 'border-red-200 bg-red-50',
    warning: 'border-amber-200 bg-amber-50',
    info: 'border-blue-200 bg-blue-50',
  };

  return (
    <div className={`gather-test-step ${statusColors[step.status]}`}>
      <div className="gather-test-step-header">
        <StepIcon status={step.status} />
        <span className="gather-test-step-message">{step.message}</span>
      </div>
      {Object.keys(step.details).length > 0 && (
        <div className="gather-test-step-details">
          {Object.entries(step.details).map(([key, value]) => (
            <div key={key} className="gather-test-step-detail">
              <span className="gather-test-step-key">{key.replace(/_/g, ' ')}:</span>
              <span className="gather-test-step-value">
                {Array.isArray(value) ? value.join(', ') : String(value)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function TestProcessModal({
  isOpen,
  onClose,
  groups,
  onSuccess,
  preloadArticle,
}: TestProcessModalProps) {
  const [articleUri, setArticleUri] = useState('');
  const [selectedGroupId, setSelectedGroupId] = useState<string>('');
  const [processing, setProcessing] = useState(false);
  const [result, setResult] = useState<TestProcessResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Preload article data when provided
  useEffect(() => {
    if (preloadArticle && isOpen) {
      setArticleUri(preloadArticle.uri);
      setSelectedGroupId(String(preloadArticle.groupId));
    }
  }, [preloadArticle, isOpen]);

  const handleProcess = async () => {
    if (!articleUri.trim() || !selectedGroupId) return;

    setProcessing(true);
    setResult(null);
    setError(null);

    try {
      const response = await testProcessArticle(articleUri.trim(), parseInt(selectedGroupId));
      setResult(response);
      // Don't call onSuccess here - let user see results first
      // onSuccess will be called when they close the modal
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to process article');
    } finally {
      setProcessing(false);
    }
  };

  const handleClose = () => {
    // If we had a successful result, trigger refresh when closing
    if (result?.success && onSuccess) {
      onSuccess();
    }
    setArticleUri('');
    setSelectedGroupId('');
    setResult(null);
    setError(null);
    onClose();
  };

  // Only close on explicit false, not on any change
  const handleOpenChange = (open: boolean) => {
    if (!open) {
      handleClose();
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="gather-modal gather-test-modal">
        <DialogHeader>
          <DialogTitle className="gather-modal-title">
            <FlaskConical className="h-5 w-5" />
            Test LLM Enrichment
          </DialogTitle>
          <DialogDescription>
            Process a single article through the enrichment workflow. View each step to troubleshoot issues.
          </DialogDescription>
        </DialogHeader>

        <div className="gather-modal-content">
          <div className="gather-form-group">
            <Label htmlFor="article-uri">Article URI</Label>
            <Input
              id="article-uri"
              placeholder="https://example.com/article or http://arxiv.org/abs/..."
              value={articleUri}
              onChange={(e) => setArticleUri(e.target.value)}
              disabled={processing}
            />
            <p className="gather-form-hint">
              Enter the URI of an existing article in the database
            </p>
          </div>

          <div className="gather-form-group">
            <Label htmlFor="group-select">Keyword Group (for topic)</Label>
            <Select
              value={selectedGroupId}
              onValueChange={setSelectedGroupId}
              disabled={processing}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select a group..." />
              </SelectTrigger>
              <SelectContent>
                {groups.map((group) => (
                  <SelectItem key={group.id} value={String(group.id)}>
                    {group.name} ({group.topic})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="gather-form-hint">
              The topic from this group determines the ontology used for analysis
            </p>
          </div>

          {/* Step-by-step Results */}
          {result && result.steps && result.steps.length > 0 && (
            <div className="gather-test-steps">
              <Label>Workflow Steps</Label>
              <div className="gather-test-steps-list">
                {result.steps.map((step, index) => (
                  <StepDisplay key={index} step={step} />
                ))}
              </div>
            </div>
          )}

          {/* Final Result Summary */}
          {result && (
            <div className={`gather-test-result ${result.success ? 'gather-test-success' : 'gather-test-warning'}`}>
              {result.success ? <CheckCircle className="h-5 w-5" /> : <AlertCircle className="h-5 w-5" />}
              <div>
                <strong>{result.success ? 'Success' : 'Failed'}: {result.message}</strong>
                {result.success && Object.keys(result.enrichment_fields).length > 0 && (
                  <ul className="gather-test-fields">
                    {Object.entries(result.enrichment_fields).map(([key, value]) => (
                      <li key={key}>
                        <span className="gather-test-field-name">{key.replace(/_/g, ' ')}:</span>{' '}
                        <span className="gather-test-field-value">{String(value)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}

          {/* Error Display */}
          {error && (
            <div className="gather-test-result gather-test-error">
              <AlertCircle className="h-5 w-5" />
              <div>
                <strong>Error:</strong> {error}
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={handleClose} disabled={processing}>
            {result ? 'Close' : 'Cancel'}
          </Button>
          <Button
            type="button"
            onClick={handleProcess}
            disabled={!articleUri.trim() || !selectedGroupId || processing}
          >
            {processing ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Processing...
              </>
            ) : (
              <>
                <FlaskConical className="h-4 w-4" />
                Process Article
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
