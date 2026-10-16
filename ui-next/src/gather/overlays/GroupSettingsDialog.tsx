import { useEffect, useState } from 'react';
import { Banner, Button, Dialog, DialogClose, Icon, type SelectOption, Skeleton, Stack, Switch, Text } from '@aunoo/ui';
import { getGroupSettings, updateGroupSettings, type AvailableProvider, type GroupSettingsUpdateRequest } from '@monolith/gatherApi';
import { errorText } from '../../shell';
import { groupCollectSettings, groupSettingsPatch, type CollectSettings, type KeywordGroup } from '../model';
import { stamp } from '../lib';
import { SettingsSections, settingsErrors } from './SettingsSections';

interface Props {
  group: KeywordGroup | null;
  onClose: () => void;
  global: CollectSettings;
  providers: AvailableProvider[];
  models: SelectOption[];
  /** Called after a successful save; the page reloads the groups. */
  onSaved: () => void;
}

type Load = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; nextAt: string | null };

/** Group Settings: loads the group's own settings (GET /group/{id}/settings) and saves only what differs from global. */
export function GroupSettingsDialog({ group, onClose, global, providers, models, onSaved }: Props) {
  const [load, setLoad] = useState<Load>({ state: 'loading' });
  const [useGlobal, setUseGlobal] = useState(true);
  const [active, setActive] = useState(true);
  const [initialActive, setInitialActive] = useState(true);
  const [draft, setDraft] = useState(global);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!group) return;
    let alive = true;
    setLoad({ state: 'loading' });
    setSaveError(null);
    getGroupSettings(Number(group.id)).then(
      (r) => {
        if (!alive) return;
        setUseGlobal((r.custom_fields ?? []).length === 0);
        setActive(r.is_active !== false);
        setInitialActive(r.is_active !== false);
        setDraft(groupCollectSettings(r.settings ?? {}, global));
        setLoad({ state: 'ready', nextAt: r.next_check_at ?? null });
      },
      (e) => alive && setLoad({ state: 'error', message: errorText(e) }),
    );
    return () => {
      alive = false;
    };
  }, [group?.id, global, attempt]);

  const errors = useGlobal ? {} : settingsErrors(draft, true);
  const valid = load.state === 'ready' && Object.keys(errors).length === 0;
  const next = load.state === 'ready' && load.nextAt ? stamp(new Date(load.nextAt)) : null;

  const save = async () => {
    if (!group) return;
    setSaving(true);
    setSaveError(null);
    try {
      const id = Number(group.id);
      if (useGlobal) {
        await updateGroupSettings(id, { use_global_settings: true });
        if (active !== initialActive) await updateGroupSettings(id, { is_active: active });
      } else {
        // null fields inherit from global (the facade writes NULL); the client's type doesn't allow null
        await updateGroupSettings(id, { is_active: active, ...groupSettingsPatch(draft, global) } as unknown as GroupSettingsUpdateRequest);
      }
      onSaved();
      onClose();
    } catch (e) {
      setSaveError(errorText(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog
      open={group !== null}
      onOpenChange={(open) => !open && onClose()}
      title={`Group Settings: ${group?.name ?? ''}`}
      description="Configure collection settings for this keyword group"
      footer={
        <>
          <Text as="span" variant="hint">{!active ? 'Collection paused' : next ? `Next scheduled check: ${next}` : ''}</Text>
          <DialogClose>
            <Button variant="secondary" size="lg">Cancel</Button>
          </DialogClose>
          <Button size="lg" disabled={!valid} busy={saving} onClick={save}>
            {saving ? 'Saving…' : 'Save Settings'}
          </Button>
        </>
      }
    >
      {load.state === 'loading' ? (
        <Skeleton variant="block" />
      ) : load.state === 'error' ? (
        <Banner
          tone="error"
          icon="WarningCircle"
          title="Couldn’t load the group’s settings"
          description={load.message}
          action={<Button variant="secondary" onClick={() => setAttempt((a) => a + 1)}>Retry</Button>}
        />
      ) : (
        <Stack gap="lg">
          {saveError && <Banner tone="error" icon="WarningCircle" title="Not saved" description={saveError} />}
          <Switch
            label={<><Icon name="Globe" size="sm" /> Use Global Settings</>}
            description="Inherit all settings from global auto-collect configuration"
            checked={useGlobal}
            onCheckedChange={setUseGlobal}
          />
          <Switch label="Active" description="Enable collection for this group" checked={active} onCheckedChange={setActive} />
          {!useGlobal && (
            <>
              <Stack direction="row" justify="end">
                <Button variant="ghost" size="sm" iconStart={<Icon name="ArrowClockwise" size="sm" />} onClick={() => setDraft({ ...global, socialPlatforms: null })}>
                  Reset to Global
                </Button>
              </Stack>
              <SettingsSections value={draft} onChange={setDraft} global={global} errors={errors} providers={providers} models={models} />
            </>
          )}
        </Stack>
      )}
    </Dialog>
  );
}
