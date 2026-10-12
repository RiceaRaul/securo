import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'

import GoalsPage from '@/pages/goals'
import { renderWithProviders } from '@/test/utils'

const api = vi.hoisted(() => ({
  goals: { list: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn() },
  recurringGoals: { list: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn() },
  accounts: { list: vi.fn() },
  assets: { list: vi.fn() },
  assetGroups: { list: vi.fn() },
  currencies: { list: vi.fn() },
}))

vi.mock('@/lib/api', () => api)

vi.mock('@/hooks/use-display-locale', () => ({
  useDisplayLocale: () => 'en-US',
  useDateLocale: () => 'en-US',
}))

vi.mock('@/contexts/auth-context', () => ({
  useAuth: () => ({ user: { preferences: { currency_display: 'EUR' } } }),
}))

vi.mock('@/contexts/workspace-context', () => ({
  useWorkspace: () => ({ canWrite: true }),
}))

vi.mock('@/hooks/use-privacy-mode', () => ({
  usePrivacyMode: () => ({ mask: (value: string) => value }),
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const goal = (over: Record<string, unknown>) => ({
  id: 'goal-1', user_id: 'user-1', name: 'Rent', target_amount: 500, current_amount: 300,
  currency: 'EUR', target_amount_primary: null, current_amount_primary: null,
  target_date: '2026-11-09', tracking_type: 'manual', account_id: null, asset_id: null,
  asset_group_id: null, status: 'active', icon: null, color: null, position: 0,
  metadata_json: null, recurring_goal_id: 'rec-1', period_start: '2026-10-10',
  period_end: '2026-11-09', created_at: '2026-10-10T00:00:00Z', updated_at: '2026-10-10T00:00:00Z',
  percentage: 60, monthly_contribution: null, on_track: null, account_name: null,
  asset_name: null, asset_group_name: null,
  ...over,
})

const recurring = {
  id: 'rec-1', name: 'Rent', target_amount: 500, currency: 'EUR', start_day: 10, icon: null,
  color: null, is_active: true, next_period_start: '2026-11-10', created_at: '', updated_at: '',
  current_goal_id: 'goal-1', periods_closed: 5, periods_met: 4,
}

beforeEach(() => {
  vi.resetAllMocks()
  api.goals.list.mockResolvedValue([goal({})])
  api.recurringGoals.list.mockResolvedValue([recurring])
  api.accounts.list.mockResolvedValue([])
  api.assets.list.mockResolvedValue([])
  api.assetGroups.list.mockResolvedValue([])
  api.currencies.list.mockResolvedValue([{ code: 'EUR', name: 'Euro', flag: '' }])
})

describe('recurring goals', () => {
  it('labels an instance with its period and lists the template', async () => {
    renderWithProviders(<GoalsPage />)

    expect(await screen.findByText('Rent · October 2026')).toBeInTheDocument()
    expect(await screen.findByText('Recurring goals')).toBeInTheDocument()
    expect(screen.getByText(/day 10/)).toHaveTextContent('4 of 5 reached')
  })

  it('hides the management card when nothing repeats', async () => {
    api.recurringGoals.list.mockResolvedValue([])
    api.goals.list.mockResolvedValue([goal({ recurring_goal_id: null, period_start: null, period_end: null })])
    renderWithProviders(<GoalsPage />)

    expect(await screen.findByText('Rent')).toBeInTheDocument()
    expect(screen.queryByText('Recurring goals')).not.toBeInTheDocument()
  })

  it('creates a recurring goal when the repeat switch is on', async () => {
    api.recurringGoals.create.mockResolvedValue(recurring)
    const { user } = renderWithProviders(<GoalsPage />)

    await user.click(await screen.findByRole('button', { name: /Add Goal/ }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('Target Date')).toBeInTheDocument()

    await user.click(within(dialog).getByRole('switch', { name: 'Repeat every month' }))
    // A recurring goal has no deadline or tracking of its own.
    expect(within(dialog).queryByText('Target Date')).not.toBeInTheDocument()
    expect(within(dialog).queryByText('Current Amount')).not.toBeInTheDocument()

    const [name, amount] = within(dialog).getAllByRole('textbox').concat(within(dialog).getAllByRole('spinbutton'))
    await user.type(name, 'Savings')
    await user.type(amount, '200')
    await user.selectOptions(within(dialog).getByLabelText('Start day'), '15')
    expect(within(dialog).getByText(/every month on day 15/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(api.recurringGoals.create).toHaveBeenCalled())
    expect(api.recurringGoals.create.mock.calls[0][0]).toMatchObject({
      name: 'Savings', target_amount: 200, currency: 'EUR', start_day: 15,
    })
    expect(api.goals.create).not.toHaveBeenCalled()
  })

  it('switches a recurring goal off', async () => {
    api.recurringGoals.update.mockResolvedValue({ ...recurring, is_active: false })
    const { user } = renderWithProviders(<GoalsPage />)

    await user.click(await screen.findByRole('switch', { name: 'Repeat every month: Rent' }))

    await waitFor(() => expect(api.recurringGoals.update).toHaveBeenCalledWith('rec-1', { is_active: false }))
  })

  it('corrects the amount of a past period from the history', async () => {
    const past = goal({ id: 'goal-0', status: 'missed', current_amount: 100, period_start: '2026-09-10', period_end: '2026-10-09' })
    api.goals.list.mockImplementation((_status?: string, recurringId?: string) =>
      Promise.resolve(recurringId ? [past] : [goal({})]),
    )
    api.goals.update.mockResolvedValue(past)
    const { user } = renderWithProviders(<GoalsPage />)

    await user.click(await screen.findByTitle('History'))
    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByText('Sep 10, 2026 – Oct 9, 2026')).toBeInTheDocument()
    expect(within(dialog).getByText('Missed')).toBeInTheDocument()

    await user.click(within(dialog).getByTitle('Edit'))
    const input = within(dialog).getByLabelText('Current Amount')
    await user.clear(input)
    await user.type(input, '500')
    await user.click(within(dialog).getByTitle('Save'))

    await waitFor(() => expect(api.goals.update).toHaveBeenCalledWith('goal-0', { current_amount: 500 }))
  })

  it('asks whether to keep the history when deleting', async () => {
    api.recurringGoals.delete.mockResolvedValue(undefined)
    const { user } = renderWithProviders(<GoalsPage />)

    const card = (await screen.findByText('Recurring goals')).parentElement!.parentElement!
    await user.click(within(card).getByTitle('Delete'))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByLabelText('Also delete past periods'))
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(api.recurringGoals.delete).toHaveBeenCalledWith('rec-1', true))
  })
})
