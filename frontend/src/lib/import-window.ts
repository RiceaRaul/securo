import { addDays, format, parseISO } from 'date-fns'
import type { ImportWindow } from '@/types'

export const DEFAULT_IMPORT_WINDOW: ImportWindow = { mode: 'full', inclusive: true }

// Most banks cap the history they hand out at about this many days.
const DEFAULT_HISTORY_DAYS = 90

const toIso = (date: Date) => format(date, 'yyyy-MM-dd')

export function todayIso(): string {
  return toIso(new Date())
}

function shiftIso(iso: string, days: number): string {
  return toIso(addDays(parseISO(iso), days))
}

export function isImportWindowValid(window: ImportWindow): boolean {
  return window.mode !== 'from_date' || Boolean(window.date)
}

/** What the connect request carries. Full history is the server default, so it sends nothing. */
export function importWindowPayload(window: ImportWindow): ImportWindow | undefined {
  if (window.mode === 'full') return undefined
  if (window.mode === 'fresh') return { mode: 'fresh' }
  return { mode: 'from_date', date: window.date, inclusive: window.inclusive ?? true }
}

export interface ImportWindowPreview {
  /** First day whose transactions are imported. */
  start: string
  /** Day the opening balance lands on. */
  opening: string
  isFuture: boolean
  /** Set when the start is older than the history the bank provides. */
  bankLimitDays: number | null
}

/** Mirrors how the server resolves a "from date" window, for the summary under the picker. */
export function previewImportWindow(
  window: ImportWindow,
  maxHistoryDays?: number | null,
  today: string = todayIso(),
): ImportWindowPreview | null {
  if (window.mode !== 'from_date' || !window.date) return null
  const start = (window.inclusive ?? true) ? window.date : shiftIso(window.date, 1)
  const dayBefore = shiftIso(start, -1)
  const historyDays = maxHistoryDays || DEFAULT_HISTORY_DAYS
  return {
    start,
    opening: dayBefore < today ? dayBefore : today,
    isFuture: start > today,
    bankLimitDays: start < shiftIso(today, -(historyDays - 1)) ? historyDays : null,
  }
}
