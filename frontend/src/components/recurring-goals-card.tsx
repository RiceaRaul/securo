import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { History, Pencil, Trash2, Check, X } from 'lucide-react'
import { goals as goalsApi, recurringGoals as recurringGoalsApi } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { GoalStatusBadge } from '@/components/goal-status-badge'
import { useDateLocale, useDisplayLocale } from '@/hooks/use-display-locale'
import { usePrivacyMode } from '@/hooks/use-privacy-mode'
import { formatCurrency } from '@/lib/format'
import { goalPeriodRange } from '@/lib/goal-period'
import type { Goal, RecurringGoal } from '@/types'

const SELECT_CLASS = 'w-full border border-border rounded-lg px-3 py-2 text-sm bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-primary'
const ICON_BUTTON = 'p-1.5 rounded-md text-muted-foreground transition-colors'

export const START_DAYS = Array.from({ length: 31 }, (_, i) => i + 1)

/** One past period, with its saved amount editable in place. */
function HistoryRow({ goal, canWrite }: { goal: Goal; canWrite: boolean }) {
  const { t } = useTranslation()
  const { mask } = usePrivacyMode()
  const locale = useDisplayLocale()
  const dateLocale = useDateLocale()
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<string | null>(null)

  const save = useMutation({
    mutationFn: (amount: number) => goalsApi.update(goal.id, { current_amount: amount }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals'] })
      queryClient.invalidateQueries({ queryKey: ['recurring-goals'] })
      setDraft(null)
      toast.success(t('goals.updated'))
    },
    onError: () => toast.error(t('common.error')),
  })

  return (
    <div className="flex items-center gap-3 py-2.5">
      <div className="flex-1 min-w-0">
        <p className="text-sm text-foreground truncate">
          {goal.period_start && goal.period_end
            ? goalPeriodRange(goal.period_start, goal.period_end, dateLocale)
            : goal.name}
        </p>
        {draft === null ? (
          <p className="text-xs text-muted-foreground tabular-nums">
            {mask(formatCurrency(goal.current_amount, goal.currency, locale))}
            {' / '}
            {mask(formatCurrency(goal.target_amount, goal.currency, locale))}
          </p>
        ) : (
          <form
            className="mt-1 flex items-center gap-1"
            onSubmit={(e) => {
              e.preventDefault()
              const amount = parseFloat(draft)
              if (!Number.isNaN(amount)) save.mutate(amount)
            }}
          >
            <Input
              type="number"
              step="0.01"
              min="0"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              aria-label={t('goals.currentAmount')}
              className="h-8 w-32"
              autoFocus
            />
            <button type="submit" className={`${ICON_BUTTON} hover:text-emerald-500`} title={t('common.save')} disabled={save.isPending}>
              <Check size={14} />
            </button>
            <button type="button" className={`${ICON_BUTTON} hover:text-foreground`} title={t('common.cancel')} onClick={() => setDraft(null)}>
              <X size={14} />
            </button>
          </form>
        )}
      </div>
      <GoalStatusBadge status={goal.status} t={t} />
      {canWrite && draft === null && (
        <button
          className={`${ICON_BUTTON} hover:text-primary hover:bg-primary/5`}
          title={t('common.edit')}
          onClick={() => setDraft(String(goal.current_amount))}
        >
          <Pencil size={13} />
        </button>
      )}
    </div>
  )
}

function HistoryDialog({ recurring, onClose, canWrite }: { recurring: RecurringGoal | null; onClose: () => void; canWrite: boolean }) {
  const { t } = useTranslation()
  const { data: periods } = useQuery({
    queryKey: ['goals', 'history', recurring?.id],
    queryFn: () => goalsApi.list(undefined, recurring!.id),
    enabled: !!recurring,
  })

  return (
    <Dialog open={!!recurring} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{recurring?.name} · {t('goals.history')}</DialogTitle>
        </DialogHeader>
        {periods && periods.length > 0 ? (
          <div className="divide-y divide-border max-h-[60vh] overflow-y-auto">
            {periods.map((goal) => (
              <HistoryRow key={goal.id} goal={goal} canWrite={canWrite} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground text-center py-8">{t('goals.historyEmpty')}</p>
        )}
      </DialogContent>
    </Dialog>
  )
}

export function RecurringGoalsCard({ canWrite }: { canWrite: boolean }) {
  const { t } = useTranslation()
  const { mask } = usePrivacyMode()
  const locale = useDisplayLocale()
  const queryClient = useQueryClient()
  const [historyOf, setHistoryOf] = useState<RecurringGoal | null>(null)
  const [editing, setEditing] = useState<RecurringGoal | null>(null)
  const [deleting, setDeleting] = useState<RecurringGoal | null>(null)
  const [deleteHistory, setDeleteHistory] = useState(false)

  const { data: recurringList } = useQuery({
    queryKey: ['recurring-goals'],
    queryFn: recurringGoalsApi.list,
  })

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['goals'] })
    queryClient.invalidateQueries({ queryKey: ['recurring-goals'] })
  }

  const updateMutation = useMutation({
    mutationFn: ({ id, ...data }: Partial<RecurringGoal> & { id: string }) => recurringGoalsApi.update(id, data),
    onSuccess: () => {
      refresh()
      setEditing(null)
      toast.success(t('goals.updated'))
    },
    onError: () => toast.error(t('common.error')),
  })

  const deleteMutation = useMutation({
    mutationFn: ({ id, withHistory }: { id: string; withHistory: boolean }) => recurringGoalsApi.delete(id, withHistory),
    onSuccess: () => {
      refresh()
      setDeleting(null)
      toast.success(t('goals.deleted'))
    },
    onError: () => toast.error(t('common.error')),
  })

  // Nothing to manage until the first recurring goal exists.
  if (!recurringList || recurringList.length === 0) return null

  return (
    <div className="mt-4 bg-card rounded-xl border border-border shadow-sm overflow-hidden">
      <div className="px-4 sm:px-5 py-4 border-b border-border">
        <p className="text-sm font-semibold text-foreground">{t('goals.recurringTitle')}</p>
      </div>
      <div className="divide-y divide-border">
        {recurringList.map((recurring) => (
          <div key={recurring.id} className="px-4 sm:px-5 py-3 flex items-center gap-3">
            <div className="flex-1 min-w-0">
              <p className={`text-sm font-semibold truncate ${recurring.is_active ? 'text-foreground' : 'text-muted-foreground'}`}>
                {recurring.name}
              </p>
              <p className="text-xs text-muted-foreground tabular-nums">
                {t('goals.recurringSummary', {
                  amount: mask(formatCurrency(recurring.target_amount, recurring.currency, locale)),
                  day: recurring.start_day,
                })}
                {recurring.periods_closed > 0 && (
                  <> · {t('goals.recurringScore', { met: recurring.periods_met, total: recurring.periods_closed })}</>
                )}
              </p>
            </div>
            {canWrite && (
              <Switch
                checked={recurring.is_active}
                onCheckedChange={(checked) => updateMutation.mutate({ id: recurring.id, is_active: checked })}
                disabled={updateMutation.isPending}
                aria-labelledby={`recurring-${recurring.id}`}
              />
            )}
            <span id={`recurring-${recurring.id}`} className="sr-only">
              {t('goals.repeatMonthly')}: {recurring.name}
            </span>
            <button
              className={`${ICON_BUTTON} hover:text-primary hover:bg-primary/5`}
              title={t('goals.history')}
              onClick={() => setHistoryOf(recurring)}
            >
              <History size={13} />
            </button>
            {canWrite && (
              <>
                <button
                  className={`${ICON_BUTTON} hover:text-primary hover:bg-primary/5`}
                  title={t('common.edit')}
                  onClick={() => setEditing(recurring)}
                >
                  <Pencil size={13} />
                </button>
                <button
                  className={`${ICON_BUTTON} hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-500/10`}
                  title={t('common.delete')}
                  onClick={() => { setDeleteHistory(false); setDeleting(recurring) }}
                >
                  <Trash2 size={13} />
                </button>
              </>
            )}
          </div>
        ))}
      </div>

      <HistoryDialog recurring={historyOf} onClose={() => setHistoryOf(null)} canWrite={canWrite} />

      <Dialog open={!!editing} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('goals.recurringEdit')}</DialogTitle>
          </DialogHeader>
          <form
            key={editing?.id}
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              if (!editing) return
              const form = new FormData(e.currentTarget)
              updateMutation.mutate({
                id: editing.id,
                name: form.get('name') as string,
                target_amount: parseFloat(form.get('target_amount') as string),
                start_day: Number(form.get('start_day')),
              })
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="recurring-name">{t('goals.name')}</Label>
              <Input id="recurring-name" name="name" defaultValue={editing?.name ?? ''} required />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="recurring-amount">{t('goals.targetAmount')}</Label>
                <Input
                  id="recurring-amount"
                  name="target_amount"
                  type="number"
                  step="0.01"
                  min="0.01"
                  defaultValue={editing?.target_amount?.toString() ?? ''}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="recurring-day">{t('goals.startDay')}</Label>
                <select id="recurring-day" name="start_day" defaultValue={editing?.start_day ?? 1} className={SELECT_CLASS}>
                  {START_DAYS.map((day) => (
                    <option key={day} value={day}>{day}</option>
                  ))}
                </select>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">{t('goals.recurringEditHint')}</p>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setEditing(null)}>{t('common.cancel')}</Button>
              <Button type="submit" disabled={updateMutation.isPending}>{t('common.save')}</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={!!deleting} onOpenChange={(open) => !open && setDeleting(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('goals.confirmDeleteTitle')}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">{t('goals.recurringDeleteDesc', { name: deleting?.name })}</p>
          <div className="flex items-center gap-2">
            <input
              id="recurring-delete-history"
              type="checkbox"
              checked={deleteHistory}
              onChange={(e) => setDeleteHistory(e.target.checked)}
              className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
            />
            <Label htmlFor="recurring-delete-history">{t('goals.recurringDeleteHistory')}</Label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleting(null)}>{t('common.cancel')}</Button>
            <Button
              variant="destructive"
              onClick={() => deleting && deleteMutation.mutate({ id: deleting.id, withHistory: deleteHistory })}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? t('common.loading') : t('common.delete')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
