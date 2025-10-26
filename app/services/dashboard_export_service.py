"""Dashboard export service for exporting dashboards to Markdown, PDF, and Image formats."""

import logging
import tempfile
from typing import Dict, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class DashboardExportService:
    """Service for exporting dashboards to various formats."""

    @staticmethod
    def export_to_markdown(
        dashboard_data: Dict,
        dashboard_type: str,
        include_metadata: bool = True
    ) -> str:
        """Export dashboard to Markdown format.

        Args:
            dashboard_data: Dashboard data dictionary
            dashboard_type: Type of dashboard
            include_metadata: Include generation metadata

        Returns:
            Markdown string
        """
        lines = []

        # Header
        title = dashboard_data.get('title', f'{dashboard_type.replace("_", " ").title()} Dashboard')
        lines.append(f"# {title}\n")

        # Metadata section
        if include_metadata:
            lines.append("## Metadata\n")
            if 'generated_at' in dashboard_data:
                lines.append(f"- **Generated**: {dashboard_data['generated_at']}")
            if 'date_range' in dashboard_data:
                lines.append(f"- **Date Range**: {dashboard_data['date_range']}")
            if 'topic' in dashboard_data and dashboard_data['topic']:
                lines.append(f"- **Topic**: {dashboard_data['topic']}")
            if 'article_count' in dashboard_data:
                lines.append(f"- **Articles**: {dashboard_data['article_count']}")
            if 'model_used' in dashboard_data and dashboard_data['model_used']:
                lines.append(f"- **Model**: {dashboard_data['model_used']}")
            lines.append("")

        # Content based on dashboard type
        content = dashboard_data.get('content', {})

        if dashboard_type == 'news_feed':
            lines.append("## Articles\n")
            items = content.get('items', [])
            for i, item in enumerate(items, 1):
                title = item.get('title', 'Untitled')
                summary = item.get('summary', 'No summary available')
                source = item.get('source', 'Unknown')
                url = item.get('url', '#')

                lines.append(f"### {i}. {title}\n")
                lines.append(f"**Source**: {source}")
                if url and url != '#':
                    lines.append(f"**URL**: {url}")
                lines.append(f"\n{summary}\n")

        elif dashboard_type == 'six_articles':
            lines.append("## Detailed Analysis\n")
            articles = content if isinstance(content, list) else content.get('articles', [])
            for i, article in enumerate(articles, 1):
                headline = article.get('headline', 'Untitled')
                summary = article.get('summary', 'No summary available')
                analysis = article.get('analysis', '')

                lines.append(f"### {i}. {headline}\n")
                lines.append(f"**Summary**: {summary}\n")
                if analysis:
                    lines.append(f"**Analysis**: {analysis}\n")

        elif dashboard_type == 'highlights':
            lines.append("## Highlights / Incident Tracking\n")
            incidents = content if isinstance(content, list) else content.get('incidents', [])
            for i, incident in enumerate(incidents, 1):
                title = incident.get('title') or incident.get('name', 'Untitled Incident')
                description = incident.get('description', 'No description available')

                lines.append(f"### {i}. {title}\n")

                # Metadata
                metadata_parts = []
                if incident.get('type'):
                    metadata_parts.append(f"**Type**: {incident['type']}")
                if incident.get('significance'):
                    metadata_parts.append(f"**Significance**: {incident['significance']}")
                if incident.get('plausibility'):
                    metadata_parts.append(f"**Plausibility**: {incident['plausibility']}")
                if incident.get('source_quality'):
                    metadata_parts.append(f"**Source Quality**: {incident['source_quality']}")

                if metadata_parts:
                    lines.append(" | ".join(metadata_parts) + "\n")

                # Timeline
                if isinstance(incident.get('timeline'), list) and incident['timeline']:
                    dates = [d for d in incident['timeline'] if d]
                    if dates:
                        timeline_text = f"**Timeline**: {dates[0]}"
                        if len(dates) > 1 and dates[-1] != dates[0]:
                            timeline_text += f" to {dates[-1]}"
                        lines.append(timeline_text + "\n")
                elif isinstance(incident.get('timeline'), str):
                    lines.append(f"**Timeline**: {incident['timeline']}\n")

                lines.append(f"\n{description}\n")

                # Investigation leads
                if incident.get('investigation_leads'):
                    leads = incident['investigation_leads']
                    if isinstance(leads, list):
                        lines.append("\n**Investigation Leads**:\n")
                        for lead in leads[:5]:
                            lines.append(f"- {lead}")
                        lines.append("")
                    else:
                        lines.append(f"\n**Investigation Leads**: {leads}\n")

        elif dashboard_type == 'narratives':
            lines.append("## Narratives / Article Insights\n")
            insights = content if isinstance(content, list) else content.get('insights', [])
            for i, insight in enumerate(insights, 1):
                theme_name = insight.get('theme_name', 'Unnamed Theme')
                theme_summary = insight.get('theme_summary', 'No summary available')

                lines.append(f"### {i}. {theme_name}\n")
                lines.append(f"{theme_summary}\n")

                # Related articles
                articles = insight.get('articles', [])
                if articles:
                    lines.append(f"\n**Related Articles** ({len(articles)}):\n")
                    for article in articles[:10]:
                        title = article.get('title', 'Untitled')
                        uri = article.get('uri', '#')
                        lines.append(f"- [{title}]({uri})")
                    if len(articles) > 10:
                        lines.append(f"- ... and {len(articles) - 10} more")
                    lines.append("")

        elif dashboard_type == 'insights':
            lines.append("## Insights\n")
            insights = content.get('insights', [])
            for i, insight in enumerate(insights, 1):
                title = insight.get('title', 'Insight')
                description = insight.get('description', '')

                lines.append(f"### {i}. {title}\n")
                lines.append(f"{description}\n")

        else:
            # Generic fallback
            lines.append("## Content\n")
            lines.append(f"```json\n{content}\n```\n")

        # Footer
        lines.append("\n---")
        lines.append(f"\n*Exported on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

        return '\n'.join(lines)

    @staticmethod
    def export_to_pdf(
        dashboard_data: Dict,
        dashboard_type: str,
        output_path: Optional[str] = None
    ) -> str:
        """Export dashboard to PDF format.

        Args:
            dashboard_data: Dashboard data dictionary
            dashboard_type: Type of dashboard
            output_path: Optional output file path

        Returns:
            Path to generated PDF file
        """
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
            from reportlab.lib.enums import TA_LEFT, TA_CENTER
        except ImportError:
            logger.error("reportlab not installed. Install with: pip install reportlab")
            raise ImportError("reportlab is required for PDF export")

        # Create output file
        if output_path is None:
            output_path = tempfile.mktemp(suffix='.pdf', prefix='dashboard_')

        # Create PDF document
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18
        )

        # Container for the 'Flowable' objects
        elements = []

        # Define styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor='#1a1a1a',
            spaceAfter=30,
            alignment=TA_CENTER
        )
        heading_style = styles['Heading2']
        normal_style = styles['BodyText']

        # Title
        title = dashboard_data.get('title', f'{dashboard_type.replace("_", " ").title()} Dashboard')
        elements.append(Paragraph(title, title_style))
        elements.append(Spacer(1, 12))

        # Metadata
        metadata_lines = []
        if 'generated_at' in dashboard_data:
            metadata_lines.append(f"<b>Generated:</b> {dashboard_data['generated_at']}")
        if 'date_range' in dashboard_data:
            metadata_lines.append(f"<b>Date Range:</b> {dashboard_data['date_range']}")
        if 'topic' in dashboard_data and dashboard_data['topic']:
            metadata_lines.append(f"<b>Topic:</b> {dashboard_data['topic']}")
        if 'article_count' in dashboard_data:
            metadata_lines.append(f"<b>Articles:</b> {dashboard_data['article_count']}")

        for line in metadata_lines:
            elements.append(Paragraph(line, normal_style))
        elements.append(Spacer(1, 20))

        # Content
        content = dashboard_data.get('content', {})

        # Debug logging
        logger.info(f"PDF Export - Dashboard Type: {dashboard_type}")
        logger.info(f"PDF Export - dashboard_data keys: {list(dashboard_data.keys()) if isinstance(dashboard_data, dict) else 'not a dict'}")
        logger.info(f"PDF Export - content type: {type(content)}")
        logger.info(f"PDF Export - content keys: {list(content.keys()) if isinstance(content, dict) else 'not a dict'}")

        if dashboard_type == 'news_feed':
            elements.append(Paragraph("Articles", heading_style))
            elements.append(Spacer(1, 12))

            items = content.get('items', [])
            for i, item in enumerate(items, 1):
                title_text = item.get('title', 'Untitled')
                summary = item.get('summary', 'No summary available')
                source = item.get('source', 'Unknown')

                elements.append(Paragraph(f"<b>{i}. {title_text}</b>", normal_style))
                elements.append(Paragraph(f"<i>Source: {source}</i>", normal_style))
                elements.append(Paragraph(summary, normal_style))
                elements.append(Spacer(1, 12))

        elif dashboard_type == 'six_articles':
            elements.append(Paragraph("Detailed Analysis", heading_style))
            elements.append(Spacer(1, 12))

            articles = content if isinstance(content, list) else content.get('articles', [])
            for i, article in enumerate(articles, 1):
                headline = article.get('headline', 'Untitled')
                summary = article.get('summary', 'No summary available')

                elements.append(Paragraph(f"<b>{i}. {headline}</b>", normal_style))
                elements.append(Paragraph(summary, normal_style))
                elements.append(Spacer(1, 12))

        elif dashboard_type == 'highlights':
            elements.append(Paragraph("Highlights / Incident Tracking", heading_style))
            elements.append(Spacer(1, 12))

            incidents = content if isinstance(content, list) else content.get('incidents', [])
            logger.info(f"PDF Export - Highlights: content type={type(content)}, incidents type={type(incidents)}, incidents count={len(incidents) if isinstance(incidents, list) else 'N/A'}")

            if isinstance(content, dict):
                logger.info(f"PDF Export - Content dict keys: {list(content.keys())}")
                if 'incidents' in content:
                    logger.info(f"PDF Export - incidents key found, length: {len(content['incidents'])}")
                    logger.info(f"PDF Export - First incident keys: {list(content['incidents'][0].keys()) if content['incidents'] else 'empty'}")

            if not incidents:
                logger.warning(f"PDF Export - No incidents found. Content: {content if len(str(content)) < 500 else str(content)[:500] + '...'}")
                elements.append(Paragraph("No incidents available", normal_style))
            else:
                logger.info(f"PDF Export - Processing {len(incidents)} incidents")

            for i, incident in enumerate(incidents, 1):
                try:
                    title = incident.get('title') or incident.get('name', 'Untitled Incident')
                    description = incident.get('description', 'No description available')

                    logger.info(f"PDF Export - Processing incident {i}: {title[:50]}...")

                    # Title and metadata
                    elements.append(Paragraph(f"<b>{i}. {title}</b>", normal_style))

                    # Metadata
                    metadata_parts = []
                    if incident.get('type'):
                        metadata_parts.append(f"Type: {incident['type']}")
                    if incident.get('significance'):
                        metadata_parts.append(f"Significance: {incident['significance']}")
                    if incident.get('plausibility'):
                        metadata_parts.append(f"Plausibility: {incident['plausibility']}")
                    if incident.get('source_quality'):
                        metadata_parts.append(f"Source Quality: {incident['source_quality']}")

                    if metadata_parts:
                        elements.append(Paragraph(f"<i>{' | '.join(metadata_parts)}</i>", normal_style))

                    # Timeline
                    timeline_text = None
                    if isinstance(incident.get('timeline'), list) and incident['timeline']:
                        dates = [d for d in incident['timeline'] if d]
                        if dates:
                            timeline_text = f"Timeline: {dates[0]}"
                            if len(dates) > 1 and dates[-1] != dates[0]:
                                timeline_text += f" to {dates[-1]}"
                    elif isinstance(incident.get('timeline'), str):
                        timeline_text = f"Timeline: {incident['timeline']}"

                    if timeline_text:
                        elements.append(Paragraph(timeline_text, normal_style))

                    # Description
                    elements.append(Paragraph(description, normal_style))

                    # Investigation leads
                    if incident.get('investigation_leads'):
                        leads = incident['investigation_leads']
                        if isinstance(leads, list):
                            leads_text = "Investigation Leads: " + ", ".join(str(l) for l in leads[:5])
                        else:
                            leads_text = f"Investigation Leads: {leads}"
                        elements.append(Paragraph(f"<i>{leads_text}</i>", normal_style))

                    # Related Articles
                    if incident.get('article_uris') and len(incident['article_uris']) > 0:
                        article_count = len(incident['article_uris'])
                        elements.append(Paragraph(f"<i>Related Articles ({article_count}):</i>", normal_style))

                        # Show first 10 article URLs
                        for article_uri in incident['article_uris'][:10]:
                            # Use smaller font for URLs
                            from reportlab.lib.styles import ParagraphStyle
                            url_style = ParagraphStyle(
                                'URLStyle',
                                parent=normal_style,
                                fontSize=8,
                                textColor='#0066cc'
                            )
                            elements.append(Paragraph(f"• {article_uri}", url_style))

                        if article_count > 10:
                            elements.append(Paragraph(f"<i>... and {article_count - 10} more</i>", normal_style))

                    elements.append(Spacer(1, 12))
                except Exception as e:
                    logger.error(f"PDF Export - Error rendering incident {i}: {e}", exc_info=True)
                    elements.append(Paragraph(f"<b>{i}. Error rendering incident: {str(e)}</b>", normal_style))
                    elements.append(Spacer(1, 12))

        elif dashboard_type == 'narratives':
            elements.append(Paragraph("Narratives / Article Insights", heading_style))
            elements.append(Spacer(1, 12))

            insights = content if isinstance(content, list) else content.get('insights', [])
            for i, insight in enumerate(insights, 1):
                theme_name = insight.get('theme_name', 'Unnamed Theme')
                theme_summary = insight.get('theme_summary', 'No summary available')

                # Theme name
                elements.append(Paragraph(f"<b>{i}. {theme_name}</b>", normal_style))

                # Theme summary
                elements.append(Paragraph(theme_summary, normal_style))

                # Related articles
                articles = insight.get('articles', [])
                if articles:
                    article_count = len(articles)
                    elements.append(Paragraph(f"<i>Related Articles ({article_count}):</i>", normal_style))

                    # Show article titles and URLs
                    from reportlab.lib.styles import ParagraphStyle
                    url_style = ParagraphStyle(
                        'URLStyle',
                        parent=normal_style,
                        fontSize=9,
                        textColor='#0066cc'
                    )

                    for article in articles[:10]:
                        title = article.get('title', 'Untitled')
                        uri = article.get('uri', '')
                        source = article.get('news_source', '')

                        # Title and source
                        title_text = f"• {title}"
                        if source:
                            title_text += f" - {source}"
                        elements.append(Paragraph(title_text, normal_style))

                        # URL on separate line
                        if uri:
                            elements.append(Paragraph(f"  {uri}", url_style))

                    if article_count > 10:
                        elements.append(Paragraph(f"<i>... and {article_count - 10} more</i>", normal_style))

                elements.append(Spacer(1, 12))

        # Build PDF
        doc.build(elements)

        logger.info(f"PDF exported to: {output_path}")
        return output_path

    @staticmethod
    async def export_to_image(
        dashboard_data: Dict,
        dashboard_type: str,
        output_path: Optional[str] = None,
        width: int = 1200,
        height: int = 800
    ) -> str:
        """Export dashboard to PNG image format using playwright.

        Args:
            dashboard_data: Dashboard data dictionary
            dashboard_type: Type of dashboard
            output_path: Optional output file path
            width: Image width in pixels
            height: Image height in pixels

        Returns:
            Path to generated PNG file
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("playwright not installed. Install with: pip install playwright && playwright install")
            raise ImportError("playwright is required for image export")

        # Create output file
        if output_path is None:
            output_path = tempfile.mktemp(suffix='.png', prefix='dashboard_')

        # Generate HTML content
        html_content = DashboardExportService._generate_html_for_screenshot(
            dashboard_data,
            dashboard_type
        )

        # Create temporary HTML file
        temp_html = tempfile.mktemp(suffix='.html', prefix='dashboard_')
        with open(temp_html, 'w', encoding='utf-8') as f:
            f.write(html_content)

        # Take screenshot with playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={'width': width, 'height': height})
            await page.goto(f'file://{temp_html}')
            await page.screenshot(path=output_path, full_page=True)
            await browser.close()

        # Clean up temp HTML
        Path(temp_html).unlink()

        logger.info(f"Image exported to: {output_path}")
        return output_path

    @staticmethod
    def _generate_html_for_screenshot(dashboard_data: Dict, dashboard_type: str) -> str:
        """Generate HTML content for screenshot rendering.

        Args:
            dashboard_data: Dashboard data dictionary
            dashboard_type: Type of dashboard

        Returns:
            HTML string
        """
        title = dashboard_data.get('title', f'{dashboard_type.replace("_", " ").title()} Dashboard')
        content = dashboard_data.get('content', {})

        # Basic styling
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                    padding: 40px;
                    background: #ffffff;
                    color: #1a1a1a;
                }}
                h1 {{
                    color: #2563eb;
                    border-bottom: 3px solid #2563eb;
                    padding-bottom: 10px;
                }}
                h2 {{
                    color: #3b82f6;
                    margin-top: 30px;
                }}
                .metadata {{
                    background: #f3f4f6;
                    padding: 15px;
                    border-radius: 8px;
                    margin: 20px 0;
                }}
                .article {{
                    margin: 20px 0;
                    padding: 15px;
                    border-left: 4px solid #2563eb;
                    background: #f9fafb;
                }}
                .article-title {{
                    font-weight: bold;
                    font-size: 1.1em;
                    color: #1a1a1a;
                }}
                .article-source {{
                    color: #6b7280;
                    font-size: 0.9em;
                }}
                .article-summary {{
                    margin-top: 10px;
                    line-height: 1.6;
                }}
            </style>
        </head>
        <body>
            <h1>{title}</h1>
        """

        # Metadata
        if 'generated_at' in dashboard_data or 'date_range' in dashboard_data:
            html += '<div class="metadata">'
            if 'generated_at' in dashboard_data:
                html += f'<div><strong>Generated:</strong> {dashboard_data["generated_at"]}</div>'
            if 'date_range' in dashboard_data:
                html += f'<div><strong>Date Range:</strong> {dashboard_data["date_range"]}</div>'
            if 'topic' in dashboard_data and dashboard_data['topic']:
                html += f'<div><strong>Topic:</strong> {dashboard_data["topic"]}</div>'
            if 'article_count' in dashboard_data:
                html += f'<div><strong>Articles:</strong> {dashboard_data["article_count"]}</div>'
            html += '</div>'

        # Content
        if dashboard_type == 'news_feed':
            html += '<h2>Articles</h2>'
            items = content.get('items', [])
            for i, item in enumerate(items, 1):
                item_title = item.get('title', 'Untitled')
                summary = item.get('summary', 'No summary available')
                source = item.get('source', 'Unknown')

                html += f'''
                <div class="article">
                    <div class="article-title">{i}. {item_title}</div>
                    <div class="article-source">Source: {source}</div>
                    <div class="article-summary">{summary}</div>
                </div>
                '''

        elif dashboard_type == 'six_articles':
            html += '<h2>Detailed Analysis</h2>'
            articles = content if isinstance(content, list) else content.get('articles', [])
            for i, article in enumerate(articles, 1):
                headline = article.get('headline', 'Untitled')
                summary = article.get('summary', 'No summary available')

                html += f'''
                <div class="article">
                    <div class="article-title">{i}. {headline}</div>
                    <div class="article-summary">{summary}</div>
                </div>
                '''

        html += """
        </body>
        </html>
        """

        return html
