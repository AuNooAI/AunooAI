import { Button, Collapsible, CollapsibleContent, CollapsibleTrigger, Eyebrow, Icon, IconButton, Menu, SettingRow, Stack } from '@aunoo/ui';
import type { BWSavedNarrative } from '@monolith/brandWatcherApi';
import { Markdown } from '../../../../shell/Markdown';
import { download } from '../../../feed/api';
import { REPORT_SECTIONS, titleCase } from './shared';

/** The report, section by section in reading order; sections the model added come last. */
export function ReportSections({ narrative, sections }: { narrative: BWSavedNarrative; sections: Record<string, string> }) {
  const known = new Set(REPORT_SECTIONS.map(([k]) => k));
  const blocks: [string, string, string][] = [
    ...REPORT_SECTIONS.filter(([k]) => sections[k]).map(([k, label]) => [k, label, sections[k]] as [string, string, string]),
    ...Object.entries(sections).filter(([k, md]) => !known.has(k) && md).map(([k, md]) => [k, titleCase(k), md] as [string, string, string]),
  ];
  // An older report with no recognisable sections renders whole
  if (!blocks.length) return <Markdown text={narrative.narrative} />;
  return (
    <Stack gap="lg">
      {blocks.map(([k, label, md]) => (
        <Stack key={k} gap="sm">
          <Eyebrow as="h3">{label}</Eyebrow>
          <Markdown text={md} />
        </Stack>
      ))}
    </Stack>
  );
}

/** One report section beside the data it reads, folded away until opened. Renders nothing when the report lacks it. */
export function InsightStrip({ md, label, onFull }: { md?: string; label: string; onFull: () => void }) {
  if (!md) return null;
  return (
    <Collapsible>
      <SettingRow title={`AI reading: ${label}`} description="From the latest brand report" actions={<CollapsibleTrigger variant="onSurface">Show</CollapsibleTrigger>}>
        <CollapsibleContent>
          <Stack gap="sm">
            <Markdown text={md} />
            <div><Button variant="ghost" size="sm" iconEnd={<Icon name="ArrowRight" size="sm" />} onClick={onFull}>Full report</Button></div>
          </Stack>
        </CollapsibleContent>
      </SettingRow>
    </Collapsible>
  );
}

/** Copy or download the report, as the old export menu did (minus print, which the browser does). */
export function ReportExport({ narrative, brandName, notify }: { narrative: BWSavedNarrative; brandName: string; notify: (m: string) => void }) {
  const date = narrative.generated_at ? new Date(narrative.generated_at).toISOString().slice(0, 10) : 'report';
  const file = `brand-report-${brandName.toLowerCase().replace(/\s+/g, '-')}-${date}`;
  const header = `# Brand intelligence report: ${brandName}\n_Written ${narrative.generated_at ? new Date(narrative.generated_at).toLocaleString('en-GB') : 'at an unknown time'}_\n\n`;
  return (
    <Menu
      trigger={<IconButton icon={<Icon name="DownloadSimple" size="sm" />} label="Export the report" />}
      items={[
        { id: 'copy', label: 'Copy as Markdown', icon: 'Copy' },
        { id: 'md', label: 'Download Markdown', icon: 'FileText' },
      ]}
      onSelect={async (id) => {
        if (id === 'copy') {
          try {
            await navigator.clipboard.writeText(narrative.narrative);
            notify('Report copied');
          } catch {
            notify('This browser didn’t allow copying');
          }
        } else download(`${file}.md`, header + narrative.narrative);
      }}
      align="end"
    />
  );
}
