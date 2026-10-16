import { useState } from 'react';
import { ActivityRow, Banner, Button, Chip, Icon, IconButton, Panel, SettingRow, Stack, Stepper, TagInput, Text, TextArea, TextField } from '@aunoo/ui';
import { createBrand, setPrimaryBrand, setupBrandMonitoring, suggestKeywords } from '@monolith/brandWatcherApi';
import { errorText } from '../../../shell';

/*
 * First run, when a site has no brands yet (every new dedicated Brand Watcher site starts here), as
 * the old BrandWatcherOnboarding: the brand to protect, at least one competitor, then create each
 * brand, set the primary, and set up its monitoring topic and keyword group.
 */

interface WizardBrand { display_name: string; description: string; keywords: string[] }
const empty = (): WizardBrand => ({ display_name: '', description: '', keywords: [] });
const PRIMARY_COLOR = '#2563eb';
const COMPETITOR_COLORS = ['#9333ea', '#059669', '#d97706', '#dc2626', '#0891b2'];
const STEPS = [{ id: 'brand', label: 'Your brand' }, { id: 'competitors', label: 'Competitors' }, { id: 'review', label: 'Review and start' }];
const slug = (n: string) => n.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'brand';

export function Onboarding({ notify, onDone }: { notify: (m: string) => void; onDone: () => void }) {
  const [step, setStep] = useState(0);
  const [primary, setPrimary] = useState<WizardBrand>(empty);
  const [competitors, setCompetitors] = useState<WizardBrand[]>([empty()]);
  const [suggested, setSuggested] = useState<string[]>([]);
  const [suggesting, setSuggesting] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [progress, setProgress] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const valid = competitors.filter((c) => c.display_name.trim());
  const setComp = (i: number, patch: Partial<WizardBrand>) => setCompetitors((cs) => cs.map((c, k) => (k === i ? { ...c, ...patch } : c)));

  const suggest = async (which: 'primary' | number) => {
    const b = which === 'primary' ? primary : competitors[which];
    if (!b.display_name.trim()) return;
    setSuggesting(String(which));
    setError(null);
    try {
      const s = await suggestKeywords(b.display_name.trim(), b.description.trim() || undefined);
      const merged = [...new Set([...b.keywords, ...(s.brand_keywords ?? [])])];
      if (which === 'primary') {
        setPrimary((p) => ({ ...p, keywords: merged }));
        setSuggested((s.competitor_keywords ?? []).slice(0, 6));
      } else setComp(which, { keywords: merged });
    } catch (e) {
      setError(`No suggestions: ${errorText(e)}`);
    } finally {
      setSuggesting(null);
    }
  };

  const launch = async () => {
    setCreating(true);
    setError(null);
    setProgress([]);
    const note = (m: string) => setProgress((p) => [...p, m]);
    const mk = (b: WizardBrand, color: string) => ({
      name: slug(b.display_name), display_name: b.display_name.trim(), description: b.description.trim() || undefined,
      brand_keywords: b.keywords.length ? b.keywords : [b.display_name.trim()], color,
    });
    try {
      const p = await createBrand(mk(primary, PRIMARY_COLOR));
      note(`Created ${p.display_name}`);
      await setPrimaryBrand(p.id);
      note(`${p.display_name} is the primary brand`);
      await setupBrandMonitoring(p.id);
      note(`Collection set up for ${p.display_name}`);
      for (let i = 0; i < valid.length; i++) {
        const c = await createBrand(mk(valid[i], COMPETITOR_COLORS[i % COMPETITOR_COLORS.length]));
        note(`Created competitor ${c.display_name}`);
        await setupBrandMonitoring(c.id);
        note(`Collection set up for ${c.display_name}`);
      }
      notify('Brand Watcher is set up. Articles arrive on the next collection run.');
      onDone();
    } catch (e) {
      setError(`Setup stopped: ${errorText(e)}. Brands created so far are kept; finish in Brand settings.`);
      setCreating(false);
    }
  };

  return (
    <Panel
      title="Set up Brand Watcher"
      description="Name the brand to protect and who to compare it with. This creates the monitoring topics and keyword groups, and collection starts on its own."
    >
      <Stack gap="lg">
        <Stepper steps={STEPS} current={step} label="Brand Watcher setup progress" />

        {step === 0 && (
          <Stack gap="md">
            <TextField label="Brand name" value={primary.display_name} onChange={(display_name) => setPrimary({ ...primary, display_name })} placeholder="e.g. Acme Publishing" />
            <TextArea label="What does the company do? (optional, improves suggestions)" rows={2} value={primary.description} onChange={(description) => setPrimary({ ...primary, description })} />
            <TagInput label="Monitoring keywords" tags={primary.keywords} onChange={(keywords) => setPrimary({ ...primary, keywords })} hint="Names the news would use: legal name, abbreviations, ticker. The brand name is always included." />
            <div>
              <Button variant="secondary" iconStart={<Icon name="Sparkle" size="sm" />} disabled={!primary.display_name.trim() || suggesting !== null} onClick={() => void suggest('primary')}>
                {suggesting === 'primary' ? 'Suggesting…' : 'Suggest keywords and competitors'}
              </Button>
            </div>
          </Stack>
        )}

        {step === 1 && (
          <Stack gap="md">
            <Text>At least one competitor is needed: the benchmarks, share of voice and comparison views compare against it.</Text>
            {suggested.length > 0 && (
              <Stack direction="row" gap="sm">
                <Text variant="label" as="span">Suggested:</Text>
                {suggested.map((name) => (
                  <Chip
                    key={name}
                    tone="neutral"
                    icon={<Icon name="Plus" size="sm" />}
                    label={`Add ${name}`}
                    onClick={() => {
                      if (competitors.some((c) => c.display_name === name)) return;
                      const blank = competitors.findIndex((c) => !c.display_name.trim());
                      if (blank >= 0) setComp(blank, { display_name: name });
                      else setCompetitors((cs) => [...cs, { ...empty(), display_name: name }]);
                    }}
                  >
                    {name}
                  </Chip>
                ))}
              </Stack>
            )}
            {competitors.map((c, i) => (
              <Stack key={i} gap="sm">
                <Stack direction="row" gap="sm" wrap={false}>
                  <TextField label={`Competitor ${i + 1}`} value={c.display_name} onChange={(display_name) => setComp(i, { display_name })} />
                  <IconButton icon={<Icon name="Sparkle" size="sm" />} label={`Suggest keywords for competitor ${i + 1}`} disabled={!c.display_name.trim() || suggesting !== null} onClick={() => void suggest(i)} />
                  {competitors.length > 1 && <IconButton icon={<Icon name="X" size="sm" />} label={`Remove competitor ${i + 1}`} onClick={() => setCompetitors((cs) => cs.filter((_, k) => k !== i))} />}
                </Stack>
                {c.display_name.trim() && <TagInput label={`Keywords for ${c.display_name}`} tags={c.keywords} onChange={(keywords) => setComp(i, { keywords })} />}
              </Stack>
            ))}
            <div><Button variant="ghost" iconStart={<Icon name="Plus" size="sm" />} onClick={() => setCompetitors((cs) => [...cs, empty()])}>Add another competitor</Button></div>
          </Stack>
        )}

        {step === 2 && (
          <Stack gap="md">
            <Stack as="ul" gap="sm" label="Brands to create">
              <li><SettingRow title={`${primary.display_name} (primary brand)`} description={(primary.keywords.length ? primary.keywords : [primary.display_name]).join(', ')} /></li>
              {valid.map((c, i) => (
                <li key={i}><SettingRow title={`${c.display_name} (competitor)`} description={(c.keywords.length ? c.keywords : [c.display_name]).join(', ')} /></li>
              ))}
            </Stack>
            <Text variant="caption">Each brand gets a “Brand Monitoring” topic and a news keyword group. Collection starts on the next run and the dashboard fills as articles arrive. You can change all of this later in Brand settings.</Text>
            {progress.length > 0 && (
              <Stack as="ul" gap="sm" label="Progress">
                {progress.map((m, i) => <ActivityRow key={i} as="li" primary={m} dotTone="live" />)}
              </Stack>
            )}
          </Stack>
        )}

        {error && <Banner tone="error" title="Something went wrong" description={error} />}

        <Stack direction="row" justify="between" gap="sm">
          <Button variant="secondary" iconStart={<Icon name="CaretLeft" size="sm" />} disabled={step === 0 || creating} onClick={() => setStep((s) => s - 1)}>Back</Button>
          {step < 2 ? (
            <Button iconEnd={<Icon name="CaretRight" size="sm" />} disabled={step === 0 ? !primary.display_name.trim() : valid.length < 1} onClick={() => setStep((s) => s + 1)}>Next</Button>
          ) : (
            <Button iconStart={<Icon name="Target" size="sm" />} disabled={creating} onClick={() => void launch()}>{creating ? 'Setting up…' : 'Start monitoring'}</Button>
          )}
        </Stack>
      </Stack>
    </Panel>
  );
}
