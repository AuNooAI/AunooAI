/**
 * ExecutiveSummaryCard Component
 * Displays an executive summary with consensus percentages, minority views, and conditional decision forks
 * Design matches the C-Level Strategic Brief template
 */

import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Card, CardContent } from '@/components/ui/card';
import { TopicExecutiveSummary, HORIZON_CONFIG, HorizonType } from '@/types/horizonsExecutiveSummary';
import ShareModal, { ShareExecutiveSummaryData } from '../ShareModal';
import { MoreVertical, Mail, Check, TrendingUp, Download, FileText } from 'lucide-react';
import html2canvas from 'html2canvas';
import './executive-summary.css';

interface ExecutiveSummaryCardProps {
  summary: TopicExecutiveSummary;
  index: number;
  researchTopic?: string;
}

const ExecutiveSummaryCard: React.FC<ExecutiveSummaryCardProps> = ({ summary, index, researchTopic }) => {
  const [showShareModal, setShowShareModal] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPosition, setMenuPosition] = useState({ top: 0, left: 0 });
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Calculate menu position when opening
  const openMenu = () => {
    if (buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setMenuPosition({
        top: rect.bottom + window.scrollY + 4,
        left: rect.right + window.scrollX - 180, // 180px menu width, align right edge
      });
    }
    setMenuOpen(true);
  };

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        menuRef.current && !menuRef.current.contains(target) &&
        buttonRef.current && !buttonRef.current.contains(target)
      ) {
        setMenuOpen(false);
      }
    };

    const handleScroll = () => {
      setMenuOpen(false);
    };

    if (menuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      window.addEventListener('scroll', handleScroll, true);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      window.removeEventListener('scroll', handleScroll, true);
    };
  }, [menuOpen]);

  // Get consensus color based on percentage
  const getConsensusColorClass = (percentage: number): string => {
    if (percentage >= 80) return 'text-green-600 dark:text-green-400';
    if (percentage >= 60) return 'text-amber-600 dark:text-amber-400';
    return 'text-orange-600 dark:text-orange-400';
  };

  // Get horizon display label
  const getHorizonLabel = (horizon: HorizonType): string => {
    const config = HORIZON_CONFIG[horizon];
    return config?.label || horizon || 'Unknown';
  };

  // Build share data
  const buildShareData = (): ShareExecutiveSummaryData => ({
    type: 'executive_summary',
    topic_title: summary.topic_title,
    research_topic: researchTopic,
    primary_horizon: summary.primary_horizon,
    horizon_label: summary.horizon_label,
    opening_statement: summary.opening_statement,
    consensus_percentage: summary.consensus_percentage,
    minority_view: summary.minority_view,
    primary_signal: summary.primary_signal,
    decision_fork: summary.decision_fork,
    action_window: summary.action_window,
    source_scenarios: summary.source_scenarios?.map(s =>
      typeof s === 'string' ? s : s.title
    ),
  });

  // Get current month and year for footer
  const currentDate = new Date();
  const footerDate = currentDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });

  const handleShareClick = () => {
    setMenuOpen(false);
    setShowShareModal(true);
  };

  const cardId = `exec-summary-card-${index}`;

  const handleDownloadPng = async () => {
    setMenuOpen(false);
    const el = document.getElementById(cardId);
    if (!el) return;
    try {
      // Expand any collapsed <details> so source scenarios are visible
      const detailsEls = el.querySelectorAll('details');
      const wasOpen: boolean[] = [];
      detailsEls.forEach((d) => {
        wasOpen.push(d.open);
        d.open = true;
      });

      // Force dark text for export — CSS variables don't resolve well in html2canvas
      const style = document.createElement('style');
      style.id = 'png-export-override';
      style.textContent = `
        #${cardId}, #${cardId} * {
          color: #111827 !important;
          border-color: #d1d5db !important;
        }
        #${cardId} .text-muted-foreground,
        #${cardId} .text-muted-foreground * {
          color: #4b5563 !important;
        }
        #${cardId} .text-green-600, #${cardId} .text-green-400 { color: #16a34a !important; }
        #${cardId} .text-amber-600, #${cardId} .text-amber-400 { color: #d97706 !important; }
        #${cardId} .text-orange-600, #${cardId} .text-orange-400 { color: #ea580c !important; }
        #${cardId} .border-green-500 { border-color: #22c55e !important; }
        #${cardId} .border-orange-500 { border-color: #f97316 !important; }
        #${cardId} .bg-muted\\/30 { background-color: #f3f4f6 !important; }
        #${cardId} { overflow: visible !important; }
      `;
      document.head.appendChild(style);

      // Allow layout to reflow after opening details
      await new Promise(r => setTimeout(r, 50));

      const canvas = await html2canvas(el, {
        backgroundColor: '#ffffff',
        scale: 2,
        logging: false,
        useCORS: true,
        height: el.scrollHeight,
        windowHeight: el.scrollHeight + 100,
      });

      // Restore collapsed state and remove override
      style.remove();
      detailsEls.forEach((d, i) => { d.open = wasOpen[i]; });

      const link = document.createElement('a');
      link.download = `${summary.topic_title.replace(/[^a-zA-Z0-9]/g, '_')}.png`;
      link.href = canvas.toDataURL('image/png');
      link.click();
    } catch (err) {
      console.error('PNG download failed:', err);
      document.getElementById('png-export-override')?.remove();
    }
  };

  const handleDownloadMarkdown = () => {
    setMenuOpen(false);
    const horizonLabel = `${HORIZON_CONFIG[summary.primary_horizon]?.label || summary.primary_horizon || 'Unknown'} — ${summary.horizon_label || ''}`;
    const lines: string[] = [
      `# ${summary.topic_title}`,
      `**Horizon:** ${horizonLabel}`,
      '',
      summary.opening_statement,
      '',
    ];

    if (summary.minority_view) {
      // percentage_range / consensus_percentage were removed from the prompt
      // in v3 — the model was inventing them. Only render when present
      // (older cached cards).
      const mvPct = summary.minority_view.percentage_range;
      lines.push(`> *Minority view${mvPct ? ` (${mvPct})` : ''}:* ${summary.minority_view.statement}`);
      lines.push('');
    }

    lines.push(
      typeof summary.consensus_percentage === 'number'
        ? `## Primary Signal (${summary.consensus_percentage}% Consensus)`
        : '## Primary Signal'
    );
    lines.push(summary.primary_signal);
    lines.push('');

    lines.push('## Decision Fork');
    lines.push(`- **If** ${summary.decision_fork.condition_a.condition}: ${summary.decision_fork.condition_a.outcome}`);
    lines.push(`- **If** ${summary.decision_fork.condition_b.condition}: ${summary.decision_fork.condition_b.outcome}`);
    lines.push('');

    lines.push('## Your Window');
    lines.push(`- **${summary.action_window.assessment.timeframe}** to ${summary.action_window.assessment.action}`);
    lines.push(`- **${summary.action_window.positioning.timeframe}** to ${summary.action_window.positioning.action}`);
    lines.push('');

    if (summary.source_scenarios && summary.source_scenarios.length > 0) {
      lines.push('## Source Scenarios');
      summary.source_scenarios.forEach(s => {
        const title = typeof s === 'string' ? s : s.title;
        const horizon = typeof s === 'string' ? '' : ` [${HORIZON_CONFIG[s.horizon]?.label || s.horizon}]`;
        lines.push(`- ${title}${horizon}`);
      });
      lines.push('');
    }

    lines.push('---');
    lines.push(`*Generated by Aunoo AI — ${footerDate}*`);

    const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' });
    const link = document.createElement('a');
    link.download = `${summary.topic_title.replace(/[^a-zA-Z0-9]/g, '_')}.md`;
    link.href = URL.createObjectURL(blob);
    link.click();
    URL.revokeObjectURL(link.href);
  };

  return (
    <>
      <Card
        id={cardId}
        className="executive-summary-card bg-card shadow-md border border-border"
        data-testid={`exec-summary-card-${index}`}
      >
        <CardContent className="p-0">
          {/* Header with title and menu */}
          <div className="p-5 pb-4">
            <div className="flex items-start justify-between gap-3">
              <h2 className="text-lg font-bold tracking-wide text-foreground uppercase">
                {summary.topic_title}
              </h2>

              {/* Menu button - dropdown renders via portal */}
              <button
                ref={buttonRef}
                onClick={() => menuOpen ? setMenuOpen(false) : openMenu()}
                className="h-8 w-8 flex items-center justify-center rounded-md hover:bg-muted transition-colors"
                aria-label="Open menu"
                type="button"
              >
                <MoreVertical className="h-4 w-4 text-muted-foreground" />
              </button>
            </div>

            {/* Opening Statement */}
            <p className="text-sm leading-relaxed text-foreground mt-3">
              {summary.opening_statement}
            </p>

            {/* Minority View */}
            {summary.minority_view && (
              <p className="text-sm text-muted-foreground leading-relaxed mt-3 pl-3 border-l-2 border-muted italic">
                Minority view{summary.minority_view.percentage_range ? ` (${summary.minority_view.percentage_range})` : ''}: {summary.minority_view.statement}
              </p>
            )}
          </div>

          {/* Primary Signal Section */}
          <div className="px-5 py-4 border-t border-border">
            <h3 className={`text-xs font-semibold tracking-wider uppercase mb-2 ${typeof summary.consensus_percentage === 'number' ? getConsensusColorClass(summary.consensus_percentage) : 'text-muted-foreground'}`}>
              {typeof summary.consensus_percentage === 'number'
                ? `PRIMARY SIGNAL (${summary.consensus_percentage}% CONSENSUS)`
                : 'PRIMARY SIGNAL'}
            </h3>
            <p className="text-sm leading-relaxed text-foreground">
              {summary.primary_signal}
            </p>
          </div>

          {/* Decision Fork Section */}
          <div className="px-5 py-4 border-t border-border">
            <h3 className="text-xs font-semibold tracking-wider uppercase text-muted-foreground mb-4">
              DECISION FORK
            </h3>
            <div className="space-y-3">
              {/* Condition A - Green checkmark */}
              <div className="flex items-start gap-3 pl-3 border-l-4 border-green-500 py-2">
                <div className="flex-shrink-0 w-6 h-6 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center mt-0.5">
                  <Check className="w-3.5 h-3.5 text-green-600 dark:text-green-400" />
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">
                    {summary.decision_fork.condition_a.condition}
                  </p>
                  <p className="text-sm text-muted-foreground mt-1">
                    {summary.decision_fork.condition_a.outcome}
                  </p>
                </div>
              </div>

              {/* Condition B - Orange arrow */}
              <div className="flex items-start gap-3 pl-3 border-l-4 border-orange-500 py-2">
                <div className="flex-shrink-0 w-6 h-6 rounded-full bg-orange-100 dark:bg-orange-900/30 flex items-center justify-center mt-0.5">
                  <TrendingUp className="w-3.5 h-3.5 text-orange-600 dark:text-orange-400" />
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">
                    {summary.decision_fork.condition_b.condition}
                  </p>
                  <p className="text-sm text-muted-foreground mt-1">
                    {summary.decision_fork.condition_b.outcome}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Your Window Section */}
          <div className="px-5 py-4 border-t border-border">
            <h3 className="text-xs font-semibold tracking-wider uppercase text-muted-foreground mb-2">
              YOUR WINDOW
            </h3>
            <p className="text-sm text-foreground">
              <span className="font-medium">{summary.action_window.assessment.timeframe}</span>
              {' '}to {summary.action_window.assessment.action};{' '}
              <span className="font-medium">{summary.action_window.positioning.timeframe}</span>
              {' '}to {summary.action_window.positioning.action}.
            </p>
          </div>

          {/* Source Scenarios (collapsed) */}
          {summary.source_scenarios && summary.source_scenarios.length > 0 && (
            <div className="px-5 py-3 border-t border-border">
              <details className="text-xs text-muted-foreground">
                <summary className="cursor-pointer hover:text-foreground transition-colors">
                  Based on {summary.source_scenarios.length} underlying scenario{summary.source_scenarios.length !== 1 ? 's' : ''}
                </summary>
                <ul className="mt-2 pl-4 space-y-1 list-disc">
                  {summary.source_scenarios.map((scenario, sIndex) => {
                    // Handle both old string[] format and new object format
                    const title = typeof scenario === 'string' ? scenario : scenario.title;
                    const horizon = typeof scenario === 'string' ? null : scenario.horizon;
                    return (
                      <li key={sIndex}>
                        {horizon && (
                          <span className={`font-medium ${HORIZON_CONFIG[horizon]?.textClass || ''}`}>
                            [{getHorizonLabel(horizon)}]
                          </span>
                        )}{' '}
                        {title}
                      </li>
                    );
                  })}
                </ul>
              </details>
            </div>
          )}

          {/* Footer */}
          <div className="px-5 py-3 bg-muted/30 border-t border-border flex items-center justify-between text-xs text-muted-foreground">
            <span className="font-medium tracking-wider">AUNOO AI</span>
            <span>{footerDate}</span>
          </div>
        </CardContent>
      </Card>

      {/* Share Modal */}
      <ShareModal
        open={showShareModal}
        onOpenChange={setShowShareModal}
        data={buildShareData()}
      />

      {/* Dropdown menu rendered via portal to document.body */}
      {menuOpen && createPortal(
        <div
          ref={menuRef}
          className="fixed bg-white dark:bg-gray-800 border border-border rounded-md shadow-lg py-1"
          style={{
            top: menuPosition.top,
            left: menuPosition.left,
            width: '180px',
            zIndex: 9999,
          }}
        >
          <button
            onClick={handleDownloadPng}
            className="flex items-center w-full px-3 py-2 text-sm text-left hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            type="button"
          >
            <Download className="mr-2 h-4 w-4" />
            Download as PNG
          </button>
          <button
            onClick={handleDownloadMarkdown}
            className="flex items-center w-full px-3 py-2 text-sm text-left hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            type="button"
          >
            <FileText className="mr-2 h-4 w-4" />
            Download as Markdown
          </button>
          <div className="border-t border-border my-1" />
          <button
            onClick={handleShareClick}
            className="flex items-center w-full px-3 py-2 text-sm text-left hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            type="button"
          >
            <Mail className="mr-2 h-4 w-4" />
            Share via Email
          </button>
        </div>,
        document.body
      )}
    </>
  );
};

export default ExecutiveSummaryCard;
