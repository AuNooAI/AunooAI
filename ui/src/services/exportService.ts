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
        scale: 2,
        useCORS: true,
        logging: false,
        backgroundColor: '#ffffff',
        windowHeight: element.scrollHeight,
        height: element.scrollHeight
      });

    const imgData = canvas.toDataURL('image/png');
    const pdf = new jsPDF({
      orientation: 'portrait',
      unit: 'mm',
      format: 'a4'
    });

    const imgWidth = 210; // A4 width in mm
    const pageHeight = 297; // A4 height in mm
    const imgHeight = (canvas.height * imgWidth) / canvas.width;
    let heightLeft = imgHeight;
    let position = 0;

    // Add first page
    pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight);
    heightLeft -= pageHeight;

    // Add additional pages if content is longer than one page
    while (heightLeft >= 0) {
      position = heightLeft - imgHeight;
      pdf.addPage();
      pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight);
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
   * Helper: Get purpose text for dashboard type
   */
  private static getPurpose(dashboardType: string): string {
    const purposes: Record<string, string> = {
      'Consensus Analysis': 'To analyze convergent themes across multiple sources',
      'Strategic Recommendations': 'To synthesize actionable strategic insights',
      'Market Signals': 'To identify market trends, risks, and opportunities',
      'Impact Timeline': 'To project temporal sequences of anticipated impacts',
      'Future Horizons': 'To explore long-term implications and future scenarios'
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
}
