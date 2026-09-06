import { existsSync, readFileSync } from 'graceful-fs'
import { libraryManagerMap } from '../..'
import { configStore } from '../electronStores'
import { NileUser } from '../user'
import { logError } from 'backend/logger'

jest.mock('../..', () => ({
  libraryManagerMap: { nile: { runRunnerCommand: jest.fn() } }
}))
jest.mock('../electronStores', () => ({
  configStore: { set: jest.fn(), delete: jest.fn(), get_nodefault: jest.fn() }
}))
jest.mock('../constants', () => ({
  nileConfigPath: '/heroic/nile_config/nile',
  nileUserData: '/heroic/nile_config/nile/current_user.json'
}))
jest.mock('graceful-fs', () => ({
  existsSync: jest.fn(),
  readFileSync: jest.fn()
}))
jest.mock('backend/utils', () => ({ clearCache: jest.fn() }))
jest.mock('backend/logger', () => ({
  LogPrefix: { Nile: 'Nile' },
  logDebug: jest.fn(),
  logInfo: jest.fn(),
  logError: jest.fn()
}))
jest.mock('electron', () => ({ session: { fromPartition: jest.fn() } }))

const currentPath = '/heroic/nile_config/nile/current_user.json'
const legacyPath = '/heroic/nile_config/nile/user.json'
const user = { name: 'Test', user_id: 'test-id' }
const registerData = {
  code: 'test-code',
  client_id: 'test-client',
  code_verifier: 'test-verifier',
  serial: 'test-serial'
}
const loginData = {
  url: 'https://amazon.com/ap/signin?openid.return_to=https%3A%2F%2Fwww.amazon.com',
  client_id: 'test-client',
  code_verifier: 'test-verifier',
  serial: 'test-serial'
}
const runCommand = jest.mocked(libraryManagerMap.nile.runRunnerCommand)
const files = new Map<string, string>()

beforeEach(() => {
  jest.clearAllMocks()
  files.clear()
  jest.mocked(existsSync).mockImplementation((path) => files.has(String(path)))
  jest.mocked(readFileSync).mockImplementation((path) => {
    const contents = files.get(String(path))
    if (contents === undefined) throw new Error('File not found')
    return contents
  })
  runCommand.mockReset()
  runCommand.mockResolvedValue({ stdout: '', stderr: '' })
})

describe('Nile session detection', () => {
  it('rehydrates a valid CLI session when the Heroic cache is empty', () => {
    files.set(currentPath, JSON.stringify(user))
    expect(NileUser.isLoggedIn()).toEqual(user)
    expect(configStore.set).toHaveBeenCalledWith('userData', user)
    expect(runCommand).not.toHaveBeenCalled()
  })

  it('reads a legacy profile without exposing its tokens', () => {
    files.set(
      legacyPath,
      JSON.stringify({
        extensions: {
          customer_info: { given_name: 'Test', user_id: 'test-id' }
        },
        tokens: { bearer: { refresh_token: 'secret' } }
      })
    )
    expect(NileUser.getUserData()).toEqual(user)
    expect(configStore.set).toHaveBeenCalledWith('userData', user)
  })

  it('does not revive legacy data over an invalid current profile', () => {
    files.set(currentPath, '{}')
    files.set(
      legacyPath,
      JSON.stringify({
        extensions: {
          customer_info: { given_name: 'Test', user_id: 'test-id' }
        }
      })
    )
    expect(NileUser.isLoggedIn()).toBe(false)
    expect(configStore.set).not.toHaveBeenCalled()
  })

  it('clears stale cached identity after the local session is removed', () => {
    files.set(currentPath, JSON.stringify(user))
    expect(NileUser.isLoggedIn()).toEqual(user)
    files.clear()
    expect(NileUser.isLoggedIn()).toBe(false)
    expect(configStore.delete).toHaveBeenCalledWith('userData')
  })

  it('handles corrupt JSON without exposing its contents', () => {
    files.set(currentPath, '{secret-token')
    expect(NileUser.getUserData()).toBeUndefined()
    expect(JSON.stringify(jest.mocked(logError).mock.calls)).not.toContain(
      'secret-token'
    )
  })
})

describe('Nile login preparation', () => {
  it('resumes existing sessions without requesting an auth URL', async () => {
    files.set(currentPath, JSON.stringify(user))
    await expect(NileUser.getLoginData()).resolves.toEqual({ user })
    expect(runCommand).not.toHaveBeenCalled()
  })

  it('returns fresh login data when signed out', async () => {
    runCommand.mockResolvedValue({
      stdout: JSON.stringify(loginData),
      stderr: ''
    })
    await expect(NileUser.getLoginData()).resolves.toEqual(loginData)
    expect(runCommand).toHaveBeenCalledWith(
      ['auth', '--login', '--non-interactive'],
      expect.objectContaining({ abortId: 'nile-auth' })
    )
  })

  it('recognizes a session migrated by Nile during preparation', async () => {
    runCommand.mockImplementation(async () => {
      files.set(currentPath, JSON.stringify(user))
      return { stdout: '', stderr: 'You are already logged in' }
    })
    await expect(NileUser.getLoginData()).resolves.toEqual({ user })
  })

  it.each([
    { stdout: '', stderr: 'some error' },
    { stdout: '{broken', stderr: '' },
    { stdout: '{}', stderr: '' },
    { stdout: '', stderr: '', abort: true },
    { stdout: '', stderr: '', error: 'helper unavailable' }
  ])('rejects failed preparation with a safe message: %j', async (result) => {
    runCommand.mockResolvedValue(result)
    await expect(NileUser.getLoginData()).rejects.toThrow(
      'Could not prepare Amazon login'
    )
  })
})

describe('Nile registration', () => {
  it('accepts saved profiles independently of log wording', async () => {
    runCommand.mockImplementation(async () => {
      files.set(currentPath, JSON.stringify(user))
      return { stdout: '', stderr: 'Registered successfully' }
    })
    await expect(NileUser.login(registerData)).resolves.toEqual({
      status: 'done',
      user
    })
    expect(runCommand).toHaveBeenCalledWith(
      [
        'register',
        '--code',
        registerData.code,
        '--code-verifier',
        registerData.code_verifier,
        '--serial',
        registerData.serial,
        '--client-id',
        registerData.client_id
      ],
      expect.objectContaining({ abortId: 'nile-login' })
    )
  })

  it('rejects success logs without a saved profile', async () => {
    runCommand.mockResolvedValue({
      stdout: '',
      stderr: '[AUTH_MANAGER]: Succesfully registered a device'
    })
    await expect(NileUser.login(registerData)).resolves.toEqual({
      status: 'failed',
      user: undefined
    })
  })

  it.each([{ abort: true }, { error: 'failed' }])(
    'does not accept aborted/failed commands: %j',
    async (failure) => {
      files.set(currentPath, JSON.stringify(user))
      runCommand.mockResolvedValue({ stdout: '', stderr: '', ...failure })
      expect((await NileUser.login(registerData)).status).toBe('failed')
    }
  )

  it('does not send incomplete registration data to Nile', async () => {
    expect((await NileUser.login({ ...registerData, code: '' })).status).toBe(
      'failed'
    )
    expect(runCommand).not.toHaveBeenCalled()
  })

  it('handles helper rejection without exposing its arguments', async () => {
    runCommand.mockRejectedValue(new Error('command contained secret-code'))
    expect((await NileUser.login(registerData)).status).toBe('failed')
    expect(JSON.stringify(jest.mocked(logError).mock.calls)).not.toContain(
      'secret-code'
    )
  })

  it('redacts partial JSON authentication output', async () => {
    await NileUser.login(registerData)
    const sanitize = runCommand.mock.calls[0][1]?.logSanitizer
    expect(sanitize).toBeDefined()
    expect(sanitize?.('{"access_token":"secret')).not.toContain('secret')
  })
})
