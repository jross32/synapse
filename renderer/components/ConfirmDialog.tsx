// Confirm-before-destructive dialog (Contract #12). Shows exactly what will
// happen -- structured detail, not a generic "are you sure?".

import { Button } from './ui/button';
import { Modal } from './ui/modal';

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  body: React.ReactNode;
  confirmLabel: string;
  danger?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  danger,
  error,
  onConfirm,
  onCancel,
}: ConfirmDialogProps): JSX.Element | null {
  return (
    <Modal open={open} onClose={onCancel} labelledBy='confirm-title' className='max-w-md'>
      <h2 id='confirm-title' className='text-lg font-semibold'>
        {title}
      </h2>
      <div className='space-y-2 text-sm text-muted-foreground'>{body}</div>
      {error && (
        <p role='alert' className='text-sm text-destructive'>
          {error}
        </p>
      )}
      <div className='flex justify-end gap-2'>
        <Button variant='outline' onClick={onCancel}>
          Cancel
        </Button>
        <Button variant={danger ? 'destructive' : 'default'} onClick={onConfirm}>
          {confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}
