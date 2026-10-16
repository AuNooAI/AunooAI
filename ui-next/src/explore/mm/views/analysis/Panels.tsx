import { useEffect, useState } from 'react';
import { Banner, Skeleton } from '@aunoo/ui';
import { getAnalyses, getChannelMix, type ChannelMix, type MarketAnalyses } from '@monolith/marketMonitorApi';
import { errorText } from '../../../../shell';
import type { MmContext } from '../../context';
import { ConfidenceGate, type ThinPanel } from '../../shared/ConfidenceGate';
import { Formation } from './panels/Formation';
import { Funding } from './panels/Funding';
import { Hiring } from './panels/Hiring';
import { SignalNoise } from './panels/SignalNoise';
import { Themes } from './panels/Themes';
import { Voice } from './panels/Voice';

/*
 * The Analysis view's cross-sectional reads, as the old MarketAnalysisView: formation, what posts
 * contain, share of voice, funding, hiring and themes. The period applies only where a window means
 * something (posts, hiring, share of voice, channel mix); founding years and funding describe the
 * market as it stands.
 */
export function Panels(ctx: MmContext) {
  const [data, setData] = useState<MarketAnalyses | null>(null);
  const [mix, setMix] = useState<ChannelMix | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setData(null);
    setError(null);
    getAnalyses(ctx.marketId, ctx.periodDays).then((d) => live && setData(d), (e) => live && setError(errorText(e)));
    getChannelMix(ctx.marketId, ctx.periodDays).then((m) => live && setMix(m), () => live && setMix(null));
    return () => {
      live = false;
    };
  }, [ctx.marketId, ctx.periodDays]);

  if (error) return <Banner tone="error" title="The analysis didn’t load" description={error} />;
  if (!data) return <Skeleton variant="block" size="card" />;

  // A confirmed zero is shown in its panel. The middle case, some data but too little for a
  // percentage or an overlap to mean anything, folds into the shared "not enough data" list.
  const sov = data.share_of_voice;
  const fu = data.funding;
  const sovThin = !!sov && !sov.error && sov.earned_total > 0 && !sov.earned_share_reliable;
  const investorsThin = !!fu && !fu.error && fu.shared_investors.length > 0 && fu.shared_investors.length < 2;
  const thin: ThinPanel[] = [];
  if (sovThin) {
    thin.push({
      id: 'share-of-voice',
      title: 'Share of voice',
      why: 'The share of what other people said about each vendor.',
      need: `${sov!.earned_total} of the ${sov!.min_earned_for_share} mentions by others needed`,
    });
  }
  if (investorsThin) {
    thin.push({ id: 'investor-overlap', title: 'Investors backing more than one vendor', why: 'Investors with more than one tracked vendor in their portfolio.', need: fu!.coverage.label });
  }
  const failed = Object.entries(data).filter(([, v]) => v && (v as { error?: string }).error).map(([k]) => k.replace(/_/g, ' '));

  return (
    <>
      {failed.length > 0 && <Banner tone="warning" title="Some analyses failed" description={`Not shown: ${failed.join(', ')}. The rest loaded.`} />}
      <Formation ctx={ctx} data={data} />
      <SignalNoise ctx={ctx} data={data} />
      <Voice ctx={ctx} data={data} mix={mix} sovThin={sovThin} />
      <Funding ctx={ctx} data={data} investorsThin={investorsThin} />
      <ConfidenceGate panels={thin} />
      <Hiring ctx={ctx} data={data} />
      <Themes ctx={ctx} />
    </>
  );
}
