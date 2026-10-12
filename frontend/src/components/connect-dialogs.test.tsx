import { act, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { renderWithProviders } from '@/test/utils'
import { ConnectorSelectDialog } from './connector-select-dialog'
import { OAuthConnectDialog } from './oauth-connect-dialog'
import { BankConnectDialog } from './bank-connect-dialog'
import { TokenConnectDialog } from './token-connect-dialog'
import { ConnectionSettingsDialog } from './connection-settings-dialog'
import type { BankConnection } from '@/types'

const api = vi.hoisted(() => ({ getProviders: vi.fn(), listInstitutions: vi.fn(), getReconnectToken: vi.fn(), getConnectToken: vi.fn(), getOAuthUrl: vi.fn(), handleCallback: vi.fn(), toastError: vi.fn() }))
vi.mock('@/lib/api', () => ({ connections: api, auth: api }))
vi.mock('@/hooks/use-display-locale', () => ({ useDateLocale: () => 'en-US' }))
vi.mock('sonner', () => ({ toast: { error: api.toastError } }))
vi.mock('react-pluggy-connect', () => ({ PluggyConnect: ({ connectToken }: { connectToken: string }) => <div>{connectToken}</div> }))

beforeEach(() => { vi.resetAllMocks() })

it('ignores provider responses from a closed session when reopened', async () => {
  let finish!: (data: unknown) => void
  api.getProviders.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    .mockResolvedValueOnce([{ name: 'new', display_name: 'New provider', description: 'Synthetic', configured: true }])
  const props = { onClose: vi.fn(), onSelect: vi.fn() }
  const { rerender } = renderWithProviders(<ConnectorSelectDialog open {...props} />)
  rerender(<ConnectorSelectDialog open={false} {...props} />)
  rerender(<ConnectorSelectDialog open {...props} />)
  await screen.findByText('New provider')
  await act(async () => { finish([{ name: 'old', display_name: 'Old provider', configured: true }]) })
  expect(screen.queryByText('Old provider')).not.toBeInTheDocument()
  expect(screen.getByText('New provider')).toBeInTheDocument()
})

it('ignores an earlier country request after back navigation and another selection', async () => {
  let finish!: (data: unknown) => void
  api.listInstitutions.mockResolvedValueOnce({ countries: ['DE', 'GB'] })
    .mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    .mockResolvedValueOnce({ institutions: [{ country: 'GB', name: 'new', display_name: 'New bank' }] })
  const { user } = renderWithProviders(<OAuthConnectDialog open provider="synthetic" onClose={vi.fn()} />)
  await user.click(await screen.findByText('DE'))
  await user.click(screen.getByRole('button', { name: 'Back' }))
  await user.click(screen.getByText('GB'))
  await screen.findByText('New bank')
  await act(async () => { finish({ institutions: [{ country: 'DE', name: 'old', display_name: 'Old bank' }] }) })
  expect(screen.queryByText('Old bank')).not.toBeInTheDocument()
  expect(screen.getByText('New bank')).toBeInTheDocument()
})

it('waits for banks in the remembered country instead of showing an empty result', async () => {
  localStorage.setItem('securo:lastOAuthCountry', 'DE')
  let finish!: (data: unknown) => void
  api.listInstitutions.mockResolvedValueOnce({ countries: ['DE'] })
    .mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
  renderWithProviders(<OAuthConnectDialog open provider="synthetic" onClose={vi.fn()} />)
  await screen.findByRole('button', { name: 'Back' })
  expect(screen.queryByText('No institutions found.')).not.toBeInTheDocument()
  await act(async () => { finish({ institutions: [{ country: 'DE', name: 'bank', display_name: 'Remembered bank' }] }) })
  expect(screen.getByText('Remembered bank')).toBeInTheDocument()
})

it('uses the latest close callback without restarting a bank token request', async () => {
  let reject!: (error: Error) => void
  api.getReconnectToken.mockImplementation(() => new Promise((_, fail) => { reject = fail }))
  const firstClose = vi.fn()
  const latestClose = vi.fn()
  const { rerender } = renderWithProviders(<BankConnectDialog open reconnectConnectionId="synthetic" onClose={firstClose} />)
  rerender(<BankConnectDialog open reconnectConnectionId="synthetic" onClose={latestClose} />)
  expect(api.getReconnectToken).toHaveBeenCalledTimes(1)
  await act(async () => { reject(new Error('synthetic failure')) })
  expect(firstClose).not.toHaveBeenCalled()
  expect(latestClose).toHaveBeenCalledOnce()
  expect(api.toastError).toHaveBeenCalledOnce()
})

it('ignores token failures after the bank dialog closes', async () => {
  let reject!: (error: Error) => void
  api.getReconnectToken.mockImplementation(() => new Promise((_, fail) => { reject = fail }))
  const onClose = vi.fn()
  const { rerender } = renderWithProviders(<BankConnectDialog open reconnectConnectionId="synthetic" onClose={onClose} />)
  rerender(<BankConnectDialog open={false} reconnectConnectionId="synthetic" onClose={onClose} />)
  await act(async () => { reject(new Error('late failure')) })
  expect(onClose).not.toHaveBeenCalled()
  expect(api.toastError).not.toHaveBeenCalled()
})

async function openOAuthOptions() {
  localStorage.removeItem('securo:lastOAuthCountry')
  api.listInstitutions.mockResolvedValueOnce({ countries: ['RO'] })
    .mockResolvedValueOnce({ institutions: [{ country: 'RO', name: 'bank', display_name: 'Synthetic bank', max_consent_days: 90 }] })
  // Never resolves: the redirect itself is not under test.
  api.getOAuthUrl.mockImplementation(() => new Promise(() => {}))
  const view = renderWithProviders(<OAuthConnectDialog open provider="synthetic" onClose={vi.fn()} />)
  await view.user.click(await screen.findByText('RO'))
  await view.user.click(await screen.findByText('Synthetic bank'))
  return view
}

it('asks for import history before redirecting to the bank', async () => {
  const { user } = await openOAuthOptions()
  expect(api.getOAuthUrl).not.toHaveBeenCalled()
  expect(screen.getByRole('radio', { name: /Full history/ })).toBeChecked()
  await user.click(screen.getByRole('button', { name: 'Continue to bank' }))
  expect(api.getOAuthUrl).toHaveBeenCalledWith('synthetic', {
    country: 'RO',
    institution_name: 'bank',
    valid_until_days: 90,
  })
})

it('sends a fresh-start import window through the OAuth flow params', async () => {
  const { user } = await openOAuthOptions()
  await user.click(screen.getByRole('radio', { name: /Start fresh/ }))
  await user.click(screen.getByRole('button', { name: 'Continue to bank' }))
  expect(api.getOAuthUrl.mock.calls[0][1]).toMatchObject({ import_window: { mode: 'fresh' } })
})

it('sends the chosen operator with a from-date import window', async () => {
  const { user } = await openOAuthOptions()
  await user.click(screen.getByRole('radio', { name: /From a date/ }))
  await user.selectOptions(screen.getByRole('combobox'), 'exclusive')
  await user.click(screen.getByRole('button', { name: 'Continue to bank' }))
  const { import_window } = api.getOAuthUrl.mock.calls[0][1]
  expect(import_window).toMatchObject({ mode: 'from_date', inclusive: false })
  expect(import_window.date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
})

it('returns from the options step to the bank list', async () => {
  const { user } = await openOAuthOptions()
  // Header arrow and footer button both go back, as on the bank step.
  await user.click(screen.getAllByRole('button', { name: 'Back' })[0])
  expect(screen.getByText('Synthetic bank')).toBeInTheDocument()
  expect(screen.queryByRole('radio')).not.toBeInTheDocument()
})

it('shows the import history step before opening the widget connector', async () => {
  api.getConnectToken.mockResolvedValue('widget-token')
  const { user } = renderWithProviders(<BankConnectDialog open provider="synthetic" onClose={vi.fn()} />)
  expect(api.getConnectToken).not.toHaveBeenCalled()
  await user.click(screen.getByRole('radio', { name: /Start fresh/ }))
  await user.click(screen.getByRole('button', { name: 'Continue to connector' }))
  expect(await screen.findByText('widget-token')).toBeInTheDocument()
})

it('sends the import window with a pasted token and hides it on reconnect', async () => {
  api.handleCallback.mockResolvedValue({})
  const { user, unmount } = renderWithProviders(<TokenConnectDialog open provider="synthetic" onClose={vi.fn()} />)
  await user.click(screen.getByRole('radio', { name: /Start fresh/ }))
  await user.type(screen.getByRole('textbox'), 'setup-token')
  await user.click(screen.getByRole('button', { name: 'Connect' }))
  expect(api.handleCallback).toHaveBeenCalledWith(
    'setup-token', 'synthetic', undefined, { import_window: { mode: 'fresh' } }, undefined,
  )
  unmount()
  renderWithProviders(<TokenConnectDialog open provider="synthetic" reconnectConnectionId="conn" onClose={vi.fn()} />)
  expect(screen.queryByRole('radio')).not.toBeInTheDocument()
})

it('shows the import cutoff as read-only in connection settings', () => {
  const connection = {
    id: 'conn', institution_name: 'Synthetic bank', display_name: null, provider: 'synthetic',
    settings: { import_mode: 'from_date', import_from: '2026-10-15' },
  } as BankConnection
  renderWithProviders(<ConnectionSettingsDialog open connection={connection} onClose={vi.fn()} />)
  expect(screen.getByText(/^From /)).toBeInTheDocument()
  expect(screen.getByText('Chosen when the connection was created. It cannot be changed.')).toBeInTheDocument()
})
