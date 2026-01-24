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
      format: 'pdf' | 'image';
    },
    scenarios: any[],
    summaries: any[] | null,
    topic: string
  ): Promise<void> {
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
            AI Technology Disclosure: This analysis was generated using AI (GPT-4) for scenario planning and future horizons modeling.
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
              <strong style="font-style: normal; color: #374151;">Minority view (${summary.minority_view.percentage_range}):</strong> ${summary.minority_view.statement}
            </p>
          ` : ''}

          <div style="background: #f8fafc; padding: 12px; border-radius: 6px; margin-bottom: 12px; border: 1px solid #e2e8f0;">
            <p style="font-size: 11px; font-weight: 600; color: ${summary.consensus_percentage >= 80 ? '#16a34a' : summary.consensus_percentage >= 60 ? '#d97706' : '#ea580c'}; margin: 0 0 4px 0; text-transform: uppercase; letter-spacing: 0.05em;">
              PRIMARY SIGNAL (${summary.consensus_percentage || 85}% CONSENSUS)
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
}
