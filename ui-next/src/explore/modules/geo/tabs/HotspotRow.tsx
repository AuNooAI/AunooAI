import { Chip, Stack, Text } from '@aunoo/ui';
import type { HotspotSummary } from '@monolith/geopoliticalHotspotsApi';
import { RISK_LABEL, RISK_TONE, TREND_LABEL } from '../labels';
import '../geo.css';

/** One hotspot in a ranked list: name (a button when it can open its articles), risk, trend, articles, intensity */
export function HotspotRow({ rank, hotspot: h, onOpen }: { rank?: number; hotspot: HotspotSummary; onOpen?: () => void }) {
  const name = `${rank ? `${rank}. ` : ''}${h.location_name}`;
  return (
    <Stack gap="sm">
      <Stack direction="row" justify="between" gap="sm">
        {onOpen ? (
          <button type="button" className="text-link geo-linkbutton" onClick={onOpen} aria-label={`${name}: show its articles`}>{name}</button>
        ) : <Text as="span" variant="label">{name}</Text>}
        <Text as="span" variant="caption">{`intensity ${Math.round(h.intensity_score)}`}</Text>
      </Stack>
      <Stack direction="row" gap="sm">
        <Chip size="sm" tone={RISK_TONE[h.risk_level]}>{`${RISK_LABEL[h.risk_level]} risk`}</Chip>
        {h.trend && <Chip size="sm" tone={h.trend === 'escalating' ? 'error' : h.trend === 'de-escalating' ? 'success' : 'muted'}>{TREND_LABEL[h.trend]}</Chip>}
        <Text as="span" variant="caption">{[h.country_name !== h.location_name ? h.country_name : null, `${h.article_count} articles`].filter(Boolean).join(' · ')}</Text>
      </Stack>
    </Stack>
  );
}
