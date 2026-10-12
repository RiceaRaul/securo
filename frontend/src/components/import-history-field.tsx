import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useDateLocale } from '@/hooks/use-display-locale'
import { DatePickerInput } from '@/components/ui/date-picker-input'
import { previewImportWindow, todayIso } from '@/lib/import-window'
import type { ImportWindow } from '@/types'

interface ImportHistoryFieldProps {
  value: ImportWindow
  onChange: (value: ImportWindow) => void
  /** History the chosen bank provides, when the connector reports it. */
  maxHistoryDays?: number | null
  disabled?: boolean
  /** Keeps input ids unique when more than one connect dialog is mounted. */
  idPrefix: string
}

export function ImportHistoryField({
  value,
  onChange,
  maxHistoryDays,
  disabled = false,
  idPrefix,
}: ImportHistoryFieldProps) {
  const { t } = useTranslation()
  const dateLocale = useDateLocale()
  const preview = previewImportWindow(value, maxHistoryDays)
  const formatDay = (iso: string) => new Date(iso + 'T00:00:00').toLocaleDateString(dateLocale)

  const option = (mode: ImportWindow['mode'], title: string, hint: string, extra?: ReactNode) => (
    <div className="p-3">
      <label htmlFor={`${idPrefix}-${mode}`} className="flex items-start gap-3 cursor-pointer">
        <input
          id={`${idPrefix}-${mode}`}
          type="radio"
          name={`${idPrefix}-import-history`}
          checked={value.mode === mode}
          disabled={disabled}
          onChange={() =>
            onChange({
              ...value,
              mode,
              // A date is required for this mode; start from today rather than empty.
              date: mode === 'from_date' ? value.date || todayIso() : value.date,
            })
          }
          className="mt-0.5 h-4 w-4 border-border text-primary focus:ring-primary"
        />
        <span className="space-y-1">
          <span className="block text-sm font-medium text-foreground">{title}</span>
          <span className="block text-xs text-muted-foreground">{hint}</span>
        </span>
      </label>
      {extra}
    </div>
  )

  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium text-foreground">{t('connections.importHistory')}</legend>
      <div className="rounded-lg border border-border divide-y divide-border">
        {option('full', t('connections.importHistoryFull'), t('connections.importHistoryFullHint'))}
        {option('fresh', t('connections.importHistoryFresh'), t('connections.importHistoryFreshHint'))}
        {option(
          'from_date',
          t('connections.importHistoryFromDate'),
          t('connections.importHistoryFromDateHint'),
          value.mode === 'from_date' && (
            <div className="mt-3 pl-7 space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <select
                  aria-label={t('connections.importHistoryFromDate')}
                  className="border border-border rounded-lg px-3 py-2 text-sm bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                  value={(value.inclusive ?? true) ? 'inclusive' : 'exclusive'}
                  disabled={disabled}
                  onChange={(e) => onChange({ ...value, inclusive: e.target.value === 'inclusive' })}
                >
                  <option value="inclusive">{t('connections.importHistoryOnOrAfter')}</option>
                  <option value="exclusive">{t('connections.importHistoryAfter')}</option>
                </select>
                <DatePickerInput
                  value={value.date ?? ''}
                  onChange={(date) => onChange({ ...value, date })}
                  disabled={disabled}
                />
              </div>
              {preview && (
                <p className="text-xs text-muted-foreground">
                  {t('connections.importHistorySummary', {
                    date: formatDay(preview.start),
                    openingDate: formatDay(preview.opening),
                  })}
                  {preview.isFuture && ` ${t('connections.importHistoryFutureHint')}`}
                </p>
              )}
              {preview?.bankLimitDays && (
                <p className="text-xs text-amber-600 dark:text-amber-500">
                  {t('connections.importHistoryBankLimit', { days: preview.bankLimitDays })}
                </p>
              )}
            </div>
          ),
        )}
      </div>
    </fieldset>
  )
}
