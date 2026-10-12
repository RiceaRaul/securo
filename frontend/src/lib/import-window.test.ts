import { describe, expect, it } from 'vitest'
import { importWindowPayload, isImportWindowValid, previewImportWindow } from './import-window'

describe('importWindowPayload', () => {
  it('sends nothing for full history', () => {
    expect(importWindowPayload({ mode: 'full', date: '2026-10-15' })).toBeUndefined()
  })

  it('drops the date for a fresh start', () => {
    expect(importWindowPayload({ mode: 'fresh', date: '2026-10-15' })).toEqual({ mode: 'fresh' })
  })

  it('carries the date and operator for a from-date window', () => {
    expect(importWindowPayload({ mode: 'from_date', date: '2026-10-15', inclusive: false })).toEqual({
      mode: 'from_date',
      date: '2026-10-15',
      inclusive: false,
    })
  })
})

describe('isImportWindowValid', () => {
  it('requires a date only for the from-date mode', () => {
    expect(isImportWindowValid({ mode: 'full' })).toBe(true)
    expect(isImportWindowValid({ mode: 'fresh' })).toBe(true)
    expect(isImportWindowValid({ mode: 'from_date' })).toBe(false)
    expect(isImportWindowValid({ mode: 'from_date', date: '2026-10-15' })).toBe(true)
  })
})

describe('previewImportWindow', () => {
  const today = '2026-10-20'

  it('has nothing to preview outside the from-date mode', () => {
    expect(previewImportWindow({ mode: 'full' }, null, today)).toBeNull()
    expect(previewImportWindow({ mode: 'fresh' }, null, today)).toBeNull()
  })

  it('starts on the date itself when inclusive', () => {
    expect(previewImportWindow({ mode: 'from_date', date: '2026-10-15', inclusive: true }, null, today)).toEqual({
      start: '2026-10-15',
      opening: '2026-10-14',
      isFuture: false,
      bankLimitDays: null,
    })
  })

  it('starts the day after when exclusive', () => {
    const preview = previewImportWindow({ mode: 'from_date', date: '2026-10-15', inclusive: false }, null, today)
    expect(preview).toMatchObject({ start: '2026-10-16', opening: '2026-10-15' })
  })

  it('keeps the opening balance on today for a future start', () => {
    const preview = previewImportWindow({ mode: 'from_date', date: '2026-10-25' }, null, today)
    expect(preview).toMatchObject({ start: '2026-10-25', opening: today, isFuture: true })
  })

  it('flags a start older than the history the bank provides', () => {
    expect(previewImportWindow({ mode: 'from_date', date: '2026-01-01' }, null, today)?.bankLimitDays).toBe(90)
    expect(previewImportWindow({ mode: 'from_date', date: '2026-09-01' }, 30, today)?.bankLimitDays).toBe(30)
    expect(previewImportWindow({ mode: 'from_date', date: '2026-09-25' }, 30, today)?.bankLimitDays).toBeNull()
  })
})
