import { Button, Dialog, DialogClose, Text } from '@aunoo/ui';

export interface Confirm {
  title: string;
  /** What happens, e.g. "Articles already collected are kept." */
  message: React.ReactNode;
  /** Label of the destructive button, e.g. "Delete feed". */
  action: string;
  onConfirm: () => void;
}

export interface ConfirmDialogProps {
  /** What is about to happen; `null` = closed. */
  confirm: Confirm | null;
  onClose: () => void;
}

/** One confirmation for every destructive action (Remove, Reset, Clear, Revoke…). */
export function ConfirmDialog({ confirm, onClose }: ConfirmDialogProps) {
  return (
    <Dialog
      open={confirm !== null}
      onOpenChange={(open) => !open && onClose()}
      title={confirm?.title ?? ''}
      footer={
        <>
          <DialogClose>
            <Button variant="secondary" size="lg">Cancel</Button>
          </DialogClose>
          <Button
            variant="danger"
            size="lg"
            onClick={() => {
              confirm?.onConfirm();
              onClose();
            }}
          >
            {confirm?.action ?? 'Delete'}
          </Button>
        </>
      }
    >
      <Text variant="description">{confirm?.message}</Text>
    </Dialog>
  );
}
