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
    markdown += `- **AI Tools**: GPT-4, OpenAI Embeddings\n`;
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
    addText('This analysis was generated using AI technologies (GPT-4, OpenAI Embeddings) for extreme scenario planning and risk identification. All content should be reviewed and validated by domain experts.', 9, false, [100, 100, 100]);
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
    md += `This analysis was generated using AI technologies (GPT-4, OpenAI Embeddings) for extreme scenario planning and risk identification. All content should be reviewed and validated by domain experts.\n\n`;
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
    addText('This analysis was generated using AI technologies (GPT-4, OpenAI Embeddings) for audience persona development. All content should be reviewed and validated by domain experts.', 9, false, [100, 100, 100]);
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
    md += `This analysis was generated using AI technologies (GPT-4, OpenAI Embeddings) for audience persona development. All content should be reviewed and validated by domain experts.\n\n`;
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
}
