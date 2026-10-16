import { Button, EmptyState, Icon, Panel } from '@aunoo/ui';
import type { ViewProps } from './types';

/** Tabs not rebuilt yet: send people to the same tab on the current page. */
export function NotRebuilt({ tab }: ViewProps) {
  return (
    <Panel title={tab.label}>
      <EmptyState
        icon={tab.icon}
        title="Not on the new page yet"
        action={
          <Button iconEnd={<Icon name="ArrowSquareOut" size="sm" />} onClick={() => window.location.assign('/trend-convergence')}>
            Open on the current Anticipate page
          </Button>
        }
      >
        This tab is being rebuilt. Until then it works as before on the current page.
      </EmptyState>
    </Panel>
  );
}
