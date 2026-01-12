/**
 * Signal Reports Tab
 * Displays saved signal reports with view and delete functionality
 */

import { useState, useEffect } from 'react';
import {
  FileText,
  Trash2,
  Calendar,
  Bot,
  Loader2,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  AlertCircle,
  Download,
} from 'lucide-react';
import { Button } from '../ui/button';
import {
  getSignalReports,
  getSignalReportById,
  deleteSignalReport,
  type SignalReport,
} from '../../services/researchAgentsApi';
import ReactMarkdown from 'react-markdown';

interface SignalReportsTabProps {
  topic?: string;
}

export function SignalReportsTab({ topic }: SignalReportsTabProps) {
  const [reports, setReports] = useState<SignalReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedReport, setExpandedReport] = useState<number | null>(null);
  const [loadingReport, setLoadingReport] = useState<number | null>(null);
  const [fullReport, setFullReport] = useState<SignalReport | null>(null);

  useEffect(() => {
    fetchReports();
  }, [topic]);

  const fetchReports = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await getSignalReports({ topic, limit: 100 });
      setReports(response.reports || []);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch reports';
      setError(message);
      console.error('Error fetching reports:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleExpandReport = async (reportId: number) => {
    if (expandedReport === reportId) {
      setExpandedReport(null);
      setFullReport(null);
      return;
    }

    setExpandedReport(reportId);
    setLoadingReport(reportId);

    try {
      const response = await getSignalReportById(reportId);
      setFullReport(response.report);
    } catch (err) {
      console.error('Error fetching report details:', err);
    } finally {
      setLoadingReport(null);
    }
  };

  const handleDeleteReport = async (reportId: number) => {
    if (!confirm('Are you sure you want to delete this report?')) {
      return;
    }

    try {
      await deleteSignalReport(reportId);
      setReports(prev => prev.filter(r => r.id !== reportId));
      if (expandedReport === reportId) {
        setExpandedReport(null);
        setFullReport(null);
      }
    } catch (err) {
      console.error('Error deleting report:', err);
    }
  };

  const handleExportMarkdown = (report: SignalReport) => {
    const content = report.report_content || '';
    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${report.name.replace(/[^a-z0-9]/gi, '_')}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (loading && reports.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-pink-500" />
        <span className="ml-2 text-gray-700 dark:text-gray-300">Loading reports...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center gap-2">
        <AlertCircle className="w-5 h-5 text-red-600" />
        <span className="text-sm text-red-800">{error}</span>
        <Button variant="outline" size="sm" onClick={fetchReports} className="ml-auto">
          Retry
        </Button>
      </div>
    );
  }

  if (reports.length === 0) {
    return (
      <div className="bg-gray-50 rounded-lg p-8 text-center border border-dashed border-gray-300">
        <FileText className="w-12 h-12 text-gray-600 dark:text-gray-600 dark:text-gray-400 mx-auto mb-4" />
        <h3 className="text-lg font-medium text-gray-900 mb-2">No Reports Yet</h3>
        <p className="text-gray-700 dark:text-gray-300 mb-4 max-w-md mx-auto">
          Reports are automatically generated when Research Agents with "Generate Report" enabled find matches.
          Enable report generation on an agent and run it to create your first report.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText className="w-5 h-5 text-blue-500" />
          <h2 className="text-xl font-semibold text-gray-900">Signal Reports</h2>
          <span className="px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-600 rounded-full">
            {reports.length} report{reports.length !== 1 ? 's' : ''}
          </span>
        </div>
        <Button variant="outline" size="sm" onClick={fetchReports} disabled={loading}>
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Refresh'}
        </Button>
      </div>

      {/* Reports List */}
      <div className="space-y-3">
        {reports.map(report => (
          <div
            key={report.id}
            className="bg-white border border-gray-200 rounded-lg overflow-hidden"
          >
            {/* Report Header */}
            <div className="flex items-center justify-between p-4 bg-gray-50">
              <div className="flex items-center gap-3 flex-1 min-w-0">
                <button
                  onClick={() => handleExpandReport(report.id)}
                  className="p-1 hover:bg-gray-200 rounded transition-colors"
                >
                  {expandedReport === report.id ? (
                    <ChevronDown className="w-4 h-4 text-gray-700 dark:text-gray-300" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-gray-700 dark:text-gray-300" />
                  )}
                </button>
                <FileText className="w-5 h-5 text-blue-500 shrink-0" />
                <div className="flex-1 min-w-0">
                  <h3 className="font-medium text-gray-900 truncate">{report.name}</h3>
                  <div className="flex items-center gap-3 mt-1 text-xs text-gray-700 dark:text-gray-300">
                    <span className="flex items-center gap-1">
                      <Bot className="w-3 h-3" />
                      {report.instruction_name}
                    </span>
                    <span className="flex items-center gap-1">
                      <Calendar className="w-3 h-3" />
                      {formatDate(report.created_at)}
                    </span>
                    {report.articles_used && (
                      <span>{report.articles_used} article{report.articles_used !== 1 ? 's' : ''}</span>
                    )}
                    {report.model_used && (
                      <span className="px-1.5 py-0.5 bg-gray-100 rounded text-xs">
                        {report.model_used}
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2 ml-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => fullReport && handleExportMarkdown(fullReport)}
                  disabled={expandedReport !== report.id || !fullReport}
                  title="Export as Markdown"
                >
                  <Download className="w-4 h-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleDeleteReport(report.id)}
                  className="text-red-600 hover:text-red-700 hover:bg-red-50"
                  title="Delete report"
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
            </div>

            {/* Expanded Content */}
            {expandedReport === report.id && (
              <div className="border-t border-gray-300 dark:border-gray-700">
                {loadingReport === report.id ? (
                  <div className="p-8 text-center">
                    <Loader2 className="w-6 h-6 animate-spin text-pink-500 mx-auto" />
                    <p className="text-sm text-gray-700 dark:text-gray-300 mt-2">Loading report...</p>
                  </div>
                ) : fullReport ? (
                  <div className="p-4 space-y-4">
                    {/* Description */}
                    {fullReport.description && (
                      <p className="text-sm text-gray-600 bg-gray-50 p-3 rounded">
                        {fullReport.description}
                      </p>
                    )}

                    {/* Report Content */}
                    <div className="prose prose-sm max-w-none bg-white border border-gray-300 dark:border-gray-700 rounded-lg p-4">
                      <ReactMarkdown>{fullReport.report_content || 'No content available'}</ReactMarkdown>
                    </div>

                    {/* Article Links */}
                    {fullReport.article_uris && fullReport.article_uris.length > 0 && (
                      <div className="mt-4">
                        <h4 className="text-xs font-medium text-gray-700 dark:text-gray-300 uppercase mb-2">
                          Source Articles ({fullReport.article_uris.length})
                        </h4>
                        <div className="flex flex-wrap gap-2">
                          {fullReport.article_uris.slice(0, 10).map((uri, idx) => (
                            <a
                              key={idx}
                              href={uri}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded text-gray-700"
                            >
                              <ExternalLink className="w-3 h-3" />
                              Article {idx + 1}
                            </a>
                          ))}
                          {fullReport.article_uris.length > 10 && (
                            <span className="px-2 py-1 text-xs text-gray-700 dark:text-gray-300">
                              +{fullReport.article_uris.length - 10} more
                            </span>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Export Button */}
                    <div className="flex justify-end pt-4 border-t">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleExportMarkdown(fullReport)}
                      >
                        <Download className="w-4 h-4 mr-2" />
                        Export as Markdown
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="p-8 text-center text-gray-700 dark:text-gray-300">
                    Failed to load report details
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
