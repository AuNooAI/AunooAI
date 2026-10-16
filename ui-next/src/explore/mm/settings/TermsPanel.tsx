import { useEffect, useState } from 'react';
import { Banner, Button, Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, Icon, Panel, SegmentedControl, Skeleton, Stack, Text, TextArea } from '@aunoo/ui';
import {
  ALL_IN_SCOPE, getCollectionPlan, setCollectionTerms, setupCollection, setVendorCollection,
  type CollectionPlan, type VendorFilter, type VendorSwitch,
} from '@monolith/marketMonitorApi';
import { errorText } from '../../../shell';
import type { MmContext } from '../context';

type VendorMode = 'none' | 'funded' | 'all';
type Msg = { tone: 'success' | 'error' | 'warning'; text: string } | null;

/**
 * What the market collects (its search terms, vendor names and keyword group) and which vendors are
 * collected for or shown in Brand Watcher, as the old "Search terms" settings tab. The plan is a
 * preview computed by the server; nothing changes until a save or set-up button is pressed.
 */
export function TermsPanel({ ctx }: { ctx: MmContext }) {
  const { marketId } = ctx;
  const [mode, setMode] = useState<VendorMode>('funded');
  const [plan, setPlan] = useState<CollectionPlan | null>(null);
  const [terms, setTerms] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<Msg>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let live = true;
    getCollectionPlan(marketId, mode).then(
      (p) => {
        if (!live) return;
        setPlan(p);
        setTerms(p.market_terms.join('\n'));
      },
      (e) => live && setMsg({ tone: 'error', text: errorText(e) }),
    );
    return () => {
      live = false;
    };
  }, [marketId, mode, nonce]);

  const run = async (work: () => Promise<string>) => {
    setBusy(true);
    setMsg(null);
    try {
      setMsg({ tone: 'success', text: await work() });
      setNonce((n) => n + 1);
      ctx.reload();
    } catch (e) {
      setMsg({ tone: 'error', text: `Failed: ${errorText(e)}` });
    } finally {
      setBusy(false);
    }
  };

  const saveTerms = () => void run(async () => {
    const list = terms.split('\n').map((s) => s.trim()).filter(Boolean);
    const r = await setCollectionTerms(marketId, list);
    return r.truncated?.length
      ? `${list.length} saved, but ${r.truncated.length} are over 30 characters and will be searched as: ${r.truncated.map((x) => `“${x.searched_as}”`).join(', ')}`
      : `${list.length} collection terms saved.`;
  });

  const live = Boolean(plan?.existing);
  const setup = () => ctx.askConfirm({
    title: live ? 'Update the keyword group?' : 'Create the keyword group?',
    message: `This writes ${plan?.keywords.length ?? 0} search terms to the keyword group “${plan?.group_name}”. Collection picks them up on its next run, and paid news sources are charged for what they return.`,
    action: live ? 'Update keyword group' : 'Create keyword group',
    onConfirm: () => void run(async () => {
      const r = await setupCollection(marketId, { qualifier: plan?.qualifier ?? 'security', vendorNames: mode, dryRun: false });
      if (r.error) throw new Error(r.error);
      return `Keyword group ${r.group_created ? 'created' : 'updated'} with ${r.keywords_written ?? 0} keywords.`;
    }),
  });

  const toggle = (label: string, filter: VendorFilter, enabled: boolean, field: VendorSwitch, cost: string) => ctx.askConfirm({
    title: `${label}?`,
    message: cost,
    action: label,
    onConfirm: () => void run(async () => {
      const r = await setVendorCollection(marketId, enabled, filter, false, field);
      const what = field === 'collection' ? 'collection' : 'brand monitoring';
      return `${r.changed ?? 0} vendors updated (${what}).${r.keywords_rewritten ? ` ${r.keywords_rewritten} keyword list${r.keywords_rewritten === 1 ? '' : 's'} rewritten to avoid matching ordinary words.` : ''}`;
    }),
  });
  const ON_COST = 'Collection for these vendors starts on the next run. Their websites and LinkedIn pages are read through paid sources, which are charged per record.';
  const OFF_COST = 'Collection stops for these vendors. Everything already collected is kept.';
  const BM_ON = 'These vendors also appear in Brand Watcher as brands of their own. Keywords that are ordinary words are rewritten (so “Variance” is searched as “Variance security”).';
  const BM_OFF = 'These vendors are removed from Brand Watcher’s brand list. Articles already collected are kept.';

  if (!plan) return msg ? <Banner tone="error" title="The collection plan didn’t load" description={msg.text} /> : <Skeleton variant="block" size="card" />;

  return (
    <>
      <Panel title="What this market collects" description="Search terms for the category. Vendor names are added separately below.">
        <Stack gap="md">
          <TextArea label="Collection terms, one per line" rows={8} mono value={terms} onChange={setTerms} placeholder={'SOC automation\nautonomous SOC\nAI SOC analyst'} hint={`${plan.market_terms.length} saved · 30 characters at most`} />
          {plan.truncated && plan.truncated.length > 0 && (
            <Banner
              tone="warning"
              title={`${plan.truncated.length} term${plan.truncated.length === 1 ? ' is' : 's are'} over 30 characters`}
              description={`These will be searched as the shorter, broader form: ${plan.truncated.map((x) => `“${x.term}” as “${x.searched_as}”`).join('; ')}.`}
            />
          )}
          <div><Button variant="secondary" disabled={busy} onClick={saveTerms}>Save terms</Button></div>

          <SegmentedControl
            label="Also search vendors by name"
            options={[
              { value: 'none', label: 'None' },
              { value: 'funded', label: `Funded (${plan.funded_vendors ?? 0})` },
              { value: 'all', label: `All (${plan.vendors})` },
            ]}
            value={mode}
            onValueChange={(v) => setMode(v as VendorMode)}
          />
          <Text variant="caption">{`None searches market language only; Funded adds vendors with a disclosed raise; All adds every active vendor. Short or ambiguous names get “${plan.qualifier}” added to cut false matches. This changes the preview below; Update keyword group saves it.`}</Text>
          {plan.error && <Banner tone="warning" title="The plan has a problem" description={plan.error} />}

          <Stack gap="sm">
            <Text variant="caption">{`Keyword group: ${plan.group_name}`}</Text>
            <Text variant="caption">{`Topic: ${plan.topic_name}`}</Text>
            <Text variant="caption">{`${plan.keywords.length} search terms in total`}</Text>
          </Stack>
          {plan.keywords.length > 0 && (
            <Collapsible>
              <CollapsibleTrigger variant="ghost" size="sm">Show the full search list</CollapsibleTrigger>
              <CollapsibleContent>
                <Stack direction="row" gap="sm">
                  {plan.keywords.map((k) => <Chip key={k} size="sm" tone={plan.vendor_keywords.includes(k) ? 'muted' : 'neutral'}>{k}</Chip>)}
                </Stack>
              </CollapsibleContent>
            </Collapsible>
          )}
          <Stack direction="row" gap="sm">
            <Button iconStart={<Icon name="Play" size="sm" />} disabled={busy || !plan.keywords.length} onClick={setup}>{live ? 'Update keyword group' : 'Create keyword group'}</Button>
            {live && <Chip tone="success" icon={<Icon name="CheckCircle" size="sm" />}>Live</Chip>}
          </Stack>
        </Stack>
      </Panel>

      <Panel title="Vendor selection">
        <Stack gap="md">
          <Text variant="label">Collection</Text>
          <Text variant="caption">Whether we pay to watch a vendor’s website and LinkedIn. Vendors marked out of scope are never included unless a rule names their role.</Text>
          <Stack direction="row" gap="sm">
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => toggle('Collect for every vendor', ALL_IN_SCOPE, true, 'collection', ON_COST)}>Select all</Button>
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => toggle('Stop collecting for every vendor', ALL_IN_SCOPE, false, 'collection', OFF_COST)}>Remove all</Button>
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => toggle('Collect for funded vendors', { funding_status: ['Disclosed'] }, true, 'collection', ON_COST)}>Select funded</Button>
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => toggle('Stop collecting for unfunded vendors', { funding_status: ['Undisclosed', 'Bootstrapped'] }, false, 'collection', OFF_COST)}>Remove unfunded</Button>
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => toggle('Stop collecting for vendors with no LinkedIn page', { has_linkedin: false }, false, 'collection', OFF_COST)}>Remove those with no LinkedIn</Button>
          </Stack>
          <Text variant="label">Brand monitoring</Text>
          <Text variant="caption">Whether a vendor also appears in Brand Watcher as a brand of its own, with sentiment, alerts and its own dashboard. Separate from collection and off by default, because dozens of vendors would swamp a brand dashboard. Switching it on rewrites keywords that are ordinary words, so “Variance” is searched as “Variance security”.</Text>
          <Stack direction="row" gap="sm">
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => toggle('Show every vendor in Brand Watcher', ALL_IN_SCOPE, true, 'brand_monitoring', BM_ON)}>Select all</Button>
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => toggle('Remove every vendor from Brand Watcher', ALL_IN_SCOPE, false, 'brand_monitoring', BM_OFF)}>Remove all</Button>
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => toggle('Show funded vendors in Brand Watcher', { funding_status: ['Disclosed'] }, true, 'brand_monitoring', BM_ON)}>Select funded</Button>
          </Stack>
        </Stack>
      </Panel>
      {msg && <Banner tone={msg.tone} title={msg.tone === 'error' ? 'Something went wrong' : 'Done'} description={msg.text} />}
    </>
  );
}
