import html2canvas from 'html2canvas';
import { jsPDF } from 'jspdf';

export class ExportService {
  /**
   * Export dashboard data as JSON
   */
  static exportJSON(data: any, filename: string): void {
    const json = JSON.stringify(data, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${filename}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  /**
   * Export dashboard data as Markdown
   */
  static exportMarkdown(data: any, dashboardType: string, topic: string): void {
    const markdown = this.generateMarkdown(data, dashboardType, topic);
    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${dashboardType.toLowerCase().replace(/\s+/g, '-')}-${topic.toLowerCase().replace(/\s+/g, '-')}-${Date.now()}.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  /**
   * Generate Markdown content with AI disclosure
   */
  private static generateMarkdown(data: any, dashboardType: string, topic: string): string {
    let markdown = `# ${dashboardType} - ${topic}\n\n`;
    markdown += `**Generated**: ${new Date().toLocaleString()}\n\n`;

    // AI Disclosure Section
    markdown += `## AI Technology Disclosure\n\n`;
    markdown += `During the preparation of this ${dashboardType}, the following AI technologies were used:\n\n`;
    markdown += `- **AI Tools**: site-configured large language models, local DeBERTa embeddings\n`;
    markdown += `- **Purpose**: ${this.getPurpose(dashboardType)}\n`;
    markdown += `- **Review Process**: All AI-generated content has been reviewed and validated.\n`;
    markdown += `- **Author Responsibility**: The content creator takes full responsibility for the accuracy and integrity of this analysis.\n\n`;

    // Data sections
    markdown += this.formatDataAsMarkdown(data, dashboardType);

    // References section
    if (data.article_list && data.article_list.length > 0) {
      markdown += `\n## References\n\n`;
      data.article_list.forEach((article: any, idx: number) => {
        markdown += `${idx + 1}. [${article.title || 'Untitled'}](${article.url || '#'})\n`;
      });
    }

    return markdown;
  }

  /**
   * Export dashboard as PDF with pagination support
   */
  static async exportPDF(elementId: string, filename: string): Promise<void> {
    const element = document.getElementById(elementId);
    if (!element) {
      throw new Error(`Element with id '${elementId}' not found`);
    }

    // Store original styles
    const originalOverflow = element.style.overflow;
    const originalHeight = element.style.height;
    const originalMaxHeight = element.style.maxHeight;

    // Find and temporarily show print-only elements
    const printOnlyElements = element.querySelectorAll('.print\\:block');
    const printOnlyOriginalClasses: Map<Element, string> = new Map();

    printOnlyElements.forEach((el) => {
      printOnlyOriginalClasses.set(el, el.className);
      // Remove 'hidden' class to make print-only content visible for capture
      el.className = el.className.replace('hidden', '');
    });

    // Temporarily expand element to capture full content
    element.style.overflow = 'visible';
    element.style.height = 'auto';
    element.style.maxHeight = 'none';

    try {
      const canvas = await html2canvas(element, {
        scale: 1.5, // Reduced from 2 for smaller file size while maintaining readability
        useCORS: true,
        logging: false,
        backgroundColor: '#ffffff',
        windowHeight: element.scrollHeight,
        height: element.scrollHeight
      });

    // Use JPEG with 85% quality for much smaller file sizes
    const imgData = canvas.toDataURL('image/jpeg', 0.85);
    const pdf = new jsPDF({
      orientation: 'portrait',
      unit: 'mm',
      format: 'a4',
      compress: true // Enable PDF compression
    });

    const imgWidth = 210; // A4 width in mm
    const pageHeight = 297; // A4 height in mm
    const imgHeight = (canvas.height * imgWidth) / canvas.width;
    let heightLeft = imgHeight;
    let position = 0;

    // Add first page
    pdf.addImage(imgData, 'JPEG', 0, position, imgWidth, imgHeight, undefined, 'FAST');
    heightLeft -= pageHeight;

    // Add additional pages if content is longer than one page
    while (heightLeft >= 0) {
      position = heightLeft - imgHeight;
      pdf.addPage();
      pdf.addImage(imgData, 'JPEG', 0, position, imgWidth, imgHeight, undefined, 'FAST');
      heightLeft -= pageHeight;
    }

      pdf.save(`${filename}.pdf`);
    } finally {
      // Restore original styles
      element.style.overflow = originalOverflow;
      element.style.height = originalHeight;
      element.style.maxHeight = originalMaxHeight;

      // Restore original classes for print-only elements
      printOnlyOriginalClasses.forEach((originalClass, el) => {
        el.className = originalClass;
      });
    }
  }

  /**
   * Export PDF with section-aware page breaking.
   * Recursively breaks down large sections into their children so that
   * individual cards/charts get their own page-break treatment instead
   * of being sliced through mid-content.  Sorts children by CSS flex
   * order so the PDF matches the visual layout.
   */
  static async exportPDFSectionAware(elementId: string, filename: string): Promise<void> {
    const element = document.getElementById(elementId);
    if (!element) {
      throw new Error(`Element with id '${elementId}' not found`);
    }

    // Store original styles
    const originalOverflow = element.style.overflow;
    const originalHeight = element.style.height;
    const originalMaxHeight = element.style.maxHeight;

    // Find and temporarily show print-only elements
    const printOnlyElements = element.querySelectorAll('.print\\:block');
    const printOnlyOriginalClasses: Map<Element, string> = new Map();

    printOnlyElements.forEach((el) => {
      printOnlyOriginalClasses.set(el, el.className);
      el.className = el.className.replace('hidden', '');
    });

    // Temporarily expand element to capture full content
    element.style.overflow = 'visible';
    element.style.height = 'auto';
    element.style.maxHeight = 'none';

    try {
      const pdf = new jsPDF({
        orientation: 'portrait',
        unit: 'mm',
        format: 'a4',
        compress: true
      });

      const pageWidthMM = 210;
      const pageHeightMM = 297;
      const margin = 8;
      const usableHeight = pageHeightMM - margin * 2;
      const imgWidth = pageWidthMM - margin * 2;
      const sectionGap = 1.5; // mm gap between sections
      let yPosition = margin;

      const html2canvasOpts = {
        scale: 1.5,
        useCORS: true,
        logging: false,
        backgroundColor: '#ffffff',
      };

      // Sort children by CSS flex order, filter out invisible elements
      const getSortedChildren = (parent: HTMLElement): HTMLElement[] => {
        return Array.from(parent.children as HTMLCollectionOf<HTMLElement>)
          .filter(el => el.offsetHeight > 0)
          .sort((a, b) => {
            const orderA = parseInt(window.getComputedStyle(a).order) || 0;
            const orderB = parseInt(window.getComputedStyle(b).order) || 0;
            return orderA - orderB;
          });
      };

      // Render an element to canvas and return height in mm
      const renderToCanvas = async (el: HTMLElement): Promise<{ canvas: HTMLCanvasElement; heightMM: number }> => {
        const canvas = await html2canvas(el, {
          ...html2canvasOpts,
          windowHeight: el.scrollHeight,
          height: el.scrollHeight,
        });
        const heightMM = (canvas.height * imgWidth) / canvas.width;
        return { canvas, heightMM };
      };

      // Place a canvas into the PDF, always filling remaining page space.
      // Content flows continuously — sliced at page boundaries like a
      // printed document rather than leaving large blank areas.
      const placeCanvas = (canvas: HTMLCanvasElement, heightMM: number) => {
        const remainingSpace = pageHeightMM - margin - yPosition;

        // If very little space left (<25mm), start a fresh page
        if (remainingSpace < 25 && yPosition > margin + 1) {
          pdf.addPage();
          yPosition = margin;
        }

        const spaceNow = pageHeightMM - margin - yPosition;

        if (heightMM <= spaceNow) {
          // Fits entirely in remaining space — place directly
          const imgData = canvas.toDataURL('image/jpeg', 0.85);
          pdf.addImage(imgData, 'JPEG', margin, yPosition, imgWidth, heightMM, undefined, 'FAST');
          yPosition += heightMM + sectionGap;
        } else {
          // Slice across page boundary — fill remaining space, continue on next page(s)
          let remaining = heightMM;
          let srcY = 0;

          while (remaining > 0.5) {
            const space = pageHeightMM - margin - yPosition;
            const sliceH = Math.min(space, remaining);
            const ratio = sliceH / heightMM;
            const srcH = canvas.height * ratio;

            const sliceCanvas = document.createElement('canvas');
            sliceCanvas.width = canvas.width;
            sliceCanvas.height = Math.max(1, Math.ceil(srcH));
            const ctx = sliceCanvas.getContext('2d');
            if (ctx) {
              ctx.drawImage(canvas, 0, srcY, canvas.width, srcH, 0, 0, canvas.width, Math.ceil(srcH));
              const sliceImg = sliceCanvas.toDataURL('image/jpeg', 0.85);
              pdf.addImage(sliceImg, 'JPEG', margin, yPosition, imgWidth, sliceH, undefined, 'FAST');
            }

            srcY += srcH;
            remaining -= sliceH;
            yPosition += sliceH;

            if (remaining > 0.5) {
              pdf.addPage();
              yPosition = margin;
            }
          }
          yPosition += sectionGap;
        }
      };

      // Process element: recurse 1 level into children of tall containers
      // to get card-level granularity, then place/slice each card.
      // Only 1 level deep so card visual frames (borders, backgrounds)
      // stay intact in the canvas captures.
      const processElement = async (el: HTMLElement, depth: number = 0) => {
        const { canvas, heightMM } = await renderToCanvas(el);

        const children = getSortedChildren(el);
        if (heightMM <= usableHeight || depth >= 1 || children.length <= 1) {
          // Fits on a page, or already at card level, or atomic — place it
          placeCanvas(canvas, heightMM);
        } else {
          // Tab-level container too tall — break into individual cards
          for (const child of children) {
            await processElement(child, depth + 1);
          }
        }
      };

      // Process top-level sections sorted by CSS order
      const topSections = getSortedChildren(element);
      for (const section of topSections) {
        await processElement(section, 0);
      }

      pdf.save(`${filename}.pdf`);
    } finally {
      // Restore original styles
      element.style.overflow = originalOverflow;
      element.style.height = originalHeight;
      element.style.maxHeight = originalMaxHeight;

      // Restore original classes for print-only elements
      printOnlyOriginalClasses.forEach((originalClass, el) => {
        el.className = originalClass;
      });
    }
  }

  /**
   * Export dashboard as PNG image
   */
  static async exportImage(elementId: string, filename: string): Promise<void> {
    const element = document.getElementById(elementId);
    if (!element) {
      throw new Error(`Element with id '${elementId}' not found`);
    }

    // Store original styles
    const originalOverflow = element.style.overflow;
    const originalHeight = element.style.height;
    const originalMaxHeight = element.style.maxHeight;

    // Find and temporarily show print-only elements
    const printOnlyElements = element.querySelectorAll('.print\\:block');
    const printOnlyOriginalClasses: Map<Element, string> = new Map();

    printOnlyElements.forEach((el) => {
      printOnlyOriginalClasses.set(el, el.className);
      // Remove 'hidden' class to make print-only content visible for capture
      el.className = el.className.replace('hidden', '');
    });

    // Temporarily expand element to capture full content
    element.style.overflow = 'visible';
    element.style.height = 'auto';
    element.style.maxHeight = 'none';

    try {
      const canvas = await html2canvas(element, {
        scale: 2,
        useCORS: true,
        logging: false,
        backgroundColor: '#ffffff',
        windowHeight: element.scrollHeight,
        height: element.scrollHeight
      });

      canvas.toBlob((blob) => {
        if (blob) {
          const url = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = `${filename}.png`;
          link.click();
          URL.revokeObjectURL(url);
        }
      });
    } finally {
      // Restore original styles
      element.style.overflow = originalOverflow;
      element.style.height = originalHeight;
      element.style.maxHeight = originalMaxHeight;

      // Restore original classes for print-only elements
      printOnlyOriginalClasses.forEach((originalClass, el) => {
        el.className = originalClass;
      });
    }
  }

  /**
   * Export Extreme Outliers as text-based PDF
   */
  static exportEOSTextPDF(scenarios: any[], topic: string, metadata?: any): void {
    const pdf = new jsPDF({
      orientation: 'portrait',
      unit: 'mm',
      format: 'a4'
    });

    const pageWidth = 210;
    const pageHeight = 297;
    const margin = 15;
    const contentWidth = pageWidth - (margin * 2);
    let y = margin;

    const addPage = () => {
      pdf.addPage();
      y = margin;
    };

    const checkPageBreak = (neededHeight: number) => {
      if (y + neededHeight > pageHeight - margin) {
        addPage();
      }
    };

    const addText = (text: string, fontSize: number, isBold: boolean = false, color: number[] = [0, 0, 0]) => {
      pdf.setFontSize(fontSize);
      pdf.setFont('helvetica', isBold ? 'bold' : 'normal');
      pdf.setTextColor(color[0], color[1], color[2]);
      const lines = pdf.splitTextToSize(text, contentWidth);
      const lineHeight = fontSize * 0.4;
      checkPageBreak(lines.length * lineHeight + 2);
      pdf.text(lines, margin, y);
      y += lines.length * lineHeight + 2;
    };

    const addSection = (title: string, items: string[], iconColor: number[]) => {
      checkPageBreak(20);
      addText(title, 11, true, iconColor);
      items.forEach(item => {
        addText(`• ${item}`, 10, false);
      });
      y += 3;
    };

    // Title
    addText(`Extreme Outlier Scenarios`, 18, true, [128, 0, 128]);
    addText(`Topic: ${topic}`, 12, false, [100, 100, 100]);
    addText(`Generated: ${new Date().toLocaleString()}`, 10, false, [150, 150, 150]);
    y += 5;

    // Metadata summary
    if (metadata) {
      addText(`Analysis Summary: ${metadata.signals_detected || 0} signals detected, ${metadata.pathways_explored || 0} pathways explored, ${metadata.scenarios_generated || 0} scenarios generated`, 10, false, [100, 100, 100]);
      y += 5;
    }

    // AI Disclosure
    checkPageBreak(30);
    addText('AI Technology Disclosure', 12, true);
    addText('This analysis was generated using AI technologies (site-configured large language models, local DeBERTa embeddings) for extreme scenario planning and risk identification. All content should be reviewed and validated by domain experts.', 9, false, [100, 100, 100]);
    y += 8;

    // Category colors
    const categoryColors: Record<string, number[]> = {
      black_swan: [128, 0, 128],
      contrarian: [180, 120, 0],
      wild_card: [0, 100, 200]
    };

    const categoryLabels: Record<string, string> = {
      black_swan: 'Black Swan Event',
      contrarian: 'Contrarian Analysis',
      wild_card: 'Wild Card Future'
    };

    // Group scenarios by category
    const blackSwans = scenarios.filter(s => s.category === 'black_swan');
    const contrarian = scenarios.filter(s => s.category === 'contrarian');
    const wildCards = scenarios.filter(s => s.category === 'wild_card');

    const renderScenarios = (scenarioList: any[], categoryName: string) => {
      if (scenarioList.length === 0) return;

      checkPageBreak(15);
      addText(`${categoryLabels[categoryName]} (${scenarioList.length})`, 14, true, categoryColors[categoryName]);
      y += 3;

      scenarioList.forEach((scenario, idx) => {
        checkPageBreak(40);

        // Scenario header
        addText(`${idx + 1}. ${scenario.title}`, 12, true);
        if (scenario.subtitle) {
          addText(scenario.subtitle, 10, false, [80, 80, 80]);
        }
        y += 2;

        // Badges line
        addText(`Probability: ${(scenario.probability || 'unknown').replace('_', ' ')} | Impact: ${scenario.impact_rating || 'N/A'}/10 | Time Horizon: ${scenario.time_horizon || 'N/A'}`, 9, false, [100, 100, 100]);
        y += 3;

        // Description
        addText(scenario.description || '', 10, false);
        y += 3;

        // Trigger Events
        if (scenario.trigger_events?.length > 0) {
          addSection('Trigger Events', scenario.trigger_events, [200, 50, 50]);
        }

        // Weak Signals
        if (scenario.weak_signals?.length > 0) {
          addSection('Weak Signals Detected', scenario.weak_signals, [0, 100, 200]);
        }

        // Amplification Path
        if (scenario.amplification_path) {
          checkPageBreak(15);
          addText('Amplification Path', 11, true, [200, 120, 0]);
          addText(scenario.amplification_path, 10, false);
          y += 3;
        }

        // Early Warning Signs
        if (scenario.early_warning_signs?.length > 0) {
          addSection('Early Warning Signs', scenario.early_warning_signs, [200, 180, 0]);
        }

        // Strategic Implications
        if (scenario.strategic_implications) {
          checkPageBreak(15);
          addText('Strategic Implications', 11, true, [128, 0, 128]);
          addText(scenario.strategic_implications, 10, false);
          y += 3;
        }

        // Preparation Actions
        if (scenario.preparation_actions?.length > 0) {
          addSection('Preparation Actions', scenario.preparation_actions, [0, 150, 50]);
        }

        // Source info
        if (scenario.source_trends?.length > 0 || scenario.source_consensus?.length > 0) {
          checkPageBreak(15);
          addText('Derived From:', 9, true, [150, 150, 150]);
          if (scenario.source_trends?.length > 0) {
            addText(`Trends: ${scenario.source_trends.join(', ')}`, 8, false, [150, 150, 150]);
          }
          if (scenario.source_consensus?.length > 0) {
            addText(`Consensus: ${scenario.source_consensus.join(', ')}`, 8, false, [150, 150, 150]);
          }
        }

        y += 8; // Space between scenarios
      });
    };

    renderScenarios(blackSwans, 'black_swan');
    renderScenarios(contrarian, 'contrarian');
    renderScenarios(wildCards, 'wild_card');

    // Footer on last page
    const totalPages = pdf.getNumberOfPages();
    for (let i = 1; i <= totalPages; i++) {
      pdf.setPage(i);
      pdf.setFontSize(8);
      pdf.setTextColor(150, 150, 150);
      pdf.text(`Page ${i} of ${totalPages}`, pageWidth / 2, pageHeight - 10, { align: 'center' });
      pdf.text('Generated by Aunoo AI - Extreme Outlier Scenarios', pageWidth / 2, pageHeight - 5, { align: 'center' });
    }

    pdf.save(`extreme-outliers-${topic.toLowerCase().replace(/\s+/g, '-')}-${Date.now()}.pdf`);
  }

  /**
   * Export Extreme Outliers as Markdown
   */
  static exportEOSMarkdown(scenarios: any[], topic: string, metadata?: any): void {
    let md = `# Extreme Outlier Scenarios\n\n`;
    md += `**Topic:** ${topic}\n`;
    md += `**Generated:** ${new Date().toLocaleString()}\n\n`;

    if (metadata) {
      md += `**Analysis Summary:** ${metadata.signals_detected || 0} signals detected, ${metadata.pathways_explored || 0} pathways explored, ${metadata.scenarios_generated || 0} scenarios generated\n\n`;
    }

    md += `## AI Technology Disclosure\n\n`;
    md += `This analysis was generated using AI technologies (site-configured large language models, local DeBERTa embeddings) for extreme scenario planning and risk identification. All content should be reviewed and validated by domain experts.\n\n`;
    md += `---\n\n`;

    const categoryLabels: Record<string, string> = {
      black_swan: 'Black Swan Events',
      contrarian: 'Contrarian Analysis',
      wild_card: 'Wild Card Futures'
    };

    const blackSwans = scenarios.filter(s => s.category === 'black_swan');
    const contrarian = scenarios.filter(s => s.category === 'contrarian');
    const wildCards = scenarios.filter(s => s.category === 'wild_card');

    const renderScenarios = (scenarioList: any[], categoryName: string) => {
      if (scenarioList.length === 0) return;

      md += `## ${categoryLabels[categoryName]} (${scenarioList.length})\n\n`;

      scenarioList.forEach((scenario, idx) => {
        md += `### ${idx + 1}. ${scenario.title}\n\n`;
        if (scenario.subtitle) {
          md += `*${scenario.subtitle}*\n\n`;
        }

        md += `| Probability | Impact | Time Horizon |\n`;
        md += `|-------------|--------|-------------|\n`;
        md += `| ${(scenario.probability || 'unknown').replace('_', ' ')} | ${scenario.impact_rating || 'N/A'}/10 | ${scenario.time_horizon || 'N/A'} |\n\n`;

        md += `${scenario.description || ''}\n\n`;

        if (scenario.trigger_events?.length > 0) {
          md += `#### Trigger Events\n`;
          scenario.trigger_events.forEach((e: string) => md += `- ${e}\n`);
          md += `\n`;
        }

        if (scenario.weak_signals?.length > 0) {
          md += `#### Weak Signals Detected\n`;
          scenario.weak_signals.forEach((s: string) => md += `- ${s}\n`);
          md += `\n`;
        }

        if (scenario.amplification_path) {
          md += `#### Amplification Path\n${scenario.amplification_path}\n\n`;
        }

        if (scenario.early_warning_signs?.length > 0) {
          md += `#### Early Warning Signs\n`;
          scenario.early_warning_signs.forEach((s: string) => md += `- ${s}\n`);
          md += `\n`;
        }

        if (scenario.strategic_implications) {
          md += `#### Strategic Implications\n${scenario.strategic_implications}\n\n`;
        }

        if (scenario.preparation_actions?.length > 0) {
          md += `#### Preparation Actions\n`;
          scenario.preparation_actions.forEach((a: string, i: number) => md += `${i + 1}. ${a}\n`);
          md += `\n`;
        }

        if (scenario.source_trends?.length > 0 || scenario.source_consensus?.length > 0) {
          md += `> **Derived From:**\n`;
          if (scenario.source_trends?.length > 0) {
            md += `> Trends: ${scenario.source_trends.join(', ')}\n`;
          }
          if (scenario.source_consensus?.length > 0) {
            md += `> Consensus: ${scenario.source_consensus.join(', ')}\n`;
          }
          md += `\n`;
        }

        md += `---\n\n`;
      });
    };

    renderScenarios(blackSwans, 'black_swan');
    renderScenarios(contrarian, 'contrarian');
    renderScenarios(wildCards, 'wild_card');

    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `extreme-outliers-${topic.toLowerCase().replace(/\s+/g, '-')}-${Date.now()}.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  /**
   * Export Focus Group as text-based PDF
   */
  static exportFocusGroupTextPDF(result: any, topic: string): void {
    const pdf = new jsPDF({
      orientation: 'portrait',
      unit: 'mm',
      format: 'a4'
    });

    const pageWidth = 210;
    const pageHeight = 297;
    const margin = 15;
    const contentWidth = pageWidth - (margin * 2);
    let y = margin;

    const addPage = () => {
      pdf.addPage();
      y = margin;
    };

    const checkPageBreak = (neededHeight: number) => {
      if (y + neededHeight > pageHeight - margin) {
        addPage();
      }
    };

    const addText = (text: string, fontSize: number, isBold: boolean = false, color: number[] = [0, 0, 0]) => {
      pdf.setFontSize(fontSize);
      pdf.setFont('helvetica', isBold ? 'bold' : 'normal');
      pdf.setTextColor(color[0], color[1], color[2]);
      const lines = pdf.splitTextToSize(text, contentWidth);
      const lineHeight = fontSize * 0.4;
      checkPageBreak(lines.length * lineHeight + 2);
      pdf.text(lines, margin, y);
      y += lines.length * lineHeight + 2;
    };

    const addSection = (title: string, items: string[], iconColor: number[]) => {
      checkPageBreak(20);
      addText(title, 11, true, iconColor);
      items.forEach(item => {
        addText(`• ${item}`, 10, false);
      });
      y += 3;
    };

    // Title
    addText(`Focus Group Analysis`, 18, true, [0, 128, 128]);
    addText(`Topic: ${topic}`, 12, false, [100, 100, 100]);
    addText(`Generated: ${result.metadata?.generated_at ? new Date(result.metadata.generated_at).toLocaleString() : new Date().toLocaleString()}`, 10, false, [150, 150, 150]);
    y += 5;

    // Metadata summary
    if (result.metadata) {
      addText(`Analysis Summary: ${result.metadata.articles_analyzed || 0} articles analyzed, ${result.metadata.mentions_found || 0} mentions found, ${result.metadata.personas_generated || 0} personas generated`, 10, false, [100, 100, 100]);
      y += 5;
    }

    // AI Disclosure
    checkPageBreak(30);
    addText('AI Technology Disclosure', 12, true);
    addText('This analysis was generated using AI technologies (site-configured large language models, local DeBERTa embeddings) for audience persona development. All content should be reviewed and validated by domain experts.', 9, false, [100, 100, 100]);
    y += 8;

    // Focus Group Summary
    if (result.focus_group_summary) {
      checkPageBreak(30);
      addText('Focus Group Summary', 14, true, [0, 100, 100]);
      addText(result.focus_group_summary, 10, false);
      y += 8;
    }

    // Interaction Dynamics
    if (result.interaction_dynamics) {
      const dynamics = result.interaction_dynamics;

      // Consensus Areas
      if (dynamics.consensus_areas?.length > 0) {
        checkPageBreak(20);
        addText('Consensus Areas', 14, true, [0, 150, 50]);
        dynamics.consensus_areas.forEach((area: any) => {
          checkPageBreak(15);
          addText(`${area.topic}`, 11, true);
          addText(area.description, 10, false);
          if (area.supporting_personas?.length > 0) {
            addText(`Supporting personas: ${area.supporting_personas.join(', ')}`, 9, false, [100, 100, 100]);
          }
          y += 3;
        });
        y += 5;
      }

      // Tension Points
      if (dynamics.tension_points?.length > 0) {
        checkPageBreak(20);
        addText('Tension Points', 14, true, [200, 100, 0]);
        dynamics.tension_points.forEach((tension: any) => {
          checkPageBreak(20);
          addText(`${tension.topic}`, 11, true);
          addText(tension.description, 10, false);
          if (tension.opposing_sides) {
            addText(`Side A: ${tension.opposing_sides.side_a?.join(', ') || 'N/A'}`, 9, false, [100, 100, 100]);
            addText(`Side B: ${tension.opposing_sides.side_b?.join(', ') || 'N/A'}`, 9, false, [100, 100, 100]);
          }
          y += 3;
        });
        y += 5;
      }

      // Power Dynamics
      if (dynamics.power_dynamics) {
        checkPageBreak(20);
        addText('Power Dynamics', 14, true, [128, 0, 128]);
        if (dynamics.power_dynamics.most_influential) {
          addText(`Most Influential: ${dynamics.power_dynamics.most_influential}`, 10, false);
        }
        if (dynamics.power_dynamics.most_vulnerable) {
          addText(`Most Vulnerable: ${dynamics.power_dynamics.most_vulnerable}`, 10, false);
        }
        if (dynamics.power_dynamics.likely_coalition?.length > 0) {
          addText(`Likely Coalition: ${dynamics.power_dynamics.likely_coalition.join(', ')}`, 10, false);
        }
        y += 5;
      }
    }

    // Personas
    if (result.personas?.length > 0) {
      checkPageBreak(15);
      addText(`Personas (${result.personas.length})`, 16, true, [0, 100, 150]);
      y += 5;

      result.personas.forEach((persona: any, idx: number) => {
        checkPageBreak(60);

        // Persona header
        addText(`${idx + 1}. ${persona.name}`, 13, true);
        addText(`${persona.archetype} - ${persona.role_title}`, 11, false, [80, 80, 80]);
        y += 2;

        // Key attributes
        addText(`Sector: ${persona.sector} | Experience: ${persona.experience_level} | Decision Authority: ${persona.decision_authority?.replace('_', ' ')}`, 9, false, [100, 100, 100]);
        y += 3;

        // Psychographic traits
        if (persona.risk_tolerance !== undefined) {
          addText(`Risk Tolerance: ${persona.risk_tolerance}/10 | Change Receptivity: ${persona.change_receptivity} | Technology Stance: ${persona.technology_stance}`, 9, false, [100, 100, 100]);
        }
        y += 3;

        // Voice description
        if (persona.voice_description) {
          addText('Voice:', 10, true, [0, 100, 100]);
          addText(persona.voice_description, 10, false);
          y += 2;
        }

        // Primary concerns
        if (persona.primary_concerns?.length > 0) {
          addSection('Primary Concerns', persona.primary_concerns, [200, 50, 50]);
        }

        // Opportunity interests
        if (persona.opportunity_interests?.length > 0) {
          addSection('Opportunity Interests', persona.opportunity_interests, [0, 150, 50]);
        }

        // Fear triggers
        if (persona.fear_triggers?.length > 0) {
          addSection('Fear Triggers', persona.fear_triggers, [200, 100, 0]);
        }

        // Typical questions
        if (persona.typical_questions?.length > 0) {
          addSection('Typical Questions', persona.typical_questions, [0, 100, 200]);
        }

        // Decision factors
        if (persona.decision_factors?.length > 0) {
          addSection('Decision Factors', persona.decision_factors, [128, 0, 128]);
        }

        // Confidence
        if (persona.confidence_score !== undefined) {
          addText(`Confidence Score: ${(persona.confidence_score * 100).toFixed(0)}% | Based on ${persona.mention_count || 0} mentions`, 9, false, [150, 150, 150]);
        }

        y += 10; // Space between personas
      });
    }

    // Footer on all pages
    const totalPages = pdf.getNumberOfPages();
    for (let i = 1; i <= totalPages; i++) {
      pdf.setPage(i);
      pdf.setFontSize(8);
      pdf.setTextColor(150, 150, 150);
      pdf.text(`Page ${i} of ${totalPages}`, pageWidth / 2, pageHeight - 10, { align: 'center' });
      pdf.text('Generated by Aunoo AI - Focus Group Analysis', pageWidth / 2, pageHeight - 5, { align: 'center' });
    }

    pdf.save(`focus-group-${topic.toLowerCase().replace(/\s+/g, '-')}-${Date.now()}.pdf`);
  }

  /**
   * Export Focus Group as Markdown
   */
  static exportFocusGroupMarkdown(result: any, topic: string): void {
    let md = `# Focus Group Analysis\n\n`;
    md += `**Topic:** ${topic}\n`;
    md += `**Generated:** ${result.metadata?.generated_at ? new Date(result.metadata.generated_at).toLocaleString() : new Date().toLocaleString()}\n\n`;

    if (result.metadata) {
      md += `**Analysis Summary:** ${result.metadata.articles_analyzed || 0} articles analyzed, ${result.metadata.mentions_found || 0} mentions found, ${result.metadata.personas_generated || 0} personas generated\n\n`;
    }

    md += `## AI Technology Disclosure\n\n`;
    md += `This analysis was generated using AI technologies (site-configured large language models, local DeBERTa embeddings) for audience persona development. All content should be reviewed and validated by domain experts.\n\n`;
    md += `---\n\n`;

    // Focus Group Summary
    if (result.focus_group_summary) {
      md += `## Focus Group Summary\n\n${result.focus_group_summary}\n\n`;
    }

    // Interaction Dynamics
    if (result.interaction_dynamics) {
      const dynamics = result.interaction_dynamics;

      if (dynamics.consensus_areas?.length > 0) {
        md += `## Consensus Areas\n\n`;
        dynamics.consensus_areas.forEach((area: any) => {
          md += `### ${area.topic}\n\n`;
          md += `${area.description}\n\n`;
          if (area.supporting_personas?.length > 0) {
            md += `*Supporting personas: ${area.supporting_personas.join(', ')}*\n\n`;
          }
        });
      }

      if (dynamics.tension_points?.length > 0) {
        md += `## Tension Points\n\n`;
        dynamics.tension_points.forEach((tension: any) => {
          md += `### ${tension.topic}\n\n`;
          md += `${tension.description}\n\n`;
          if (tension.opposing_sides) {
            md += `| Side A | Side B |\n|--------|--------|\n`;
            md += `| ${tension.opposing_sides.side_a?.join(', ') || 'N/A'} | ${tension.opposing_sides.side_b?.join(', ') || 'N/A'} |\n\n`;
          }
        });
      }

      if (dynamics.power_dynamics) {
        md += `## Power Dynamics\n\n`;
        md += `| Aspect | Persona |\n|--------|--------|\n`;
        if (dynamics.power_dynamics.most_influential) {
          md += `| Most Influential | ${dynamics.power_dynamics.most_influential} |\n`;
        }
        if (dynamics.power_dynamics.most_vulnerable) {
          md += `| Most Vulnerable | ${dynamics.power_dynamics.most_vulnerable} |\n`;
        }
        if (dynamics.power_dynamics.likely_coalition?.length > 0) {
          md += `| Likely Coalition | ${dynamics.power_dynamics.likely_coalition.join(', ')} |\n`;
        }
        md += `\n`;
      }
    }

    // Personas
    if (result.personas?.length > 0) {
      md += `## Personas (${result.personas.length})\n\n`;

      result.personas.forEach((persona: any, idx: number) => {
        md += `### ${idx + 1}. ${persona.name}\n\n`;
        md += `**${persona.archetype}** - ${persona.role_title}\n\n`;

        md += `| Attribute | Value |\n|-----------|-------|\n`;
        md += `| Sector | ${persona.sector} |\n`;
        md += `| Experience | ${persona.experience_level} |\n`;
        md += `| Decision Authority | ${persona.decision_authority?.replace('_', ' ')} |\n`;
        if (persona.risk_tolerance !== undefined) {
          md += `| Risk Tolerance | ${persona.risk_tolerance}/10 |\n`;
        }
        md += `| Change Receptivity | ${persona.change_receptivity} |\n`;
        md += `| Technology Stance | ${persona.technology_stance} |\n`;
        md += `\n`;

        if (persona.voice_description) {
          md += `#### Voice\n${persona.voice_description}\n\n`;
        }

        if (persona.primary_concerns?.length > 0) {
          md += `#### Primary Concerns\n`;
          persona.primary_concerns.forEach((c: string) => md += `- ${c}\n`);
          md += `\n`;
        }

        if (persona.opportunity_interests?.length > 0) {
          md += `#### Opportunity Interests\n`;
          persona.opportunity_interests.forEach((o: string) => md += `- ${o}\n`);
          md += `\n`;
        }

        if (persona.fear_triggers?.length > 0) {
          md += `#### Fear Triggers\n`;
          persona.fear_triggers.forEach((f: string) => md += `- ${f}\n`);
          md += `\n`;
        }

        if (persona.typical_questions?.length > 0) {
          md += `#### Typical Questions\n`;
          persona.typical_questions.forEach((q: string) => md += `- ${q}\n`);
          md += `\n`;
        }

        if (persona.decision_factors?.length > 0) {
          md += `#### Decision Factors\n`;
          persona.decision_factors.forEach((d: string) => md += `- ${d}\n`);
          md += `\n`;
        }

        if (persona.confidence_score !== undefined) {
          md += `> Confidence: ${(persona.confidence_score * 100).toFixed(0)}% | Based on ${persona.mention_count || 0} mentions\n\n`;
        }

        md += `---\n\n`;
      });
    }

    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `focus-group-${topic.toLowerCase().replace(/\s+/g, '-')}-${Date.now()}.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  /**
   * Helper: Get purpose text for dashboard type
   */
  private static getPurpose(dashboardType: string): string {
    const purposes: Record<string, string> = {
      'Consensus Analysis': 'To analyze convergent themes across multiple sources',
      'Strategic Recommendations': 'To synthesize actionable strategic insights',
      'Market Signals': 'To identify market trends, risks, and opportunities',
      'Impact Timeline': 'To project temporal sequences of anticipated impacts',
      'Future Horizons': 'To explore long-term implications and future scenarios',
      'Extreme Outliers': 'To identify black swan events, contrarian views, and wild card scenarios'
    };
    return purposes[dashboardType] || 'Advanced analysis and insight generation';
  }

  /**
   * Helper: Format data as Markdown sections
   */
  private static formatDataAsMarkdown(data: any, dashboardType: string): string {
    // Dashboard-specific formatting
    switch (dashboardType) {
      case 'Consensus Analysis':
        return this.formatConsensusMarkdown(data);
      case 'Strategic Recommendations':
        return this.formatRecommendationsMarkdown(data);
      case 'Market Signals':
        return this.formatSignalsMarkdown(data);
      case 'Impact Timeline':
        return this.formatTimelineMarkdown(data);
      case 'Future Horizons':
        return this.formatHorizonsMarkdown(data);
      default:
        return `\n## Data\n\n\`\`\`json\n${JSON.stringify(data, null, 2)}\n\`\`\`\n`;
    }
  }

  // Format methods for each dashboard type
  private static formatConsensusMarkdown(data: any): string {
    let md = '\n## Consensus Categories\n\n';
    data.categories?.forEach((cat: any) => {
      md += `### ${cat.category}\n\n`;
      md += `**Consensus Level**: ${cat.consensus_level}\n\n`;
      md += `${cat.description}\n\n`;
      if (cat.key_points) {
        md += '**Key Points**:\n';
        cat.key_points.forEach((point: string) => {
          md += `- ${point}\n`;
        });
        md += '\n';
      }
    });
    return md;
  }

  private static formatRecommendationsMarkdown(data: any): string {
    let md = '\n## Strategic Recommendations\n\n';
    data.recommendations?.forEach((rec: any, idx: number) => {
      md += `### ${idx + 1}. ${rec.title}\n\n`;
      md += `**Priority**: ${rec.priority || 'Medium'}\n\n`;
      md += `${rec.description}\n\n`;
      if (rec.action_items) {
        md += '**Action Items**:\n';
        rec.action_items.forEach((item: string) => {
          md += `- ${item}\n`;
        });
        md += '\n';
      }
    });
    return md;
  }

  private static formatSignalsMarkdown(data: any): string {
    let md = '\n## Market Signals & Strategic Risks\n\n';

    if (data.opportunities) {
      md += '### Opportunities\n\n';
      data.opportunities.forEach((opp: any, idx: number) => {
        md += `${idx + 1}. **${opp.title}**: ${opp.description}\n`;
      });
      md += '\n';
    }

    if (data.risks) {
      md += '### Risks\n\n';
      data.risks.forEach((risk: any, idx: number) => {
        md += `${idx + 1}. **${risk.title}**: ${risk.description}\n`;
      });
      md += '\n';
    }

    return md;
  }

  private static formatTimelineMarkdown(data: any): string {
    let md = '\n## Impact Timeline\n\n';

    const timeframes = ['immediate', 'near_term', 'medium_term', 'long_term'];
    timeframes.forEach((tf) => {
      const impacts = data[tf] || [];
      if (impacts.length > 0) {
        md += `### ${tf.replace('_', ' ').toUpperCase()}\n\n`;
        impacts.forEach((impact: any) => {
          md += `- **${impact.title}**: ${impact.description}\n`;
        });
        md += '\n';
      }
    });

    return md;
  }

  private static formatHorizonsMarkdown(data: any): string {
    let md = '\n## Future Horizons\n\n';

    data.horizons?.forEach((horizon: any) => {
      md += `### ${horizon.title}\n\n`;
      md += `**Timeframe**: ${horizon.timeframe}\n\n`;
      md += `${horizon.description}\n\n`;
      if (horizon.implications) {
        md += '**Implications**:\n';
        horizon.implications.forEach((imp: string) => {
          md += `- ${imp}\n`;
        });
        md += '\n';
      }
    });

    return md;
  }

  /**
   * Export Your Briefing as Markdown
   */
  static exportBriefingMarkdown(briefing: any, persona: string, model?: string): void {
    let md = `# Executive Briefing - ${persona}\n\n`;
    md += `*Generated: ${new Date(briefing.generated_at).toLocaleString()}*\n\n`;

    // AI Disclosure
    md += `## AI Technology Disclosure\n\n`;
    const modelInfo = model || briefing.model || 'AI';
    md += `This briefing was generated using **${modelInfo}**. All content has been reviewed for accuracy.\n\n`;

    // Executive Summary
    if (briefing.executive_summary) {
      md += `## Executive Summary\n\n${briefing.executive_summary}\n\n`;
    }

    // Key Themes
    if (briefing.key_themes?.length) {
      md += `## Key Themes\n\n`;
      briefing.key_themes.forEach((theme: string) => {
        md += `- ${theme}\n`;
      });
      md += '\n';
    }

    // Top Stories
    md += `## Top Stories\n\n`;
    const articles = briefing.articles || [];
    articles.forEach((article: any, i: number) => {
      const title = article.title || article.headline || 'Untitled';
      md += `### ${i + 1}. ${title}\n\n`;

      // Metadata
      const source = article.source || article.primary_article?.source?.name || '';
      const date = article.date || article.primary_article?.publication_date || '';
      if (source || date) {
        md += `**Source:** ${source}`;
        if (date) md += ` | **Date:** ${date}`;
        md += '\n\n';
      }

      // Classification badges
      const badges: string[] = [];
      if (article.category) badges.push(`Category: ${article.category}`);
      if (article.time_horizon) badges.push(`Time Horizon: ${article.time_horizon}`);
      if (article.risk_opportunity) badges.push(`Classification: ${article.risk_opportunity}`);
      if (article.signal_strength) badges.push(`Signal: ${article.signal_strength}`);
      if (badges.length) {
        md += `*${badges.join(' | ')}*\n\n`;
      }

      // Executive Takeaway
      if (article.executive_takeaway) {
        md += `**Why It Matters:** ${article.executive_takeaway}\n\n`;
      }

      // Summary
      const summary = article.summary || article.primary_article?.summary || '';
      if (summary) {
        md += `${summary}\n\n`;
      }

      // Strategic Relevance
      if (article.strategic_relevance) {
        md += `**Strategic Relevance:** ${article.strategic_relevance}\n\n`;
      }

      // Executive Actions
      if (article.executive_action?.length) {
        md += `**Recommended Actions:**\n`;
        article.executive_action.forEach((action: string) => {
          md += `- ${action}\n`;
        });
        md += '\n';
      }

      // Scores
      if (article.scores?.overall) {
        md += `**Score:** ${article.scores.overall}/5\n\n`;
      }

      // URL
      const url = article.url || article.uri || article.primary_article?.url || '';
      if (url) {
        md += `[Read Full Article](${url})\n\n`;
      }

      md += `---\n\n`;
    });

    // Download
    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    const dateStr = new Date().toISOString().split('T')[0];
    link.download = `briefing-${persona.toLowerCase()}-${dateStr}.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  /**
   * Export Your Briefing as CSV
   */
  static exportBriefingCSV(briefing: any): void {
    const headers = [
      'Title',
      'Source',
      'Date',
      'Category',
      'Time Horizon',
      'Risk/Opportunity',
      'Signal Strength',
      'Score',
      'Executive Takeaway',
      'Strategic Relevance',
      'Actions',
      'URL'
    ];

    const articles = briefing.articles || [];
    const rows = articles.map((a: any) => {
      const escapeCSV = (str: string) => {
        if (!str) return '';
        // Escape double quotes and wrap in quotes if contains comma, quote, or newline
        const escaped = String(str).replace(/"/g, '""');
        return `"${escaped}"`;
      };

      return [
        escapeCSV(a.title || a.headline || ''),
        escapeCSV(a.source || a.primary_article?.source?.name || ''),
        escapeCSV(a.date || a.primary_article?.publication_date || ''),
        escapeCSV(a.category || ''),
        escapeCSV(a.time_horizon || ''),
        escapeCSV(a.risk_opportunity || ''),
        escapeCSV(a.signal_strength || ''),
        escapeCSV(a.scores?.overall ? `${a.scores.overall}/5` : ''),
        escapeCSV(a.executive_takeaway || ''),
        escapeCSV(a.strategic_relevance || ''),
        escapeCSV(a.executive_action?.join('; ') || ''),
        escapeCSV(a.url || a.uri || a.primary_article?.url || '')
      ].join(',');
    });

    const csv = [headers.join(','), ...rows].join('\n');

    // Download
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    const dateStr = new Date().toISOString().split('T')[0];
    link.download = `briefing-${dateStr}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  /**
   * Export Incidents as Markdown
   */
  static exportIncidentsMarkdown(incidents: any[], topic?: string, model?: string): void {
    let md = `# Incidents Report${topic ? ` - ${topic}` : ''}\n\n`;
    md += `*Generated: ${new Date().toLocaleString()}*\n\n`;

    // AI Disclosure
    md += `## AI Technology Disclosure\n\n`;
    const modelInfo = model || 'AI';
    md += `This report was generated using **${modelInfo}**. All content has been reviewed for accuracy.\n\n`;

    md += `## Incidents (${incidents.length})\n\n`;

    incidents.forEach((incident, i) => {
      const name = incident.name || incident.title || 'Unnamed Incident';
      const description = incident.description || incident.summary || '';

      md += `### ${i + 1}. ${name}\n\n`;

      // Classification badges
      const badges: string[] = [];
      if (incident.type) badges.push(`Type: ${incident.type}`);
      if (incident.significance) badges.push(`Significance: ${incident.significance}`);
      if (incident.status) badges.push(`Status: ${incident.status}`);
      if (incident.first_seen) badges.push(`First seen: ${incident.first_seen}`);
      if (badges.length) {
        md += `*${badges.join(' | ')}*\n\n`;
      }

      if (description) {
        md += `${description}\n\n`;
      }

      // Organizational relevance
      if (incident.organizational_relevance) {
        md += `**Organizational Relevance:** ${incident.organizational_relevance}\n\n`;
      }

      // Credibility summary
      if (incident.credibility_summary) {
        md += `**Credibility:** ${incident.credibility_summary}\n\n`;
      }

      // Entities
      if (incident.entities?.length) {
        md += `**Entities:** ${incident.entities.join(', ')}\n\n`;
      }

      // Investigation leads
      if (incident.investigation_leads?.length) {
        md += `**Investigation Leads:**\n`;
        incident.investigation_leads.forEach((lead: string) => {
          md += `- ${lead}\n`;
        });
        md += '\n';
      }

      // Related articles with URLs
      if (incident.articles?.length) {
        md += `**Sources (${incident.articles.length}):**\n`;
        incident.articles.slice(0, 10).forEach((article: any) => {
          const title = article.title || 'Untitled';
          const source = article.source || article.news_source || '';
          const url = article.uri || article.url || '';
          if (url) {
            md += `- [${title}](${url})${source ? ` (${source})` : ''}\n`;
          } else {
            md += `- ${title}${source ? ` (${source})` : ''}\n`;
          }
        });
        if (incident.articles.length > 10) {
          md += `- ... and ${incident.articles.length - 10} more\n`;
        }
        md += '\n';
      }

      md += `---\n\n`;
    });

    // Download
    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    const dateStr = new Date().toISOString().split('T')[0];
    link.download = `incidents-${dateStr}.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  /**
   * Export Incidents as CSV
   */
  static exportIncidentsCSV(incidents: any[]): void {
    const headers = [
      'Name',
      'Type',
      'Significance',
      'Status',
      'Description',
      'Organizational Relevance',
      'Credibility Summary',
      'Entities',
      'Investigation Leads',
      'Article Count',
      'First Seen',
      'Last Seen',
      'Primary Article URL',
      'All Article URLs'
    ];

    const rows = incidents.map((incident: any) => {
      const escapeCSV = (str: string) => {
        if (!str) return '';
        const escaped = String(str).replace(/"/g, '""');
        return `"${escaped}"`;
      };

      // Get article URLs
      const articleUrls = incident.articles?.map((a: any) => a.uri || a.url).filter(Boolean) || [];
      const primaryUrl = articleUrls[0] || '';

      return [
        escapeCSV(incident.name || incident.title || ''),
        escapeCSV(incident.type || ''),
        escapeCSV(incident.significance || ''),
        escapeCSV(incident.status || ''),
        escapeCSV(incident.description || incident.summary || ''),
        escapeCSV(incident.organizational_relevance || ''),
        escapeCSV(incident.credibility_summary || ''),
        escapeCSV(incident.entities?.join('; ') || ''),
        escapeCSV(incident.investigation_leads?.join('; ') || ''),
        escapeCSV(String(incident.articles?.length || 0)),
        escapeCSV(incident.first_seen || ''),
        escapeCSV(incident.last_seen || ''),
        escapeCSV(primaryUrl),
        escapeCSV(articleUrls.join('; '))
      ].join(',');
    });

    const csv = [headers.join(','), ...rows].join('\n');

    // Download
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    const dateStr = new Date().toISOString().split('T')[0];
    link.download = `incidents-${dateStr}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  /**
   * Export Incidents as styled Markdown (similar to email layout)
   */
  static exportIncidentsStyledMarkdown(incidents: any[], topic?: string, model?: string): void {
    const dateStr = new Date().toISOString().split('T')[0];
    const modelInfo = model || 'AI';

    let md = `# 🎯 Incident Report\n\n`;
    if (topic) md += `**Topic:** ${topic}\n\n`;
    md += `**Generated:** ${new Date().toLocaleString()}\n`;
    md += `**Total Incidents:** ${incidents.length}\n\n`;
    md += `---\n\n`;

    // AI Disclosure
    md += `## ℹ️ AI Technology Disclosure\n\n`;
    md += `> This report was generated using **${modelInfo}**. All content has been reviewed for accuracy.\n\n`;
    md += `---\n\n`;

    incidents.forEach((incident, i) => {
      const name = incident.name || incident.title || 'Unnamed Incident';
      const description = incident.description || incident.summary || '';
      const type = incident.type || 'event';
      const significance = incident.significance || 'medium';

      md += `## ${i + 1}. ${name}\n\n`;

      // Badges as inline code
      const badges: string[] = [];
      if (type) badges.push(`\`${type.toUpperCase()}\``);
      if (significance) badges.push(`\`${significance.toUpperCase()}\``);
      if (incident.plausibility) badges.push(`\`Plausibility: ${incident.plausibility}\``);
      if (incident.source_quality) badges.push(`\`Source: ${incident.source_quality}\``);
      if (badges.length) {
        md += badges.join(' ') + '\n\n';
      }

      // Timeline info
      if (incident.first_seen || incident.last_seen) {
        const timeline: string[] = [];
        if (incident.first_seen) timeline.push(`First seen: ${incident.first_seen}`);
        if (incident.last_seen) timeline.push(`Last seen: ${incident.last_seen}`);
        md += `📅 *${timeline.join(' | ')}*\n\n`;
      }

      // Description
      if (description) {
        md += `### Description\n\n${description}\n\n`;
      }

      // Strategic Relevance
      if (incident.organizational_relevance) {
        md += `### 🎯 Strategic Relevance\n\n${incident.organizational_relevance}\n\n`;
      }

      // Credibility Assessment
      if (incident.credibility_summary) {
        md += `### ✅ Credibility Assessment\n\n${incident.credibility_summary}\n\n`;
      }

      // Entities
      if (incident.entities?.length) {
        md += `### 🏷️ Key Entities\n\n`;
        incident.entities.forEach((entity: string) => {
          md += `- ${entity}\n`;
        });
        md += '\n';
      }

      // Investigation Leads
      if (incident.investigation_leads?.length) {
        md += `### 🔍 Investigation Leads\n\n`;
        incident.investigation_leads.forEach((lead: string) => {
          md += `- ${lead}\n`;
        });
        md += '\n';
      }

      // Source Articles
      if (incident.articles?.length || incident.article_metadata?.length) {
        const articles = incident.article_metadata || incident.articles || [];
        md += `### 📰 Source Articles (${articles.length})\n\n`;
        articles.slice(0, 5).forEach((article: any, j: number) => {
          const title = article.title || 'Untitled';
          const source = article.news_source || article.source || '';
          const url = article.uri || article.url || '';
          if (url) {
            md += `${j + 1}. [${title}](${url})${source ? ` - *${source}*` : ''}\n`;
          } else {
            md += `${j + 1}. ${title}${source ? ` - *${source}*` : ''}\n`;
          }
        });
        if (articles.length > 5) {
          md += `\n*...and ${articles.length - 5} more sources*\n`;
        }
        md += '\n';
      }

      // Analyst Notes
      if (incident.analyst_notes?.length) {
        md += `### 📝 Analyst Notes (${incident.analyst_notes.length})\n\n`;
        incident.analyst_notes.forEach((note: any) => {
          let formattedDate = note.timestamp;
          try {
            const ts = new Date(note.timestamp);
            formattedDate = ts.toLocaleString('en-GB', {
              day: '2-digit', month: 'short', year: 'numeric',
              hour: '2-digit', minute: '2-digit'
            });
          } catch {}
          md += `> **${note.analyst}** · ${formattedDate}\n>\n`;
          md += `> ${note.comment.replace(/\n/g, '\n> ')}\n\n`;
        });
      }

      md += `---\n\n`;
    });

    md += `\n*Report generated by AuNoo AI*\n`;

    // Download
    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `incidents-report-${dateStr}.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  /**
   * Export Incidents as PDF (opens styled HTML for print/save)
   */
  static exportIncidentsPDF(incidents: any[], topic?: string, model?: string): void {
    const dateStr = new Date().toISOString().split('T')[0];
    const modelInfo = model || 'AI';

    // Build HTML similar to email template styling
    let html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Incident Report${topic ? ` - ${topic}` : ''}</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      max-width: 800px;
      margin: 0 auto;
      padding: 40px 20px;
      background: #f8f9fa;
      color: #333;
      line-height: 1.6;
    }
    @media print {
      body { background: white; padding: 20px; }
      .no-print { display: none; }
      .incident-card { break-inside: avoid; }
    }
    .header {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      padding: 30px;
      border-radius: 12px 12px 0 0;
      color: white;
      margin-bottom: 0;
    }
    .header h1 { font-size: 28px; margin-bottom: 8px; }
    .header p { opacity: 0.9; font-size: 14px; }
    .content {
      background: white;
      padding: 30px;
      border: 1px solid #e9ecef;
      border-top: none;
      border-radius: 0 0 12px 12px;
    }
    .ai-disclosure {
      background: #e3f2fd;
      padding: 15px 20px;
      border-radius: 8px;
      margin-bottom: 30px;
      border-left: 4px solid #2196f3;
      font-size: 13px;
      color: #1565c0;
    }
    .incident-card {
      background: #fafafa;
      border: 1px solid #e9ecef;
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 20px;
    }
    .incident-card h2 {
      color: #333;
      font-size: 18px;
      margin-bottom: 12px;
      padding-bottom: 8px;
      border-bottom: 2px solid #667eea;
    }
    .badge {
      display: inline-block;
      padding: 4px 10px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 600;
      margin-right: 6px;
      margin-bottom: 8px;
      text-transform: uppercase;
    }
    .badge-incident { background: #dc3545; color: white; }
    .badge-event { background: #0d6efd; color: white; }
    .badge-expertise { background: #6f42c1; color: white; }
    .badge-trend { background: #198754; color: white; }
    .badge-high { background: #dc3545; color: white; }
    .badge-medium { background: #ffc107; color: #000; }
    .badge-low { background: #28a745; color: white; }
    .badge-info { background: #17a2b8; color: white; }
    .badge-secondary { background: #6c757d; color: white; }
    .section { margin: 15px 0; }
    .section-title {
      font-size: 13px;
      font-weight: 600;
      color: #666;
      margin-bottom: 8px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .section-content { font-size: 14px; color: #444; }
    .relevance-box {
      background: #e8f5e9;
      padding: 12px 15px;
      border-radius: 6px;
      border-left: 3px solid #4caf50;
    }
    .credibility-box {
      background: #fff3e0;
      padding: 12px 15px;
      border-radius: 6px;
      border-left: 3px solid #ff9800;
    }
    .entities { display: flex; flex-wrap: wrap; gap: 6px; }
    .entity-tag {
      background: #e8eaf6;
      color: #3f51b5;
      padding: 4px 10px;
      border-radius: 4px;
      font-size: 12px;
    }
    .leads-list, .articles-list { padding-left: 20px; }
    .leads-list li, .articles-list li { margin: 6px 0; font-size: 13px; }
    .articles-list a { color: #1976d2; text-decoration: none; }
    .articles-list a:hover { text-decoration: underline; }
    .source-info { color: #666; font-size: 12px; }
    .analyst-note {
      background: #fffbeb;
      padding: 12px 15px;
      border-radius: 6px;
      border-left: 3px solid #f59e0b;
      margin: 10px 0;
    }
    .analyst-note-header {
      font-size: 12px;
      color: #92400e;
      margin-bottom: 6px;
    }
    .analyst-note-header strong { color: #78350f; }
    .analyst-note-content {
      font-size: 13px;
      color: #333;
      white-space: pre-wrap;
    }
    .timeline-info {
      font-size: 12px;
      color: #666;
      margin-bottom: 12px;
    }
    .footer {
      text-align: center;
      padding: 20px;
      font-size: 12px;
      color: #666;
      margin-top: 20px;
    }
    .print-btn {
      position: fixed;
      top: 20px;
      right: 20px;
      background: #667eea;
      color: white;
      border: none;
      padding: 12px 24px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 14px;
      font-weight: 500;
      box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }
    .print-btn:hover { background: #5a67d8; }
  </style>
</head>
<body>
  <button class="print-btn no-print" onclick="window.print()">🖨️ Print / Save as PDF</button>

  <div class="header">
    <h1>🎯 Incident Report</h1>
    <p>${topic ? `Topic: ${topic} · ` : ''}${incidents.length} incident${incidents.length !== 1 ? 's' : ''} · Generated: ${new Date().toLocaleString()}</p>
  </div>

  <div class="content">
    <div class="ai-disclosure">
      <strong>ℹ️ AI Technology Disclosure:</strong> This report was generated using ${modelInfo}. All content has been reviewed for accuracy.
    </div>
`;

    incidents.forEach((incident, i) => {
      const name = incident.name || incident.title || 'Unnamed Incident';
      const description = incident.description || incident.summary || '';
      const type = (incident.type || 'event').toLowerCase();
      const significance = (incident.significance || 'medium').toLowerCase();

      html += `
    <div class="incident-card">
      <h2>${i + 1}. ${this.escapeHtml(name)}</h2>

      <div style="margin-bottom: 12px;">
        <span class="badge badge-${type}">${type}</span>
        <span class="badge badge-${significance}">${significance}</span>
        ${incident.plausibility ? `<span class="badge badge-info">Plausibility: ${incident.plausibility}</span>` : ''}
        ${incident.source_quality ? `<span class="badge badge-secondary">Source: ${incident.source_quality}</span>` : ''}
      </div>
`;

      // Timeline
      if (incident.first_seen || incident.last_seen) {
        const timeline: string[] = [];
        if (incident.first_seen) timeline.push(`First seen: ${incident.first_seen}`);
        if (incident.last_seen) timeline.push(`Last seen: ${incident.last_seen}`);
        html += `      <div class="timeline-info">📅 ${timeline.join(' | ')}</div>\n`;
      }

      // Description
      if (description) {
        html += `
      <div class="section">
        <div class="section-content">${this.escapeHtml(description)}</div>
      </div>
`;
      }

      // Strategic Relevance
      if (incident.organizational_relevance) {
        html += `
      <div class="section">
        <div class="section-title">🎯 Strategic Relevance</div>
        <div class="relevance-box">${this.escapeHtml(incident.organizational_relevance)}</div>
      </div>
`;
      }

      // Credibility
      if (incident.credibility_summary) {
        html += `
      <div class="section">
        <div class="section-title">✅ Credibility Assessment</div>
        <div class="credibility-box">${this.escapeHtml(incident.credibility_summary)}</div>
      </div>
`;
      }

      // Entities
      if (incident.entities?.length) {
        html += `
      <div class="section">
        <div class="section-title">🏷️ Key Entities</div>
        <div class="entities">
          ${incident.entities.map((e: string) => `<span class="entity-tag">${this.escapeHtml(e)}</span>`).join('')}
        </div>
      </div>
`;
      }

      // Investigation Leads
      if (incident.investigation_leads?.length) {
        html += `
      <div class="section">
        <div class="section-title">🔍 Investigation Leads</div>
        <ul class="leads-list">
          ${incident.investigation_leads.map((lead: string) => `<li>${this.escapeHtml(lead)}</li>`).join('')}
        </ul>
      </div>
`;
      }

      // Source Articles
      const articles = incident.article_metadata || incident.articles || [];
      if (articles.length > 0) {
        html += `
      <div class="section">
        <div class="section-title">📰 Source Articles (${articles.length})</div>
        <ol class="articles-list">
          ${articles.slice(0, 5).map((article: any) => {
            const title = article.title || 'Untitled';
            const source = article.news_source || article.source || '';
            const url = article.uri || article.url || '';
            if (url) {
              return `<li><a href="${this.escapeHtml(url)}" target="_blank">${this.escapeHtml(title)}</a>${source ? ` <span class="source-info">- ${this.escapeHtml(source)}</span>` : ''}</li>`;
            }
            return `<li>${this.escapeHtml(title)}${source ? ` <span class="source-info">- ${this.escapeHtml(source)}</span>` : ''}</li>`;
          }).join('')}
          ${articles.length > 5 ? `<li class="source-info">...and ${articles.length - 5} more sources</li>` : ''}
        </ol>
      </div>
`;
      }

      // Analyst Notes
      if (incident.analyst_notes?.length) {
        html += `
      <div class="section">
        <div class="section-title">📝 Analyst Notes (${incident.analyst_notes.length})</div>
`;
        incident.analyst_notes.forEach((note: any) => {
          let formattedDate = note.timestamp;
          try {
            const ts = new Date(note.timestamp);
            formattedDate = ts.toLocaleString('en-GB', {
              day: '2-digit', month: 'short', year: 'numeric',
              hour: '2-digit', minute: '2-digit'
            });
          } catch {}
          html += `
        <div class="analyst-note">
          <div class="analyst-note-header"><strong>${this.escapeHtml(note.analyst)}</strong> · ${formattedDate}</div>
          <div class="analyst-note-content">${this.escapeHtml(note.comment)}</div>
        </div>
`;
        });
        html += `      </div>\n`;
      }

      html += `    </div>\n`;
    });

    html += `
    <div class="footer">
      <p>Generated by <strong>AuNoo AI</strong> · ${dateStr}</p>
    </div>
  </div>
</body>
</html>`;

    // Open in new window for printing
    const printWindow = window.open('', '_blank');
    if (printWindow) {
      printWindow.document.write(html);
      printWindow.document.close();
    }
  }

  /**
   * Helper to escape HTML special characters
   */
  private static escapeHtml(str: string): string {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  /**
   * Export a single incident as PNG image
   */
  static async exportSingleIncidentPNG(incident: any): Promise<void> {
    const name = incident.name || incident.title || 'Unnamed Incident';
    const description = incident.description || incident.summary || '';
    const type = (incident.type || 'event').toLowerCase();
    const significance = (incident.significance || 'medium').toLowerCase();
    const topic = incident.topic || '';
    const sourceQuality = incident.source_quality || '';
    const plausibility = incident.plausibility || '';

    // Get articles
    const articleMetadata = incident.article_metadata || [];
    const articleUris = incident.article_uris || [];
    const articles = articleMetadata.length > 0 ? articleMetadata :
      articleUris.map((uri: string, i: number) => ({ uri, title: incident.articles?.[i]?.title || uri }));

    // Get signal tags
    const signalTags: string[] = [];
    if (incident.is_black_swan) signalTags.push('Black Swan');
    if (incident.is_wildcard) signalTags.push('Wildcard');
    if (incident.first_mover_advantage) signalTags.push('First Mover');
    if (incident.competitive_threat) signalTags.push('Competitive Threat');
    if (incident.regulatory_risk) signalTags.push('Regulatory Risk');
    if (incident.market_disruption) signalTags.push('Market Disruption');
    if (incident.emerging_trend) signalTags.push('Emerging Trend');

    // Create a temporary container for the card
    const container = document.createElement('div');
    container.style.cssText = 'position: absolute; left: -9999px; top: 0; width: 700px; padding: 20px; background: white;';

    container.innerHTML = `
      <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; color: white;">
          ${topic ? `<div style="font-size: 11px; opacity: 0.8; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px;">Topic: ${this.escapeHtml(topic)}</div>` : ''}
          <h2 style="margin: 0 0 10px 0; font-size: 20px;">${this.escapeHtml(name)}</h2>
          <div style="display: flex; gap: 8px; flex-wrap: wrap;">
            <span style="background: rgba(255,255,255,0.2); padding: 4px 10px; border-radius: 4px; font-size: 12px; text-transform: uppercase;">${type}</span>
            <span style="background: ${significance === 'high' ? '#dc3545' : significance === 'medium' ? '#ffc107' : '#28a745'}; color: ${significance === 'medium' ? '#000' : '#fff'}; padding: 4px 10px; border-radius: 4px; font-size: 12px; text-transform: uppercase;">${significance} significance</span>
            ${plausibility ? `<span style="background: #17a2b8; padding: 4px 10px; border-radius: 4px; font-size: 12px;">Plausibility: ${plausibility}</span>` : ''}
            ${sourceQuality ? `<span style="background: #6c757d; padding: 4px 10px; border-radius: 4px; font-size: 12px;">Source: ${sourceQuality}</span>` : ''}
          </div>
          ${signalTags.length ? `
            <div style="display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px;">
              ${signalTags.map(tag => `<span style="background: #f59e0b; color: #000; padding: 3px 8px; border-radius: 4px; font-size: 10px; font-weight: 600;">⚡ ${tag}</span>`).join('')}
            </div>
          ` : ''}
        </div>
        <div style="padding: 20px;">
          ${description ? `<p style="margin: 0 0 15px 0; color: #333; line-height: 1.6;">${this.escapeHtml(description)}</p>` : ''}
          ${incident.organizational_relevance ? `
            <div style="background: #e8f5e9; padding: 12px; border-radius: 6px; border-left: 3px solid #4caf50; margin-bottom: 12px;">
              <div style="font-size: 11px; font-weight: 600; color: #2e7d32; margin-bottom: 4px; text-transform: uppercase;">Strategic Relevance</div>
              <div style="font-size: 13px; color: #333;">${this.escapeHtml(incident.organizational_relevance)}</div>
            </div>
          ` : ''}
          ${incident.entities?.length ? `
            <div style="margin-bottom: 12px;">
              <div style="font-size: 11px; font-weight: 600; color: #666; margin-bottom: 6px; text-transform: uppercase;">Key Entities (${incident.entities.length})</div>
              <div style="display: flex; flex-wrap: wrap; gap: 6px;">
                ${incident.entities.map((e: string) => `<span style="background: #e8eaf6; color: #3f51b5; padding: 4px 10px; border-radius: 4px; font-size: 12px;">${this.escapeHtml(e)}</span>`).join('')}
              </div>
            </div>
          ` : ''}
          ${articles.length ? `
            <div style="margin-bottom: 12px;">
              <div style="font-size: 11px; font-weight: 600; color: #666; margin-bottom: 6px; text-transform: uppercase;">Sources (${articles.length})</div>
              <div style="font-size: 12px; color: #555;">
                ${articles.slice(0, 10).map((a: any, i: number) => `
                  <div style="margin-bottom: 4px; padding-left: 12px; border-left: 2px solid #ddd;">${i + 1}. ${this.escapeHtml(a.title || a.uri || 'Source')}</div>
                `).join('')}
                ${articles.length > 10 ? `<div style="color: #888; font-style: italic;">...and ${articles.length - 10} more sources</div>` : ''}
              </div>
            </div>
          ` : ''}
          ${incident.analyst_notes?.length ? `
            <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #eee;">
              <div style="font-size: 11px; font-weight: 600; color: #d97706; margin-bottom: 8px; text-transform: uppercase;">📝 Analyst Notes (${incident.analyst_notes.length})</div>
              ${incident.analyst_notes.map((note: any) => {
                let formattedDate = '';
                try {
                  const ts = new Date(note.timestamp);
                  formattedDate = ts.toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
                } catch {}
                return `
                  <div style="background: #fffbeb; padding: 10px; border-radius: 6px; border-left: 3px solid #f59e0b; margin-bottom: 8px;">
                    <div style="font-size: 11px; color: #92400e; margin-bottom: 4px;"><strong>${this.escapeHtml(note.analyst)}</strong>${formattedDate ? ` · ${formattedDate}` : ''}</div>
                    <div style="font-size: 12px; color: #333; white-space: pre-wrap;">${this.escapeHtml(note.comment)}</div>
                  </div>
                `;
              }).join('')}
            </div>
          ` : ''}
        </div>
        <div style="background: #f8f9fa; padding: 12px 20px; font-size: 11px; color: #666; text-align: right;">
          Generated by AuNoo AI · ${new Date().toLocaleDateString()}
        </div>
      </div>
    `;

    document.body.appendChild(container);

    try {
      const canvas = await html2canvas(container.firstElementChild as HTMLElement, {
        scale: 2,
        backgroundColor: '#ffffff',
        logging: false,
      });

      // Download as PNG
      const link = document.createElement('a');
      link.download = `incident-${name.toLowerCase().replace(/[^a-z0-9]+/g, '-').substring(0, 50)}.png`;
      link.href = canvas.toDataURL('image/png');
      link.click();
    } finally {
      document.body.removeChild(container);
    }
  }

  /**
   * Export a single incident as styled PDF
   */
  static exportSingleIncidentPDF(incident: any): void {
    // Use the same function as bulk but with single incident
    this.exportIncidentsPDF([incident], incident.topic);
  }

  /**
   * Export a single incident as styled Markdown
   */
  static exportSingleIncidentMarkdown(incident: any): void {
    // Use the same function as bulk but with single incident
    this.exportIncidentsStyledMarkdown([incident], incident.topic);
  }

  /**
   * Export Narratives/Themes as Markdown
   */
  static exportNarrativesMarkdown(themes: any[], topic?: string, model?: string): void {
    let md = `# Narrative Themes${topic ? ` - ${topic}` : ''}\n\n`;
    md += `*Generated: ${new Date().toLocaleString()}*\n\n`;

    // AI Disclosure
    md += `## AI Technology Disclosure\n\n`;
    const modelInfo = model || 'AI';
    md += `This report was generated using **${modelInfo}**. All content has been reviewed for accuracy.\n\n`;

    md += `## Themes (${themes.length})\n\n`;

    themes.forEach((theme, i) => {
      const name = theme.theme_name || theme.name || 'Unnamed Theme';
      const description = theme.theme_summary || theme.description || '';

      md += `### ${i + 1}. ${name}\n\n`;

      // Metadata
      const meta: string[] = [];
      if (theme.article_count) meta.push(`${theme.article_count} articles`);
      if (theme.source_count) meta.push(`${theme.source_count} sources`);
      if (theme.sentiment) meta.push(`Sentiment: ${theme.sentiment}`);
      if (theme.confidence) meta.push(`Confidence: ${Math.round(theme.confidence * 100)}%`);
      if (meta.length) {
        md += `*${meta.join(' | ')}*\n\n`;
      }

      if (description) {
        md += `${description}\n\n`;
      }

      // Key entities
      if (theme.key_entities?.length) {
        md += `**Key Entities:** ${theme.key_entities.join(', ')}\n\n`;
      }

      // Research suggestions
      if (theme.research_suggestions?.length) {
        md += `**Research Suggestions:**\n`;
        theme.research_suggestions.forEach((suggestion: string) => {
          md += `- ${suggestion}\n`;
        });
        md += '\n';
      }

      // Articles
      if (theme.articles?.length) {
        md += `**Articles:**\n`;
        theme.articles.slice(0, 5).forEach((article: any) => {
          const title = article.title || 'Untitled';
          const source = article.news_source || '';
          const url = article.uri || article.url || '';
          if (url) {
            md += `- [${title}](${url})${source ? ` (${source})` : ''}\n`;
          } else {
            md += `- ${title}${source ? ` (${source})` : ''}\n`;
          }
        });
        if (theme.articles.length > 5) {
          md += `- ... and ${theme.articles.length - 5} more\n`;
        }
        md += '\n';
      }

      md += `---\n\n`;
    });

    // Download
    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    const dateStr = new Date().toISOString().split('T')[0];
    link.download = `narratives-${dateStr}.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  /**
   * Export Narratives/Themes as CSV
   */
  /**
   * Generate email body for Your Briefing (for mailto: link)
   */
  static generateBriefingEmailBody(briefing: any, persona: string): string {
    let body = `EXECUTIVE BRIEFING - ${persona.toUpperCase()}\n`;
    body += `Generated: ${new Date(briefing.generated_at).toLocaleString()}\n\n`;

    if (briefing.executive_summary) {
      body += `EXECUTIVE SUMMARY\n${briefing.executive_summary}\n\n`;
    }

    if (briefing.key_themes?.length) {
      body += `KEY THEMES\n`;
      briefing.key_themes.forEach((theme: string) => {
        body += `- ${theme}\n`;
      });
      body += '\n';
    }

    body += `TOP STORIES\n\n`;
    const articles = briefing.articles || [];
    articles.slice(0, 6).forEach((article: any, i: number) => {
      const title = article.title || article.headline || 'Untitled';
      body += `${i + 1}. ${title}\n`;

      if (article.executive_takeaway) {
        body += `   Why It Matters: ${article.executive_takeaway}\n`;
      }

      if (article.strategic_relevance) {
        body += `   Strategic Relevance: ${article.strategic_relevance}\n`;
      }

      const url = article.url || article.uri || article.primary_article?.url || '';
      if (url) {
        body += `   Link: ${url}\n`;
      }
      body += '\n';
    });

    body += `---\nGenerated by Aunoo AI\n`;

    // Truncate if too long for email (max ~2000 chars for mailto body)
    if (body.length > 1800) {
      body = body.substring(0, 1800) + '...\n\n[Content truncated - download full report for complete briefing]';
    }

    return body;
  }

  /**
   * Generate email body for Incidents (for mailto: link)
   */
  static generateIncidentsEmailBody(incidents: any[]): string {
    let body = `INCIDENTS REPORT\n`;
    body += `Generated: ${new Date().toLocaleString()}\n`;
    body += `Total Incidents: ${incidents.length}\n\n`;

    incidents.slice(0, 5).forEach((incident, i) => {
      const name = incident.name || incident.title || 'Unnamed Incident';
      body += `${i + 1}. ${name}\n`;

      const badges: string[] = [];
      if (incident.type) badges.push(`Type: ${incident.type}`);
      if (incident.significance) badges.push(`Significance: ${incident.significance}`);
      if (badges.length) {
        body += `   ${badges.join(' | ')}\n`;
      }

      const description = incident.description || incident.summary || '';
      if (description) {
        const truncatedDesc = description.length > 150 ? description.substring(0, 150) + '...' : description;
        body += `   ${truncatedDesc}\n`;
      }

      if (incident.organizational_relevance) {
        const truncatedRel = incident.organizational_relevance.length > 100
          ? incident.organizational_relevance.substring(0, 100) + '...'
          : incident.organizational_relevance;
        body += `   Relevance: ${truncatedRel}\n`;
      }

      body += '\n';
    });

    if (incidents.length > 5) {
      body += `... and ${incidents.length - 5} more incidents\n\n`;
    }

    body += `---\nGenerated by Aunoo AI\n`;

    // Truncate if too long
    if (body.length > 1800) {
      body = body.substring(0, 1800) + '...\n\n[Content truncated - download full report]';
    }

    return body;
  }

  /**
   * Generate email body for Narratives (for mailto: link)
   */
  static generateNarrativesEmailBody(themes: any[]): string {
    let body = `NARRATIVE THEMES REPORT\n`;
    body += `Generated: ${new Date().toLocaleString()}\n`;
    body += `Total Themes: ${themes.length}\n\n`;

    themes.slice(0, 5).forEach((theme, i) => {
      const name = theme.theme_name || theme.name || 'Unnamed Theme';
      body += `${i + 1}. ${name}\n`;

      const meta: string[] = [];
      if (theme.article_count) meta.push(`${theme.article_count} articles`);
      if (theme.sentiment) meta.push(`Sentiment: ${theme.sentiment}`);
      if (meta.length) {
        body += `   ${meta.join(' | ')}\n`;
      }

      const description = theme.theme_summary || theme.description || '';
      if (description) {
        const truncatedDesc = description.length > 200 ? description.substring(0, 200) + '...' : description;
        body += `   ${truncatedDesc}\n`;
      }

      if (theme.key_entities?.length) {
        body += `   Key Entities: ${theme.key_entities.slice(0, 5).join(', ')}\n`;
      }

      body += '\n';
    });

    if (themes.length > 5) {
      body += `... and ${themes.length - 5} more themes\n\n`;
    }

    body += `---\nGenerated by Aunoo AI\n`;

    // Truncate if too long
    if (body.length > 1800) {
      body = body.substring(0, 1800) + '...\n\n[Content truncated - download full report]';
    }

    return body;
  }

  static exportNarrativesCSV(themes: any[]): void {
    const headers = [
      'Theme Name',
      'Summary',
      'Article Count',
      'Source Count',
      'Sentiment',
      'Confidence',
      'Key Entities',
      'Research Suggestions',
      'Primary Article URL',
      'All Article URLs'
    ];

    const rows = themes.map((theme: any) => {
      const escapeCSV = (str: string) => {
        if (!str) return '';
        const escaped = String(str).replace(/"/g, '""');
        return `"${escaped}"`;
      };

      // Get article URLs
      const articleUrls = theme.articles?.map((a: any) => a.uri || a.url).filter(Boolean) || [];
      const primaryUrl = articleUrls[0] || '';

      return [
        escapeCSV(theme.theme_name || theme.name || ''),
        escapeCSV(theme.theme_summary || theme.description || ''),
        escapeCSV(String(theme.article_count || theme.articles?.length || 0)),
        escapeCSV(String(theme.source_count || '')),
        escapeCSV(theme.sentiment || ''),
        escapeCSV(theme.confidence ? `${Math.round(theme.confidence * 100)}%` : ''),
        escapeCSV(theme.key_entities?.join('; ') || ''),
        escapeCSV(theme.research_suggestions?.join('; ') || ''),
        escapeCSV(primaryUrl),
        escapeCSV(articleUrls.join('; '))
      ].join(',');
    });

    const csv = [headers.join(','), ...rows].join('\n');

    // Download
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    const dateStr = new Date().toISOString().split('T')[0];
    link.download = `narratives-${dateStr}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  /**
   * Export Emerging Topics as Markdown
   */
  static exportEmergingTopicsMarkdown(topics: any[], topicFilter?: string): void {
    let md = `# Emerging Topics Report${topicFilter ? ` - ${topicFilter}` : ''}\n\n`;
    md += `*Generated: ${new Date().toLocaleString()}*\n\n`;

    // AI Disclosure
    md += `## AI Technology Disclosure\n\n`;
    md += `This report was generated using AI technologies for emerging topic detection and analysis. All content has been reviewed for accuracy.\n\n`;
    md += `---\n\n`;

    // Summary stats
    md += `## Summary\n\n`;
    md += `- **Total Themes Detected:** ${topics.length}\n`;
    md += `- **Accelerating Topics:** ${topics.filter(t => t.velocity === 'accelerating').length}\n`;
    md += `- **Total Articles Analyzed:** ${topics.reduce((sum, t) => sum + (t.article_count || 0), 0)}\n`;
    const avgScore = topics.length > 0
      ? Math.round(topics.reduce((sum, t) => sum + (t.trend_score?.composite || t.confidence_score * 100 || 0), 0) / topics.length)
      : 0;
    md += `- **Average Composite Score:** ${avgScore}\n\n`;

    md += `---\n\n`;

    md += `## Detected Themes (${topics.length})\n\n`;

    topics.forEach((topic, i) => {
      md += `### ${i + 1}. ${topic.topic_label}\n\n`;

      // Metadata badges
      const meta: string[] = [];
      if (topic.detection_type) meta.push(`Type: ${topic.detection_type}`);
      if (topic.velocity) meta.push(`Velocity: ${topic.velocity}`);
      if (topic.article_count) meta.push(`${topic.article_count} articles`);
      if (topic.source_count) meta.push(`${topic.source_count} sources`);
      if (topic.synthesis?.urgency) meta.push(`Urgency: ${topic.synthesis.urgency}`);
      if (meta.length) {
        md += `*${meta.join(' | ')}*\n\n`;
      }

      // Description
      if (topic.topic_description) {
        md += `${topic.topic_description}\n\n`;
      }

      // Trend tracking info
      if (topic.first_detection_date) {
        md += `**Detection History:**\n`;
        md += `- First Seen: ${topic.first_detection_date}\n`;
        if (topic.last_detection_date && topic.last_detection_date !== topic.first_detection_date) {
          md += `- Last Seen: ${topic.last_detection_date}\n`;
        }
        if (topic.detection_count > 1) {
          md += `- Times Detected: ${topic.detection_count}\n`;
        }
        if (topic.trajectory) {
          md += `- Trajectory: ${topic.trajectory}\n`;
        }
        md += '\n';
      }

      // Why Emerging
      if (topic.why_emerging) {
        md += `**Why Emerging:** ${topic.why_emerging}\n\n`;
      }

      // Key Takeaway
      if (topic.synthesis?.key_takeaway) {
        md += `**Key Takeaway:** ${topic.synthesis.key_takeaway}\n\n`;
      }

      // Trend Score
      if (topic.trend_score) {
        md += `#### Trend Score\n\n`;
        md += `| Volume | Velocity | Diversity | Novelty | Composite |\n`;
        md += `|--------|----------|-----------|---------|----------|\n`;
        md += `| ${Math.round(topic.trend_score.volume)} | ${Math.round(topic.trend_score.velocity)} | ${Math.round(topic.trend_score.diversity)} | ${Math.round(topic.trend_score.novelty)} | **${Math.round(topic.trend_score.composite)}** |\n\n`;
      }

      // Key Entities
      if (topic.key_entities?.length) {
        md += `**Key Entities:** ${topic.key_entities.join(', ')}\n\n`;
      }

      // Actors
      const hasActors = topic.actors?.companies?.length || topic.actors?.people?.length || topic.actors?.organizations?.length;
      if (hasActors) {
        md += `#### Key Actors\n\n`;
        if (topic.actors.companies?.length) {
          md += `- **Companies:** ${topic.actors.companies.join(', ')}\n`;
        }
        if (topic.actors.people?.length) {
          md += `- **People:** ${topic.actors.people.join(', ')}\n`;
        }
        if (topic.actors.organizations?.length) {
          md += `- **Organizations:** ${topic.actors.organizations.join(', ')}\n`;
        }
        md += '\n';
      }

      // Events
      if (topic.events?.trigger_event || topic.events?.timeline?.length) {
        md += `#### Events\n\n`;
        if (topic.events.trigger_event) {
          md += `**Trigger Event:** ${topic.events.trigger_event}\n\n`;
        }
        if (topic.events.timeline?.length) {
          md += `**Timeline:**\n`;
          topic.events.timeline.forEach((t: string) => md += `- ${t}\n`);
          md += '\n';
        }
        if (topic.events.current_status) {
          md += `**Current Status:** ${topic.events.current_status}\n\n`;
        }
      }

      // Signals
      const hasSignals = topic.signals?.growth_indicators?.length || topic.signals?.risk_factors?.length || topic.signals?.watch_for?.length;
      if (hasSignals) {
        md += `#### Signals\n\n`;
        if (topic.signals.growth_indicators?.length) {
          md += `**Growth Indicators:**\n`;
          topic.signals.growth_indicators.forEach((g: string) => md += `- ${g}\n`);
          md += '\n';
        }
        if (topic.signals.risk_factors?.length) {
          md += `**Risk Factors:**\n`;
          topic.signals.risk_factors.forEach((r: string) => md += `- ${r}\n`);
          md += '\n';
        }
        if (topic.signals.watch_for?.length) {
          md += `**Watch For:**\n`;
          topic.signals.watch_for.forEach((w: string) => md += `- ${w}\n`);
          md += '\n';
        }
      }

      // Implications
      if (topic.implications?.industry_impact || topic.implications?.regulatory || topic.implications?.market) {
        md += `#### Implications\n\n`;
        if (topic.implications.industry_impact) {
          md += `- **Industry:** ${topic.implications.industry_impact}\n`;
        }
        if (topic.implications.regulatory) {
          md += `- **Regulatory:** ${topic.implications.regulatory}\n`;
        }
        if (topic.implications.market) {
          md += `- **Market:** ${topic.implications.market}\n`;
        }
        md += '\n';
      }

      // Stakeholders
      if (topic.synthesis?.stakeholders_affected?.length) {
        md += `**Stakeholders Affected:** ${topic.synthesis.stakeholders_affected.join(', ')}\n\n`;
      }

      // Keywords
      if (topic.representative_keywords?.length) {
        md += `**Keywords:** ${topic.representative_keywords.join(', ')}\n\n`;
      }

      md += `---\n\n`;
    });

    // Download
    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    const dateStr = new Date().toISOString().split('T')[0];
    const filterStr = topicFilter ? `-${topicFilter.toLowerCase().replace(/\s+/g, '-')}` : '';
    link.download = `emerging-topics${filterStr}-${dateStr}.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  /**
   * Export Emerging Topics as CSV
   */
  static exportEmergingTopicsCSV(topics: any[]): void {
    const headers = [
      'Topic Label',
      'Description',
      'Detection Type',
      'Velocity',
      'Urgency',
      'Article Count',
      'Source Count',
      'Volume Score',
      'Velocity Score',
      'Diversity Score',
      'Novelty Score',
      'Composite Score',
      'Confidence Score',
      'First Detected',
      'Last Detected',
      'Detection Count',
      'Trajectory',
      'Why Emerging',
      'Key Takeaway',
      'Key Entities',
      'Companies',
      'People',
      'Organizations',
      'Trigger Event',
      'Current Status',
      'Growth Indicators',
      'Risk Factors',
      'Watch For',
      'Industry Impact',
      'Regulatory Impact',
      'Market Impact',
      'Stakeholders Affected',
      'Keywords'
    ];

    const rows = topics.map((topic: any) => {
      const escapeCSV = (str: string) => {
        if (!str) return '';
        const escaped = String(str).replace(/"/g, '""');
        return `"${escaped}"`;
      };

      return [
        escapeCSV(topic.topic_label || ''),
        escapeCSV(topic.topic_description || ''),
        escapeCSV(topic.detection_type || ''),
        escapeCSV(topic.velocity || ''),
        escapeCSV(topic.synthesis?.urgency || ''),
        escapeCSV(String(topic.article_count || 0)),
        escapeCSV(String(topic.source_count || '')),
        escapeCSV(String(topic.trend_score?.volume || '')),
        escapeCSV(String(topic.trend_score?.velocity || '')),
        escapeCSV(String(topic.trend_score?.diversity || '')),
        escapeCSV(String(topic.trend_score?.novelty || '')),
        escapeCSV(String(topic.trend_score?.composite || '')),
        escapeCSV(topic.confidence_score ? `${Math.round(topic.confidence_score * 100)}%` : ''),
        escapeCSV(topic.first_detection_date || ''),
        escapeCSV(topic.last_detection_date || ''),
        escapeCSV(String(topic.detection_count || 1)),
        escapeCSV(topic.trajectory || ''),
        escapeCSV(topic.why_emerging || ''),
        escapeCSV(topic.synthesis?.key_takeaway || ''),
        escapeCSV(topic.key_entities?.join('; ') || ''),
        escapeCSV(topic.actors?.companies?.join('; ') || ''),
        escapeCSV(topic.actors?.people?.join('; ') || ''),
        escapeCSV(topic.actors?.organizations?.join('; ') || ''),
        escapeCSV(topic.events?.trigger_event || ''),
        escapeCSV(topic.events?.current_status || ''),
        escapeCSV(topic.signals?.growth_indicators?.join('; ') || ''),
        escapeCSV(topic.signals?.risk_factors?.join('; ') || ''),
        escapeCSV(topic.signals?.watch_for?.join('; ') || ''),
        escapeCSV(topic.implications?.industry_impact || ''),
        escapeCSV(topic.implications?.regulatory || ''),
        escapeCSV(topic.implications?.market || ''),
        escapeCSV(topic.synthesis?.stakeholders_affected?.join('; ') || ''),
        escapeCSV(topic.representative_keywords?.join('; ') || '')
      ].join(',');
    });

    const csv = [headers.join(','), ...rows].join('\n');

    // Download
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    const dateStr = new Date().toISOString().split('T')[0];
    link.download = `emerging-topics-${dateStr}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  /**
   * Export Emerging Topics as text-based PDF
   */
  static exportEmergingTopicsPDF(topics: any[], topicFilter?: string): void {
    const pdf = new jsPDF({
      orientation: 'portrait',
      unit: 'mm',
      format: 'a4'
    });

    const pageWidth = 210;
    const pageHeight = 297;
    const margin = 15;
    const contentWidth = pageWidth - (margin * 2);
    let y = margin;

    const addPage = () => {
      pdf.addPage();
      y = margin;
    };

    const checkPageBreak = (neededHeight: number) => {
      if (y + neededHeight > pageHeight - margin) {
        addPage();
      }
    };

    const addText = (text: string, fontSize: number, isBold: boolean = false, color: number[] = [0, 0, 0]) => {
      pdf.setFontSize(fontSize);
      pdf.setFont('helvetica', isBold ? 'bold' : 'normal');
      pdf.setTextColor(color[0], color[1], color[2]);
      const lines = pdf.splitTextToSize(text, contentWidth);
      const lineHeight = fontSize * 0.4;
      checkPageBreak(lines.length * lineHeight + 2);
      pdf.text(lines, margin, y);
      y += lines.length * lineHeight + 2;
    };

    const addSection = (title: string, items: string[], iconColor: number[]) => {
      checkPageBreak(20);
      addText(title, 11, true, iconColor);
      items.forEach(item => {
        addText(`• ${item}`, 10, false);
      });
      y += 3;
    };

    // Title
    addText(`Emerging Topics Report`, 18, true, [128, 0, 128]);
    if (topicFilter) {
      addText(`Filter: ${topicFilter}`, 12, false, [100, 100, 100]);
    }
    addText(`Generated: ${new Date().toLocaleString()}`, 10, false, [150, 150, 150]);
    y += 5;

    // Summary stats
    const accelerating = topics.filter(t => t.velocity === 'accelerating').length;
    const totalArticles = topics.reduce((sum, t) => sum + (t.article_count || 0), 0);
    const avgScore = topics.length > 0
      ? Math.round(topics.reduce((sum, t) => sum + (t.trend_score?.composite || t.confidence_score * 100 || 0), 0) / topics.length)
      : 0;
    addText(`Summary: ${topics.length} themes detected, ${accelerating} accelerating, ${totalArticles} articles, avg score ${avgScore}`, 10, false, [100, 100, 100]);
    y += 5;

    // AI Disclosure
    checkPageBreak(25);
    addText('AI Technology Disclosure', 12, true);
    addText('This report was generated using AI technologies for emerging topic detection and analysis. All content has been reviewed for accuracy.', 9, false, [100, 100, 100]);
    y += 8;

    // Velocity colors
    const velocityColors: Record<string, number[]> = {
      accelerating: [0, 150, 50],
      stable: [100, 100, 100],
      decelerating: [200, 100, 0]
    };

    // Render each topic
    topics.forEach((topic, idx) => {
      checkPageBreak(50);

      // Topic header
      addText(`${idx + 1}. ${topic.topic_label}`, 13, true);

      // Metadata line
      const metaParts: string[] = [];
      if (topic.detection_type) metaParts.push(topic.detection_type);
      if (topic.velocity) metaParts.push(topic.velocity);
      if (topic.article_count) metaParts.push(`${topic.article_count} articles`);
      if (topic.synthesis?.urgency) metaParts.push(`${topic.synthesis.urgency} urgency`);
      if (metaParts.length) {
        addText(metaParts.join(' | '), 9, false, velocityColors[topic.velocity] || [100, 100, 100]);
      }
      y += 2;

      // Description
      if (topic.topic_description) {
        addText(topic.topic_description, 10, false);
        y += 2;
      }

      // Detection history
      if (topic.first_detection_date && topic.detection_count > 1) {
        addText(`Detected ${topic.detection_count}x since ${topic.first_detection_date}${topic.trajectory ? ` (${topic.trajectory})` : ''}`, 9, false, [100, 100, 100]);
        y += 2;
      }

      // Why Emerging
      if (topic.why_emerging) {
        checkPageBreak(15);
        addText('Why Emerging', 10, true, [200, 150, 0]);
        addText(topic.why_emerging, 10, false);
        y += 2;
      }

      // Key Takeaway
      if (topic.synthesis?.key_takeaway) {
        checkPageBreak(15);
        addText('Key Takeaway', 10, true, [128, 0, 128]);
        addText(topic.synthesis.key_takeaway, 10, false);
        y += 2;
      }

      // Trend Score
      if (topic.trend_score) {
        checkPageBreak(12);
        addText(`Trend Score: Volume ${Math.round(topic.trend_score.volume)} | Velocity ${Math.round(topic.trend_score.velocity)} | Diversity ${Math.round(topic.trend_score.diversity)} | Novelty ${Math.round(topic.trend_score.novelty)} | Composite ${Math.round(topic.trend_score.composite)}`, 9, false, [0, 100, 150]);
        y += 2;
      }

      // Key Entities
      if (topic.key_entities?.length > 0) {
        addText(`Key Entities: ${topic.key_entities.join(', ')}`, 9, false, [80, 80, 80]);
        y += 2;
      }

      // Actors
      const hasActors = topic.actors?.companies?.length || topic.actors?.people?.length || topic.actors?.organizations?.length;
      if (hasActors) {
        checkPageBreak(15);
        addText('Key Actors', 10, true, [0, 100, 200]);
        if (topic.actors.companies?.length) {
          addText(`Companies: ${topic.actors.companies.join(', ')}`, 9, false);
        }
        if (topic.actors.people?.length) {
          addText(`People: ${topic.actors.people.join(', ')}`, 9, false);
        }
        if (topic.actors.organizations?.length) {
          addText(`Organizations: ${topic.actors.organizations.join(', ')}`, 9, false);
        }
        y += 2;
      }

      // Events
      if (topic.events?.trigger_event) {
        checkPageBreak(15);
        addText('Trigger Event', 10, true, [200, 50, 50]);
        addText(topic.events.trigger_event, 10, false);
        y += 2;
      }

      // Signals
      if (topic.signals?.growth_indicators?.length > 0) {
        addSection('Growth Indicators', topic.signals.growth_indicators.slice(0, 3), [0, 150, 50]);
      }
      if (topic.signals?.risk_factors?.length > 0) {
        addSection('Risk Factors', topic.signals.risk_factors.slice(0, 3), [200, 100, 0]);
      }
      if (topic.signals?.watch_for?.length > 0) {
        addSection('Watch For', topic.signals.watch_for.slice(0, 3), [0, 100, 200]);
      }

      // Implications
      if (topic.implications?.industry_impact || topic.implications?.regulatory || topic.implications?.market) {
        checkPageBreak(20);
        addText('Implications', 10, true, [128, 0, 128]);
        if (topic.implications.industry_impact) {
          addText(`Industry: ${topic.implications.industry_impact}`, 9, false);
        }
        if (topic.implications.regulatory) {
          addText(`Regulatory: ${topic.implications.regulatory}`, 9, false);
        }
        if (topic.implications.market) {
          addText(`Market: ${topic.implications.market}`, 9, false);
        }
        y += 2;
      }

      y += 8; // Space between topics
    });

    // Footer on all pages
    const totalPages = pdf.getNumberOfPages();
    for (let i = 1; i <= totalPages; i++) {
      pdf.setPage(i);
      pdf.setFontSize(8);
      pdf.setTextColor(150, 150, 150);
      pdf.text(`Page ${i} of ${totalPages}`, pageWidth / 2, pageHeight - 10, { align: 'center' });
      pdf.text('Generated by Aunoo AI - Emerging Topics Report', pageWidth / 2, pageHeight - 5, { align: 'center' });
    }

    const dateStr = new Date().toISOString().split('T')[0];
    const filterStr = topicFilter ? `-${topicFilter.toLowerCase().replace(/\s+/g, '-')}` : '';
    pdf.save(`emerging-topics${filterStr}-${dateStr}.pdf`);
  }

  /**
   * Export Future Horizons with optional sections
   */
  static async exportFutureHorizons(
    options: {
      includeChart: boolean;
      includeExecutiveSummary: boolean;
      includeDetailedCards: boolean;
      format: 'pdf' | 'image' | 'html';
      runId?: string;
    },
    scenarios: any[],
    summaries: any[] | null,
    topic: string
  ): Promise<void> {
    // Interactive HTML path — fetch the server-rendered standalone doc.
    if (options.format === 'html') {
      if (!options.runId) {
        throw new Error('Interactive HTML download requires a horizons run id.');
      }
      const resp = await fetch(`/api/trend-convergence/horizons/${encodeURIComponent(options.runId)}/download.html`);
      if (!resp.ok) {
        const body = await resp.text();
        throw new Error(`${resp.status} ${body || resp.statusText}`);
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `future-horizons-${topic.toLowerCase().replace(/\s+/g, '-')}.html`;
      document.body.appendChild(a);
      a.click();
      setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 100);
      return;
    }
    // Create a temporary container for export content
    const exportContainer = document.createElement('div');
    exportContainer.id = 'horizons-export-temp';
    exportContainer.style.cssText = 'position: absolute; left: -9999px; width: 1200px; background: white; padding: 40px;';
    document.body.appendChild(exportContainer);

    try {
      // Add title
      const titleHtml = `
        <div style="text-align: center; margin-bottom: 30px;">
          <h1 style="font-size: 24px; font-weight: bold; color: #1f2937; margin: 0 0 10px 0;">Future Horizons Analysis</h1>
          <p style="font-size: 14px; color: #6b7280; margin: 0;">${topic}</p>
          <p style="font-size: 12px; color: #9ca3af; margin: 5px 0 0 0;">Generated: ${new Date().toLocaleString()}</p>
        </div>
      `;
      exportContainer.innerHTML = titleHtml;

      // Add chart section
      if (options.includeChart) {
        const chartElement = document.querySelector('#horizons-chart-container, .relative.bg-gradient-to-br');
        if (chartElement) {
          const chartClone = chartElement.cloneNode(true) as HTMLElement;
          chartClone.style.marginBottom = '40px';
          exportContainer.appendChild(chartClone);
        }
      }

      // Add executive summary section
      if (options.includeExecutiveSummary && summaries && summaries.length > 0) {
        const summaryHtml = this.generateExecutiveSummaryHTML(summaries);
        const summaryDiv = document.createElement('div');
        summaryDiv.innerHTML = summaryHtml;
        summaryDiv.style.marginBottom = '40px';
        exportContainer.appendChild(summaryDiv);
      }

      // Add detailed cards section
      if (options.includeDetailedCards && scenarios.length > 0) {
        const cardsHtml = this.generateScenariosHTML(scenarios);
        const cardsDiv = document.createElement('div');
        cardsDiv.innerHTML = cardsHtml;
        exportContainer.appendChild(cardsDiv);
      }

      // Add AI disclosure footer
      const footerHtml = `
        <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #e5e7eb; text-align: center;">
          <p style="font-size: 10px; color: #9ca3af; margin: 0;">
            AI Technology Disclosure: This analysis was generated using AI (site-configured large language models) for scenario planning and future horizons modeling.
          </p>
          <p style="font-size: 10px; color: #9ca3af; margin: 5px 0 0 0;">
            Generated by Aunoo AI
          </p>
        </div>
      `;
      const footerDiv = document.createElement('div');
      footerDiv.innerHTML = footerHtml;
      exportContainer.appendChild(footerDiv);

      // Generate the export
      const filename = `future-horizons-${topic.toLowerCase().replace(/\s+/g, '-')}-${Date.now()}`;

      if (options.format === 'pdf') {
        await this.exportPDF('horizons-export-temp', filename);
      } else {
        await this.exportImage('horizons-export-temp', filename);
      }
    } finally {
      // Clean up
      document.body.removeChild(exportContainer);
    }
  }

  /**
   * Generate HTML for executive summaries in export
   */
  private static generateExecutiveSummaryHTML(summaries: any[]): string {
    const horizonColors: Record<string, { bg: string; border: string; text: string }> = {
      h1: { bg: '#dbeafe', border: '#2563eb', text: '#1e40af' },
      h2: { bg: '#f3e8ff', border: '#9333ea', text: '#7e22ce' },
      h3: { bg: '#dcfce7', border: '#16a34a', text: '#166534' }
    };

    const horizonLabels: Record<string, string> = {
      h1: 'H1 | Declining System',
      h2: 'H2 | Transition/Innovation',
      h3: 'H3 | Future Vision'
    };

    let html = `
      <div style="margin-bottom: 30px;">
        <h2 style="font-size: 18px; font-weight: bold; color: #1f2937; margin: 0 0 20px 0; display: flex; align-items: center; gap: 10px;">
          <span>Executive Summary</span>
        </h2>
        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px;">
    `;

    summaries.forEach((summary) => {
      const colors = horizonColors[summary.primary_horizon] || horizonColors.h1;

      html += `
        <div style="border-left: 4px solid ${colors.border}; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-radius: 8px; padding: 16px;">
          <div style="display: flex; align-items: start; justify-content: space-between; gap: 12px; margin-bottom: 12px;">
            <h3 style="font-size: 14px; font-weight: bold; color: #1f2937; margin: 0; letter-spacing: 0.02em;">
              ${summary.topic_title}
            </h3>
            <span style="background: ${colors.border}; color: white; font-size: 10px; padding: 4px 8px; border-radius: 4px; white-space: nowrap;">
              ${horizonLabels[summary.primary_horizon] || 'Unknown'}
            </span>
          </div>

          <p style="font-size: 12px; color: #374151; margin: 0 0 12px 0; line-height: 1.6;">
            ${summary.opening_statement || summary.primary_signal}
          </p>

          ${summary.minority_view ? `
            <p style="font-size: 11px; color: #6b7280; margin: 0 0 12px 0; padding-left: 12px; border-left: 2px solid #e5e7eb; line-height: 1.5; font-style: italic;">
              <strong style="font-style: normal; color: #374151;">Minority view${summary.minority_view.percentage_range ? ` (${summary.minority_view.percentage_range})` : ''}:</strong> ${summary.minority_view.statement}
            </p>
          ` : ''}

          <div style="background: #f8fafc; padding: 12px; border-radius: 6px; margin-bottom: 12px; border: 1px solid #e2e8f0;">
            <p style="font-size: 11px; font-weight: 600; color: ${typeof summary.consensus_percentage === 'number' ? (summary.consensus_percentage >= 80 ? '#16a34a' : summary.consensus_percentage >= 60 ? '#d97706' : '#ea580c') : '#6b7280'}; margin: 0 0 4px 0; text-transform: uppercase; letter-spacing: 0.05em;">
              ${typeof summary.consensus_percentage === 'number' ? `PRIMARY SIGNAL (${summary.consensus_percentage}% CONSENSUS)` : 'PRIMARY SIGNAL'}
            </p>
            <p style="font-size: 12px; color: #374151; margin: 0; line-height: 1.5;">
              ${summary.primary_signal}
            </p>
          </div>

          <div style="border-top: 1px solid #e5e7eb; margin: 12px 0; padding-top: 12px;">
            <h4 style="font-size: 11px; font-weight: 600; color: #6b7280; margin: 0 0 8px 0; text-transform: uppercase; letter-spacing: 0.05em;">Decision Fork</h4>
            <div style="font-size: 11px; color: #374151;">
              <div style="border-left: 3px solid #22c55e; padding-left: 10px; margin-bottom: 8px;">
                <p style="margin: 0 0 2px 0; font-weight: 600;">${summary.decision_fork?.condition_a?.condition || summary.decision_fork?.branch_a?.label || 'If condition A'}</p>
                <p style="margin: 0; color: #6b7280;">${summary.decision_fork?.condition_a?.outcome || summary.decision_fork?.branch_a?.outcome || ''}</p>
              </div>
              <div style="border-left: 3px solid #f97316; padding-left: 10px;">
                <p style="margin: 0 0 2px 0; font-weight: 600;">${summary.decision_fork?.condition_b?.condition || summary.decision_fork?.branch_b?.label || 'If condition B'}</p>
                <p style="margin: 0; color: #6b7280;">${summary.decision_fork?.condition_b?.outcome || summary.decision_fork?.branch_b?.outcome || ''}</p>
              </div>
            </div>
          </div>

          <div style="margin-top: 12px;">
            <span style="background: #eff6ff; color: #1d4ed8; font-size: 10px; padding: 4px 8px; border-radius: 4px; border: 1px solid #bfdbfe;">
              Your Window
            </span>
            <span style="font-size: 11px; color: #374151; margin-left: 8px;">
              <strong>${summary.action_window?.assessment?.timeframe}</strong> to ${summary.action_window?.assessment?.action};
              <strong>${summary.action_window?.positioning?.timeframe}</strong> to ${summary.action_window?.positioning?.action}
            </span>
          </div>

          ${summary.source_scenarios && summary.source_scenarios.length > 0 ? `
          <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #e5e7eb;">
            <p style="font-size: 10px; color: #9ca3af; margin: 0 0 6px 0;">Based on ${summary.source_scenarios.length} underlying scenario${summary.source_scenarios.length !== 1 ? 's' : ''}:</p>
            <ul style="margin: 0; padding-left: 16px; font-size: 10px; color: #6b7280;">
              ${summary.source_scenarios.map((scenario: any) => {
                const title = typeof scenario === 'string' ? scenario : scenario.title;
                const horizon = typeof scenario === 'string' ? null : scenario.horizon;
                const horizonLabel = horizon ? (horizon === 'h1' ? 'H1' : horizon === 'h2' ? 'H2' : 'H3') : '';
                const horizonColor = horizon ? (horizon === 'h1' ? '#2563eb' : horizon === 'h2' ? '#9333ea' : '#16a34a') : '#6b7280';
                return `<li style="margin: 2px 0;">${horizon ? `<span style="color: ${horizonColor}; font-weight: 600;">[${horizonLabel}]</span> ` : ''}${title}</li>`;
              }).join('')}
            </ul>
          </div>
          ` : ''}
        </div>
      `;
    });

    html += `
        </div>
        <div style="display: flex; justify-content: center; gap: 20px; margin-top: 16px; padding-top: 16px; border-top: 1px solid #e5e7eb; font-size: 10px; color: #9ca3af;">
          <span style="display: flex; align-items: center; gap: 6px;"><span style="width: 12px; height: 12px; background: #2563eb; border-radius: 3px;"></span> H1 Declining System</span>
          <span style="display: flex; align-items: center; gap: 6px;"><span style="width: 12px; height: 12px; background: #9333ea; border-radius: 3px;"></span> H2 Transition/Innovation</span>
          <span style="display: flex; align-items: center; gap: 6px;"><span style="width: 12px; height: 12px; background: #16a34a; border-radius: 3px;"></span> H3 Future Vision</span>
        </div>
      </div>
    `;

    return html;
  }

  /**
   * Generate HTML for scenarios in export
   */
  private static generateScenariosHTML(scenarios: any[]): string {
    const horizonColors: Record<string, { bg: string; border: string; header: string }> = {
      h1: { bg: '#dbeafe', border: '#2563eb', header: '#2563eb' },
      h2: { bg: '#f3e8ff', border: '#9333ea', header: '#9333ea' },
      h3: { bg: '#dcfce7', border: '#16a34a', header: '#16a34a' }
    };

    const horizonLabels: Record<string, { label: string; subtitle: string }> = {
      h1: { label: 'Current', subtitle: 'Declining Systems' },
      h2: { label: 'Transition', subtitle: 'Innovation' },
      h3: { label: 'Future', subtitle: 'Emerging Vision' }
    };

    const h1Scenarios = scenarios.filter(s => s.type === 'h1');
    const h2Scenarios = scenarios.filter(s => s.type === 'h2');
    const h3Scenarios = scenarios.filter(s => s.type === 'h3');

    const renderColumn = (type: string, scenarioList: any[]) => {
      const config = horizonLabels[type] || { label: type, subtitle: '' };
      const colors = horizonColors[type] || horizonColors.h1;

      return `
        <div style="flex: 1;">
          <div style="background: ${colors.header}; color: white; padding: 12px; border-radius: 8px 8px 0 0; text-align: center;">
            <div style="font-weight: bold; font-size: 13px;">${config.label}</div>
            <div style="font-size: 11px; opacity: 0.9;">${config.subtitle}</div>
          </div>
          <div style="background: #f9fafb; padding: 12px; border-radius: 0 0 8px 8px; min-height: 200px;">
            ${scenarioList.length > 0 ? scenarioList.map(scenario => `
              <div style="background: white; border: 1px solid #e5e7eb; border-radius: 6px; padding: 12px; margin-bottom: 10px;">
                <h4 style="font-size: 12px; font-weight: 600; color: #1f2937; margin: 0 0 8px 0; line-height: 1.3;">${scenario.title}</h4>
                <p style="font-size: 11px; color: #4b5563; margin: 0 0 8px 0; line-height: 1.5;">${scenario.description?.substring(0, 200)}${(scenario.description?.length || 0) > 200 ? '...' : ''}</p>
                <div style="font-size: 10px; color: #6b7280;">${scenario.timeframe || ''}</div>
              </div>
            `).join('') : `
              <p style="font-size: 11px; color: #9ca3af; text-align: center; padding: 20px;">No ${config.label.toLowerCase()} scenarios</p>
            `}
          </div>
        </div>
      `;
    };

    return `
      <div>
        <h2 style="font-size: 18px; font-weight: bold; color: #1f2937; margin: 0 0 20px 0;">Three Horizons Scenarios</h2>
        <div style="display: flex; gap: 16px;">
          ${renderColumn('h1', h1Scenarios)}
          ${renderColumn('h2', h2Scenarios)}
          ${renderColumn('h3', h3Scenarios)}
        </div>
      </div>
    `;
  }

  // --- Brand Watcher shared helpers ---

  private static bwNormalizeSentiment(sentiments: Record<string, number>): { positive: number; neutral: number; negative: number } {
    const pos = ['positive', 'optimistic', 'positive development'];
    const neg = ['negative', 'pessimistic', 'concerning', 'concerned', 'critical', 'alarming'];
    let p = 0, ne = 0, nu = 0;
    for (const [k, v] of Object.entries(sentiments)) {
      const lo = k.toLowerCase();
      if (pos.some(x => lo.includes(x))) p += v;
      else if (neg.some(x => lo.includes(x))) ne += v;
      else nu += v;
    }
    return { positive: p, neutral: nu, negative: ne };
  }

  /**
   * Export Brand Watcher report as Markdown — comprehensive multi-section report
   */
  static exportBrandWatcherMarkdown(data: {
    brandName?: string; daysBack?: number; stats?: any; categories?: any[];
    riskAssessment?: any;
    sentimentTrends?: any[]; comparison?: any[]; shareOfVoice?: any[];
    alerts?: any[]; narrative?: any; articles?: any[];
    temporalData?: any[]; selectedBrand?: any;
  }): void {
    const brandLabel = data.brandName || 'All Brands';
    const dateStr = new Date().toISOString().split('T')[0];
    const period = data.daysBack === 0 ? 'All Time' : `Last ${data.daysBack || 30} days`;
    let md = `# Brand Intelligence Report — ${brandLabel}\n\n`;
    md += `*Generated: ${new Date().toLocaleString()}*\n`;
    md += `*Period: ${period}*\n\n`;

    // AI Disclosure
    md += `## AI Technology Disclosure\n\n`;
    md += `This report was generated using AI technologies for brand intelligence analysis, article classification, sentiment tracking, and narrative generation. All AI-generated content has been processed automatically and should be reviewed and validated.\n\n`;
    md += `---\n\n`;

    // ===== SECTION 1: EXECUTIVE OVERVIEW =====
    md += `# 1. Executive Overview\n\n`;

    // Key metrics
    if (data.stats) {
      md += `## Key Metrics\n\n`;
      md += `| Metric | Value |\n|--------|-------|\n`;
      md += `| Total Articles | ${data.stats.total_articles ?? 0} |\n`;
      md += `| Active Brands | ${data.stats.total_brands ?? 0} |\n`;
      md += `| Most Active Category | ${data.stats.most_active_category || 'N/A'} |\n`;
      md += `| Multi-Category Articles | ${data.stats.multi_category_count ?? 0} |\n`;
      if (data.stats.date_range_start) md += `| Date Range | ${data.stats.date_range_start} to ${data.stats.date_range_end} |\n`;
      md += `\n`;
    }

    // Aggregate sentiment
    if (data.sentimentTrends && data.sentimentTrends.length > 0) {
      const agg = { positive: 0, neutral: 0, negative: 0 };
      for (const t of data.sentimentTrends) {
        const s = this.bwNormalizeSentiment(t.sentiments || {});
        agg.positive += s.positive; agg.neutral += s.neutral; agg.negative += s.negative;
      }
      const sentTotal = agg.positive + agg.neutral + agg.negative;
      if (sentTotal > 0) {
        md += `## Overall Sentiment\n\n`;
        const pPct = ((agg.positive / sentTotal) * 100).toFixed(1);
        const nuPct = ((agg.neutral / sentTotal) * 100).toFixed(1);
        const nPct = ((agg.negative / sentTotal) * 100).toFixed(1);
        md += `| Sentiment | Count | Percentage |\n|-----------|-------|------------|\n`;
        md += `| Positive | ${agg.positive} | ${pPct}% |\n`;
        md += `| Neutral | ${agg.neutral} | ${nuPct}% |\n`;
        md += `| Negative | ${agg.negative} | ${nPct}% |\n`;
        md += `| **Total** | **${sentTotal}** | |\n\n`;

        if (parseFloat(nPct) >= 15) {
          md += `> **Risk Flag:** Negative sentiment is at ${nPct}% — above the 15% threshold.\n\n`;
        }
      }
    }

    // Risk assessment — Brand Risk v2: active issues, no 0-100 score
    if (data.riskAssessment) {
      const ra = data.riskAssessment;
      md += `## Brand Risk Assessment\n\n`;
      if (ra.escalation_tier) {
        md += `**Status: ${ra.escalation_tier.label}** — triggered by: ${ra.escalation_tier.triggered.join('; ')}\n\n`;
      }
      if (ra.active_issues?.length) {
        md += `| Severity | Type | Issue | Coverage | Momentum |\n|----------|------|-------|----------|----------|\n`;
        ra.active_issues.forEach((i: any) => {
          md += `| ${i.severity.toUpperCase()} | ${i.primary_type.replace(/_/g, ' ')} | ${i.title} | ${i.articles} articles, ${i.sources} sources, first seen ${i.first_seen} | ${i.momentum} |\n`;
        });
        md += `\n`;
      } else {
        md += `No active issues — no adverse events currently open for this brand.\n\n`;
      }
      if (ra.attention?.available && ra.attention.category_spikes?.length) {
        md += `Attention (coverage volume, not risk): ${ra.attention.category_spikes.map((s: any) => `${s.category} at ${s.multiple}x normal (${s.recent} vs ${s.weekly_avg}/wk)`).join('; ')}.\n\n`;
      }
    }

    // Spike alerts
    if (data.alerts && data.alerts.length > 0) {
      md += `## Spike Alerts\n\n`;
      const sorted = [...data.alerts].sort((a, b) => b.spike_ratio - a.spike_ratio);
      md += `| Severity | Category | Current | Average | Spike |\n|----------|----------|---------|---------|-------|\n`;
      sorted.forEach(a => {
        md += `| ${(a.severity || 'medium').toUpperCase()} | ${a.category} | ${a.current_count} | ${a.average_count?.toFixed(1)} | ${a.spike_ratio?.toFixed(1)}x |\n`;
      });
      md += `\n`;
    }

    // ===== SECTION 2: SENTIMENT ANALYSIS =====
    md += `---\n\n# 2. Sentiment Analysis\n\n`;

    if (data.sentimentTrends && data.sentimentTrends.length > 0) {
      // Weekly sentiment trend table
      md += `## Weekly Sentiment Trend\n\n`;
      md += `| Week | Positive | Neutral | Negative | Total | Neg% |\n|------|----------|---------|----------|-------|------|\n`;
      data.sentimentTrends.forEach(t => {
        const s = this.bwNormalizeSentiment(t.sentiments || {});
        const total = s.positive + s.neutral + s.negative;
        const negPct = total > 0 ? ((s.negative / total) * 100).toFixed(1) : '0.0';
        md += `| ${t.week} | ${s.positive} | ${s.neutral} | ${s.negative} | ${total} | ${negPct}% |\n`;
      });
      md += `\n`;

      // Sentiment by category
      const catSent: Record<string, { positive: number; neutral: number; negative: number }> = {};
      for (const t of data.sentimentTrends) {
        const cat = t.category || 'Overall';
        if (!catSent[cat]) catSent[cat] = { positive: 0, neutral: 0, negative: 0 };
        const s = this.bwNormalizeSentiment(t.sentiments || {});
        catSent[cat].positive += s.positive;
        catSent[cat].neutral += s.neutral;
        catSent[cat].negative += s.negative;
      }
      if (Object.keys(catSent).length > 1) {
        md += `## Sentiment by Category\n\n`;
        md += `| Category | Positive | Neutral | Negative | Total |\n|----------|----------|---------|----------|-------|\n`;
        for (const [cat, s] of Object.entries(catSent)) {
          const total = s.positive + s.neutral + s.negative;
          md += `| ${cat} | ${s.positive} | ${s.neutral} | ${s.negative} | ${total} |\n`;
        }
        md += `\n`;
      }
    }

    // ===== SECTION 3: CATEGORY DISTRIBUTION =====
    md += `---\n\n# 3. Category Distribution\n\n`;

    if (data.categories && data.categories.length > 0) {
      md += `## Category Breakdown\n\n`;
      md += `| Category | Articles | Share | Trend |\n|----------|----------|-------|-------|\n`;
      data.categories.forEach(c => {
        const trend = c.recent_trend === 'up' ? 'Rising' : c.recent_trend === 'down' ? 'Declining' : 'Stable';
        md += `| ${c.category} | ${c.article_count} | ${c.percentage?.toFixed(1)}% | ${trend} |\n`;
      });
      md += `\n`;
    }

    // Monthly volume over time
    if (data.temporalData && data.temporalData.length > 0) {
      md += `## Monthly Article Volume\n\n`;
      md += `| Month | Total |`;
      // Get top 5 categories
      const topCats = (data.categories || []).slice(0, 5).map(c => c.category);
      topCats.forEach(cat => { md += ` ${cat} |`; });
      md += `\n|-------|-------|`;
      topCats.forEach(() => { md += `-------|`; });
      md += `\n`;
      data.temporalData.slice(-12).forEach(d => {
        md += `| ${d.month} | ${d.total} |`;
        topCats.forEach(cat => { md += ` ${d.by_category?.[cat] || 0} |`; });
        md += `\n`;
      });
      md += `\n`;
    }

    // ===== SECTION 4: COMPETITIVE COMPARISON =====
    if ((data.comparison && data.comparison.length > 1) || (data.shareOfVoice && data.shareOfVoice.length > 1)) {
      md += `---\n\n# 4. Competitive Comparison\n\n`;

      // Share of Voice
      if (data.shareOfVoice && data.shareOfVoice.length > 1) {
        md += `## Share of Voice\n\n`;
        const sovTotal = data.shareOfVoice.reduce((s, b) => s + (b.mention_count || 0), 0);
        md += `| Brand | Mentions | Share |\n|-------|----------|-------|\n`;
        data.shareOfVoice.forEach(b => {
          const pct = sovTotal > 0 ? ((b.mention_count / sovTotal) * 100).toFixed(1) : b.percentage?.toFixed(1) || '0.0';
          md += `| ${b.brand_name} | ${b.mention_count} | ${pct}% |\n`;
        });
        md += `\n`;
      }

      // Cross-brand category breakdown
      if (data.comparison && data.comparison.length > 1) {
        // Sentiment by brand
        md += `## Sentiment by Brand\n\n`;
        md += `| Brand | Total | Positive | Neutral | Negative |\n|-------|-------|----------|---------|----------|\n`;
        data.comparison.forEach(comp => {
          const s = this.bwNormalizeSentiment(comp.sentiment_breakdown || {});
          const total = s.positive + s.neutral + s.negative;
          md += `| ${comp.brand_name} | ${comp.total_articles} | ${s.positive} | ${s.neutral} | ${s.negative} |\n`;
        });
        md += `\n`;

        // Category breakdown matrix
        const allCats = new Set<string>();
        data.comparison.forEach(comp => {
          Object.entries(comp.category_breakdown || {}).forEach(([k, v]) => { if (v > 0) allCats.add(k); });
        });
        const sortedCats = [...allCats].sort((a, b) => {
          const aT = data.comparison!.reduce((s, c) => s + (c.category_breakdown[a] || 0), 0);
          const bT = data.comparison!.reduce((s, c) => s + (c.category_breakdown[b] || 0), 0);
          return bT - aT;
        });

        if (sortedCats.length > 0) {
          md += `## Category Breakdown by Brand\n\n`;
          md += `| Brand | Total |`;
          sortedCats.forEach(c => { md += ` ${c} |`; });
          md += `\n|-------|-------|`;
          sortedCats.forEach(() => { md += `-------|`; });
          md += `\n`;
          data.comparison.forEach(comp => {
            md += `| ${comp.brand_name} | ${comp.total_articles} |`;
            sortedCats.forEach(cat => {
              const count = comp.category_breakdown[cat] || 0;
              md += ` ${count || '—'} |`;
            });
            md += `\n`;
          });
          md += `\n`;
        }
      }
    }

    // ===== SECTION 5: BRAND PROFILE =====
    if (data.selectedBrand) {
      md += `---\n\n# 5. Brand Profile\n\n`;
      const b = data.selectedBrand;
      md += `**${b.display_name}**`;
      if (b.description) md += ` — ${b.description}`;
      md += `\n\n`;
      if (b.brand_keywords?.length) md += `- **Brand Keywords:** ${b.brand_keywords.join(', ')}\n`;
      if (b.product_keywords?.length) md += `- **Product Keywords:** ${b.product_keywords.join(', ')}\n`;
      if (b.people_keywords?.length) md += `- **People Keywords:** ${b.people_keywords.join(', ')}\n`;
      if (b.competitor_keywords?.length) md += `- **Competitor Keywords:** ${b.competitor_keywords.join(', ')}\n`;
      md += `\n`;
    }

    // ===== SECTION 6: AI NARRATIVE =====
    if (data.narrative?.narrative) {
      md += `---\n\n# ${data.selectedBrand ? '6' : '5'}. AI-Generated Intelligence Narrative\n\n`;
      if (data.narrative.generated_at) {
        md += `*Narrative generated: ${new Date(data.narrative.generated_at).toLocaleString()}*\n\n`;
      }
      md += `${data.narrative.narrative}\n\n`;
      if (data.narrative.data_summary) {
        const ds = data.narrative.data_summary;
        md += `> Based on ${ds.total_articles} articles from ${ds.date_range?.start || '?'} to ${ds.date_range?.end || '?'}\n\n`;
      }
    }

    // ===== SECTION 7: ARTICLE INDEX =====
    if (data.articles && data.articles.length > 0) {
      const secNum = (data.selectedBrand ? 7 : 6);
      md += `---\n\n# ${secNum}. Article Index (${Math.min(data.articles.length, 50)} of ${data.articles.length})\n\n`;
      data.articles.slice(0, 50).forEach((a, i) => {
        md += `### ${i + 1}. ${a.title || 'Untitled'}\n\n`;
        const meta: string[] = [];
        if (a.news_source) meta.push(`Source: ${a.news_source}`);
        if (a.publication_date) meta.push(`Date: ${a.publication_date.slice(0, 10)}`);
        if (a.sentiment) meta.push(`Sentiment: ${a.sentiment}`);
        if (a.brand_name) meta.push(`Brand: ${a.brand_name}`);
        if (meta.length) md += `*${meta.join(' | ')}*\n\n`;
        if (a.categories?.length) md += `Categories: ${a.categories.join(', ')}\n\n`;
        if (a.matched_keywords?.length) md += `Matched keywords: ${a.matched_keywords.join(', ')}\n\n`;
        if (a.summary) md += `${a.summary}\n\n`;
      });
    }

    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `brand-intelligence-${brandLabel.toLowerCase().replace(/\s+/g, '-')}-${dateStr}.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  /**
   * Export Brand Watcher as text-based PDF — comprehensive multi-section report
   */
  static exportBrandWatcherPDF(data: {
    brandName?: string; daysBack?: number; stats?: any; categories?: any[];
    riskAssessment?: any;
    sentimentTrends?: any[]; comparison?: any[]; shareOfVoice?: any[];
    alerts?: any[]; narrative?: any; articles?: any[];
    temporalData?: any[]; selectedBrand?: any;
  }): void {
    const brandLabel = data.brandName || 'All Brands';
    const period = data.daysBack === 0 ? 'All Time' : `Last ${data.daysBack || 30} days`;
    const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });

    const pageWidth = 210;
    const pageHeight = 297;
    const margin = 15;
    const contentWidth = pageWidth - (margin * 2);
    let y = margin;

    const addPage = () => { pdf.addPage(); y = margin; };
    const checkPageBreak = (needed: number) => { if (y + needed > pageHeight - margin) addPage(); };

    const addText = (text: string, fontSize: number, isBold = false, color: number[] = [0, 0, 0]) => {
      pdf.setFontSize(fontSize);
      pdf.setFont('helvetica', isBold ? 'bold' : 'normal');
      pdf.setTextColor(color[0], color[1], color[2]);
      const lines = pdf.splitTextToSize(text, contentWidth);
      const lineHeight = fontSize * 0.4;
      checkPageBreak(lines.length * lineHeight + 2);
      pdf.text(lines, margin, y);
      y += lines.length * lineHeight + 2;
    };

    const addHRule = () => {
      checkPageBreak(8);
      y += 2;
      pdf.setDrawColor(200, 200, 200);
      pdf.line(margin, y, pageWidth - margin, y);
      y += 6;
    };

    const addSectionTitle = (text: string) => {
      checkPageBreak(15);
      y += 4;
      addText(text, 16, true, [0, 80, 160]);
      y += 2;
    };

    const addSubsectionTitle = (text: string, color: number[] = [40, 40, 40]) => {
      checkPageBreak(12);
      y += 2;
      addText(text, 12, true, color);
      y += 1;
    };

    // Helper: draw a simple text table
    const addTableRow = (cells: string[], widths: number[], isBold = false, color: number[] = [0, 0, 0]) => {
      const rowHeight = 5;
      checkPageBreak(rowHeight + 2);
      pdf.setFontSize(9);
      pdf.setFont('helvetica', isBold ? 'bold' : 'normal');
      pdf.setTextColor(color[0], color[1], color[2]);
      let x = margin;
      cells.forEach((cell, i) => {
        const w = widths[i] || 30;
        const truncated = cell.length > Math.floor(w / 1.8) ? cell.slice(0, Math.floor(w / 1.8)) + '..' : cell;
        pdf.text(truncated, x + 1, y);
        x += w;
      });
      y += rowHeight;
    };

    const addTableSeparator = (widths: number[]) => {
      pdf.setDrawColor(220, 220, 220);
      let x = margin;
      const totalW = widths.reduce((s, w) => s + w, 0);
      pdf.line(x, y, x + totalW, y);
      y += 1;
    };

    // ===== TITLE PAGE =====
    y = 60;
    addText('Brand Intelligence Report', 24, true, [0, 80, 160]);
    y += 5;
    addText(brandLabel, 18, false, [60, 60, 60]);
    y += 10;
    addText(`Period: ${period}`, 12, false, [120, 120, 120]);
    addText(`Generated: ${new Date().toLocaleString()}`, 12, false, [120, 120, 120]);
    y += 20;

    // AI Disclosure on title page
    addText('AI Technology Disclosure', 11, true, [100, 100, 100]);
    addText('This report was generated using AI technologies for brand intelligence analysis, article classification, sentiment tracking, and narrative generation. All content should be reviewed and validated by appropriate stakeholders.', 9, false, [130, 130, 130]);

    // Brand profile on title page
    if (data.selectedBrand) {
      y += 15;
      addText('Brand Profile', 12, true, [80, 80, 80]);
      if (data.selectedBrand.description) addText(data.selectedBrand.description, 10, false, [100, 100, 100]);
      if (data.selectedBrand.brand_keywords?.length)
        addText(`Brand keywords: ${data.selectedBrand.brand_keywords.join(', ')}`, 9, false, [120, 120, 120]);
      if (data.selectedBrand.product_keywords?.length)
        addText(`Product keywords: ${data.selectedBrand.product_keywords.join(', ')}`, 9, false, [120, 120, 120]);
      if (data.selectedBrand.people_keywords?.length)
        addText(`People keywords: ${data.selectedBrand.people_keywords.join(', ')}`, 9, false, [120, 120, 120]);
      if (data.selectedBrand.competitor_keywords?.length)
        addText(`Competitor keywords: ${data.selectedBrand.competitor_keywords.join(', ')}`, 9, false, [120, 120, 120]);
    }

    // ===== SECTION 1: EXECUTIVE OVERVIEW =====
    addPage();
    addSectionTitle('1. Executive Overview');

    if (data.stats) {
      addSubsectionTitle('Key Metrics');
      const colW = [60, 40];
      addTableRow(['Metric', 'Value'], colW, true);
      addTableSeparator(colW);
      addTableRow(['Total Articles', String(data.stats.total_articles ?? 0)], colW);
      addTableRow(['Active Brands', String(data.stats.total_brands ?? 0)], colW);
      addTableRow(['Most Active Category', data.stats.most_active_category || 'N/A'], colW);
      addTableRow(['Multi-Category Articles', String(data.stats.multi_category_count ?? 0)], colW);
      if (data.stats.date_range_start)
        addTableRow(['Date Range', `${data.stats.date_range_start} to ${data.stats.date_range_end}`], [60, 80]);
      y += 5;
    }

    // Aggregate sentiment
    if (data.sentimentTrends && data.sentimentTrends.length > 0) {
      const agg = { positive: 0, neutral: 0, negative: 0 };
      for (const t of data.sentimentTrends) {
        const s = this.bwNormalizeSentiment(t.sentiments || {});
        agg.positive += s.positive; agg.neutral += s.neutral; agg.negative += s.negative;
      }
      const sentTotal = agg.positive + agg.neutral + agg.negative;
      if (sentTotal > 0) {
        addSubsectionTitle('Overall Sentiment');
        const pPct = ((agg.positive / sentTotal) * 100).toFixed(1);
        const nuPct = ((agg.neutral / sentTotal) * 100).toFixed(1);
        const nPct = ((agg.negative / sentTotal) * 100).toFixed(1);
        addText(`Positive: ${agg.positive} (${pPct}%)  |  Neutral: ${agg.neutral} (${nuPct}%)  |  Negative: ${agg.negative} (${nPct}%)`, 10, false);
        if (parseFloat(nPct) >= 15) {
          y += 2;
          addText(`RISK FLAG: Negative sentiment at ${nPct}% exceeds 15% threshold`, 10, true, [200, 0, 0]);
        }
        y += 5;
      }

      // Risk assessment — Brand Risk v2: active issues, no 0-100 score
      if (data.riskAssessment) {
        const ra = data.riskAssessment;
        addSubsectionTitle('Brand Risk Assessment');
        if (ra.escalation_tier) {
          addText(`Status: ${ra.escalation_tier.label} — ${ra.escalation_tier.triggered.join('; ')}`, 11, true, [200, 0, 0]);
        }
        if (ra.active_issues?.length) {
          ra.active_issues.forEach((i: any) => {
            const c = i.severity === 'high' ? [200, 0, 0] : i.severity === 'medium' ? [200, 150, 0] : [150, 120, 0];
            addText(`[${i.severity.toUpperCase()}] ${i.primary_type.replace(/_/g, ' ')}: ${i.title}`, 10, true, c);
            addText(`${i.articles} articles, ${i.sources} sources, first seen ${i.first_seen}, ${i.momentum}`, 9, false);
          });
        } else {
          addText('No active issues — no adverse events currently open for this brand.', 10, false);
        }
        y += 5;
      }
    }

    // Spike alerts
    if (data.alerts && data.alerts.length > 0) {
      addSubsectionTitle('Spike Alerts', [200, 100, 0]);
      const colW = [20, 50, 22, 22, 18];
      addTableRow(['Severity', 'Category', 'Current', 'Average', 'Spike'], colW, true);
      addTableSeparator(colW);
      const sorted = [...data.alerts].sort((a, b) => b.spike_ratio - a.spike_ratio);
      const sevColors: Record<string, number[]> = { high: [220, 80, 0], medium: [200, 150, 0] };
      sorted.forEach(a => {
        const sev = a.severity || 'medium';
        addTableRow(
          [sev.toUpperCase(), a.category, String(a.current_count), a.average_count?.toFixed(1), `${a.spike_ratio?.toFixed(1)}x`],
          colW, false, sevColors[sev] || [100, 100, 100]
        );
      });
      y += 5;
    }

    // ===== SECTION 2: SENTIMENT ANALYSIS =====
    addHRule();
    addSectionTitle('2. Sentiment Analysis');

    if (data.sentimentTrends && data.sentimentTrends.length > 0) {
      addSubsectionTitle('Weekly Sentiment Trend');
      const colW = [28, 20, 20, 20, 18, 18];
      addTableRow(['Week', 'Positive', 'Neutral', 'Negative', 'Total', 'Neg%'], colW, true);
      addTableSeparator(colW);
      data.sentimentTrends.forEach(t => {
        const s = this.bwNormalizeSentiment(t.sentiments || {});
        const total = s.positive + s.neutral + s.negative;
        const negPct = total > 0 ? ((s.negative / total) * 100).toFixed(1) : '0.0';
        addTableRow([t.week, String(s.positive), String(s.neutral), String(s.negative), String(total), `${negPct}%`], colW);
      });
      y += 5;

      // Sentiment by category
      const catSent: Record<string, { positive: number; neutral: number; negative: number }> = {};
      for (const t of data.sentimentTrends) {
        const cat = t.category || 'Overall';
        if (!catSent[cat]) catSent[cat] = { positive: 0, neutral: 0, negative: 0 };
        const s = this.bwNormalizeSentiment(t.sentiments || {});
        catSent[cat].positive += s.positive;
        catSent[cat].neutral += s.neutral;
        catSent[cat].negative += s.negative;
      }
      if (Object.keys(catSent).length > 1) {
        addSubsectionTitle('Sentiment by Category');
        const colW2 = [50, 20, 20, 20, 18];
        addTableRow(['Category', 'Positive', 'Neutral', 'Negative', 'Total'], colW2, true);
        addTableSeparator(colW2);
        for (const [cat, s] of Object.entries(catSent)) {
          const total = s.positive + s.neutral + s.negative;
          addTableRow([cat, String(s.positive), String(s.neutral), String(s.negative), String(total)], colW2);
        }
        y += 5;
      }
    }

    // ===== SECTION 3: CATEGORY DISTRIBUTION =====
    addHRule();
    addSectionTitle('3. Category Distribution');

    if (data.categories && data.categories.length > 0) {
      addSubsectionTitle('Category Breakdown');
      const colW = [55, 20, 18, 20];
      addTableRow(['Category', 'Articles', 'Share', 'Trend'], colW, true);
      addTableSeparator(colW);
      data.categories.forEach(c => {
        const trend = c.recent_trend === 'up' ? 'Rising' : c.recent_trend === 'down' ? 'Declining' : 'Stable';
        const trendColor = c.recent_trend === 'up' ? [0, 150, 50] : c.recent_trend === 'down' ? [200, 50, 50] : [100, 100, 100];
        addTableRow([c.category, String(c.article_count), `${c.percentage?.toFixed(1)}%`, trend], colW, false, trendColor);
      });
      y += 5;
    }

    // Monthly volume
    if (data.temporalData && data.temporalData.length > 0) {
      addSubsectionTitle('Monthly Article Volume');
      const months = data.temporalData.slice(-12);
      const topCats = (data.categories || []).slice(0, 5).map(c => c.category);
      // Header
      const colW = [22, 16];
      topCats.forEach(() => colW.push(Math.floor((contentWidth - 38) / topCats.length)));
      addTableRow(['Month', 'Total', ...topCats.map(c => c.length > 12 ? c.slice(0, 12) + '..' : c)], colW, true);
      addTableSeparator(colW);
      months.forEach(d => {
        addTableRow(
          [d.month, String(d.total), ...topCats.map(cat => String(d.by_category?.[cat] || 0))],
          colW
        );
      });
      y += 5;
    }

    // ===== SECTION 4: COMPETITIVE COMPARISON =====
    if ((data.comparison && data.comparison.length > 1) || (data.shareOfVoice && data.shareOfVoice.length > 1)) {
      addHRule();
      addSectionTitle('4. Competitive Comparison');

      // Share of Voice
      if (data.shareOfVoice && data.shareOfVoice.length > 1) {
        addSubsectionTitle('Share of Voice');
        const colW = [50, 25, 25];
        addTableRow(['Brand', 'Mentions', 'Share'], colW, true);
        addTableSeparator(colW);
        const sovTotal = data.shareOfVoice.reduce((s, b) => s + (b.mention_count || 0), 0);
        data.shareOfVoice.forEach(b => {
          const pct = sovTotal > 0 ? ((b.mention_count / sovTotal) * 100).toFixed(1) : b.percentage?.toFixed(1) || '0.0';
          addTableRow([b.brand_name, String(b.mention_count), `${pct}%`], colW);
        });
        y += 5;
      }

      // Sentiment by brand
      if (data.comparison && data.comparison.length > 1) {
        addSubsectionTitle('Sentiment by Brand');
        const colW = [40, 18, 20, 20, 20];
        addTableRow(['Brand', 'Total', 'Positive', 'Neutral', 'Negative'], colW, true);
        addTableSeparator(colW);
        data.comparison.forEach(comp => {
          const s = this.bwNormalizeSentiment(comp.sentiment_breakdown || {});
          addTableRow([comp.brand_name, String(comp.total_articles), String(s.positive), String(s.neutral), String(s.negative)], colW);
        });
        y += 5;

        // Category matrix
        const allCats = new Set<string>();
        data.comparison.forEach(comp => {
          Object.entries(comp.category_breakdown || {}).forEach(([k, v]) => { if (v > 0) allCats.add(k); });
        });
        const sortedCats = [...allCats].sort((a, b) => {
          const aT = data.comparison!.reduce((s, c) => s + (c.category_breakdown[a] || 0), 0);
          const bT = data.comparison!.reduce((s, c) => s + (c.category_breakdown[b] || 0), 0);
          return bT - aT;
        }).slice(0, 8);

        if (sortedCats.length > 0) {
          addSubsectionTitle('Category Breakdown by Brand');
          const catColW = [35, 16];
          sortedCats.forEach(() => catColW.push(Math.floor((contentWidth - 51) / sortedCats.length)));
          addTableRow(['Brand', 'Total', ...sortedCats.map(c => c.length > 10 ? c.slice(0, 10) + '..' : c)], catColW, true);
          addTableSeparator(catColW);
          data.comparison.forEach(comp => {
            addTableRow(
              [comp.brand_name, String(comp.total_articles), ...sortedCats.map(cat => String(comp.category_breakdown[cat] || 0))],
              catColW
            );
          });
          y += 5;
        }
      }
    }

    // ===== SECTION 5: AI NARRATIVE =====
    if (data.narrative?.narrative) {
      addHRule();
      addSectionTitle(`${data.comparison && data.comparison.length > 1 ? '5' : '4'}. AI-Generated Intelligence Narrative`);
      if (data.narrative.generated_at) {
        addText(`Generated: ${new Date(data.narrative.generated_at).toLocaleString()}`, 9, false, [150, 150, 150]);
      }
      y += 2;
      // Render narrative — split paragraphs for readability
      const paragraphs = data.narrative.narrative.split(/\n{2,}/);
      paragraphs.forEach((para: string) => {
        const trimmed = para.trim();
        if (!trimmed) return;
        // Detect markdown headers
        if (trimmed.startsWith('## ')) {
          y += 3;
          addText(trimmed.replace(/^##\s*/, ''), 12, true, [40, 40, 40]);
        } else if (trimmed.startsWith('### ')) {
          y += 2;
          addText(trimmed.replace(/^###\s*/, ''), 11, true, [60, 60, 60]);
        } else if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
          // Bullet list
          trimmed.split('\n').forEach(line => {
            const bulletText = line.replace(/^[-*]\s*/, '');
            if (bulletText) addText(`  \u2022 ${bulletText.replace(/\*\*/g, '')}`, 10, false);
          });
        } else {
          addText(trimmed.replace(/\*\*/g, ''), 10, false);
        }
        y += 2;
      });
      if (data.narrative.data_summary) {
        y += 3;
        const ds = data.narrative.data_summary;
        addText(`Based on ${ds.total_articles} articles from ${ds.date_range?.start || '?'} to ${ds.date_range?.end || '?'}`, 9, false, [130, 130, 130]);
      }
      y += 5;
    }

    // ===== SECTION 6: ARTICLE INDEX =====
    if (data.articles && data.articles.length > 0) {
      addHRule();
      const secNum = (data.comparison && data.comparison.length > 1) ? 6 : 5;
      addSectionTitle(`${secNum}. Article Index (${Math.min(data.articles.length, 50)} of ${data.articles.length})`);

      data.articles.slice(0, 50).forEach((a, i) => {
        checkPageBreak(20);
        addText(`${i + 1}. ${a.title || 'Untitled'}`, 10, true);
        const meta: string[] = [];
        if (a.news_source) meta.push(a.news_source);
        if (a.publication_date) meta.push(a.publication_date.slice(0, 10));
        if (a.sentiment) meta.push(a.sentiment);
        if (a.brand_name) meta.push(a.brand_name);
        if (meta.length) addText(meta.join('  |  '), 8, false, [120, 120, 120]);
        if (a.categories?.length) addText(`Categories: ${a.categories.join(', ')}`, 8, false, [100, 100, 100]);
        if (a.matched_keywords?.length) addText(`Keywords: ${a.matched_keywords.join(', ')}`, 8, false, [100, 100, 100]);
        if (a.summary) {
          const summaryTrunc = a.summary.length > 200 ? a.summary.slice(0, 200) + '...' : a.summary;
          addText(summaryTrunc, 9, false, [60, 60, 60]);
        }
        y += 3;
      });
    }

    // Footer on all pages
    const totalPages = pdf.getNumberOfPages();
    for (let i = 1; i <= totalPages; i++) {
      pdf.setPage(i);
      pdf.setFontSize(8);
      pdf.setTextColor(150, 150, 150);
      pdf.text(`Page ${i} of ${totalPages}`, pageWidth / 2, pageHeight - 10, { align: 'center' });
      pdf.text(`Brand Intelligence Report — ${brandLabel} — Generated by Aunoo AI`, pageWidth / 2, pageHeight - 5, { align: 'center' });
    }

    const dateStr = new Date().toISOString().split('T')[0];
    pdf.save(`brand-intelligence-${brandLabel.toLowerCase().replace(/\s+/g, '-')}-${dateStr}.pdf`);
  }
}
