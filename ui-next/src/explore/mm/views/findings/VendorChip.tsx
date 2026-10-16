import { Chip } from '@aunoo/ui';
import { VendorSwatch } from '../../shared/colours';

/** A tracked vendor named on a row; pressing it opens the vendor's page. Used by Findings and Pulse. */
export function VendorChip({ id, name, color, onOpen }: { id: number; name: string; color?: string; onOpen: (id: number) => void }) {
  return (
    <Chip size="sm" tone="info" variant="outline" label={`Open ${name}`} onClick={() => onOpen(id)}>
      <VendorSwatch color={color} />
      {name}
    </Chip>
  );
}
