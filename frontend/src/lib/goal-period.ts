const parse = (iso: string) => new Date(iso + 'T00:00:00')

/** "November 2026": the month a recurring goal's period starts in. */
export function goalPeriodMonth(periodStart: string, locale: string): string {
  return parse(periodStart).toLocaleDateString(locale, { month: 'long', year: 'numeric' })
}

/** "10 Oct 2026 – 9 Nov 2026" */
export function goalPeriodRange(periodStart: string, periodEnd: string, locale: string): string {
  const format = (iso: string) =>
    parse(iso).toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' })
  return `${format(periodStart)} – ${format(periodEnd)}`
}
