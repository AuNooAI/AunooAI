import { useEffect, useState } from 'react';
import {
  Button, Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, Dialog, EmptyState, Grid, Icon, IconButton,
  Select, SettingRow, Stack, TextField,
} from '@aunoo/ui';
import type { KeywordGroup } from '../model';
import { plural } from '../lib';
import type { Confirm } from '@aunoo/shell';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  groups: KeywordGroup[];
  /** Topic names from /api/topics */
  topics: string[];
  onCreateGroup: (name: string, topic: string) => void;
  onAddKeyword: (groupId: string, text: string) => void;
  onRemoveKeyword: (groupId: string, keywordId: string) => void;
  onDeleteGroup: (groupId: string) => void;
  askConfirm: (confirm: Confirm) => void;
}

function GroupRow({ group, onAddKeyword, onRemoveKeyword, onDeleteGroup, askConfirm }: { group: KeywordGroup } & Pick<Props, 'onAddKeyword' | 'onRemoveKeyword' | 'onDeleteGroup' | 'askConfirm'>) {
  const [draft, setDraft] = useState('');
  const add = () => {
    if (!draft.trim()) return;
    onAddKeyword(group.id, draft.trim());
    setDraft('');
  };
  return (
    <Collapsible>
      <SettingRow
        title={group.name}
        description={`${group.topic} · ${plural(group.keywords.length, 'keyword')}`}
        actionsPlacement="title"
        actions={
          <>
            <CollapsibleTrigger variant="onSurface" size="sm">Keywords</CollapsibleTrigger>
            <IconButton
              icon={<Icon name="Trash" size="sm" />}
              label={`Delete ${group.name}`}
              tone="danger"
              onClick={() =>
                askConfirm({
                  title: 'Delete keyword group?',
                  message: `“${group.name}” and its ${plural(group.keywords.length, 'keyword')} will stop collecting. Articles already collected are kept.`,
                  action: 'Delete group',
                  onConfirm: () => onDeleteGroup(group.id),
                })
              }
            />
          </>
        }
      >
        <CollapsibleContent>
          <Stack gap="md">
            <TextField
              label={`Add keyword to ${group.name}`}
              hideLabel
              placeholder="Enter keyword..."
              value={draft}
              onChange={setDraft}
              onSubmit={add}
              action={
                <Button size="lg" variant="onSurface" iconStart={<Icon name="Plus" size="sm" />} disabled={!draft.trim()} onClick={add}>
                  Add
                </Button>
              }
            />
            {/* Bug 8: remove is always visible and asks first */}
            <Stack as="ul" direction="row" gap="sm" label={`${group.name} keywords`}>
              {group.keywords.map((k) => (
                <li key={k.id}>
                  <Stack direction="row" gap="sm" wrap={false}>
                    <Chip size="sm" tone="neutral">{k.text}</Chip>
                    <IconButton
                      icon={<Icon name="X" size="sm" />}
                      label={`Remove ${k.text}`}
                      tone="danger"
                      onClick={() =>
                        askConfirm({
                          title: 'Remove keyword?',
                          message: `“${k.text}” will no longer be collected for ${group.name}.`,
                          action: 'Remove keyword',
                          onConfirm: () => onRemoveKeyword(group.id, k.id),
                        })
                      }
                    />
                  </Stack>
                </li>
              ))}
            </Stack>
          </Stack>
        </CollapsibleContent>
      </SettingRow>
    </Collapsible>
  );
}

/** Manage Keywords: create groups, add/remove keywords, delete groups. */
export function ManageKeywordsDialog({ open, onOpenChange, groups, topics, onCreateGroup, ...rowProps }: Props) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [topic, setTopic] = useState('');
  useEffect(() => {
    if (open) {
      setCreating(false);
      setName('');
      setTopic('');
    }
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Manage Keywords" description="Create and manage keyword groups for article collection" size="lg">
      <Stack gap="md">
        {creating ? (
          <SettingRow title="New Keyword Group" actionsPlacement="title">
            <Stack gap="md">
              <Grid columns={2} stackAt="small" gap="md">
                <TextField label="Group Name" placeholder="e.g., AI Industry Leaders" value={name} onChange={setName} />
                <Select label="Topic" fullWidth placeholder="Select topic..." options={topics.map((t) => ({ value: t, label: t }))} value={topic} onValueChange={setTopic} />
              </Grid>
              <Stack direction="row" justify="end" gap="sm">
                <Button variant="onSurface" onClick={() => setCreating(false)}>Cancel</Button>
                <Button
                  iconStart={<Icon name="Plus" size="sm" />}
                  disabled={!name.trim() || !topic}
                  onClick={() => {
                    onCreateGroup(name.trim(), topic);
                    setCreating(false);
                    setName('');
                    setTopic('');
                  }}
                >
                  Create Group
                </Button>
              </Stack>
            </Stack>
          </SettingRow>
        ) : (
          <Button fullWidth size="lg" iconStart={<Icon name="Plus" size="sm" />} onClick={() => setCreating(true)}>
            New Keyword Group
          </Button>
        )}
        {groups.length === 0 ? (
          <EmptyState icon="ListBullets" title="No keyword groups">Create a group to start collecting articles.</EmptyState>
        ) : (
          <Stack as="ul" gap="sm" label="Keyword groups">
            {groups.map((g) => (
              <li key={g.id}>
                <GroupRow group={g} {...rowProps} />
              </li>
            ))}
          </Stack>
        )}
      </Stack>
    </Dialog>
  );
}
