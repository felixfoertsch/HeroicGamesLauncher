import { LogPrefix, logDebug, logError, logInfo } from 'backend/logger'
import {
  NileLoginData,
  NileRegisterData,
  NileUserData
} from 'common/types/nile'
import { parseNileLoginData, parseNileUserData } from 'common/nileAuth'
import { libraryManagerMap } from '..'
import { existsSync, readFileSync } from 'graceful-fs'
import { configStore } from './electronStores'
import { clearCache } from 'backend/utils'
import { nileConfigPath, nileUserData } from './constants'
import { session } from 'electron'
import { join } from 'path'

function authLogSanitizer() {
  // Output can contain authorization codes, PKCE verifiers and bearer tokens,
  // including partial JSON chunks that cannot be safely parsed for redaction.
  return '<redacted Nile authentication output>\n'
}

export class NileUser {
  static async getLoginData(): Promise<NileLoginData> {
    // Nile refuses `auth --login` when a session already exists. Heroic's
    // electron-store cache may have been cleared independently of that session.
    const existingUser = this.getUserData()
    if (existingUser) return { user: existingUser }

    logDebug('Getting login data from Nile', LogPrefix.Nile)
    const result = await libraryManagerMap['nile'].runRunnerCommand(
      ['auth', '--login', '--non-interactive'],
      {
        abortId: 'nile-auth',
        logSanitizer: authLogSanitizer
      }
    )
    if (result.abort || result.error) {
      throw new Error('Could not prepare Amazon login')
    }

    const output = parseNileLoginData(result.stdout)
    if (output) return output

    // Starting Nile can migrate a legacy session to current_user.json.
    const migratedUser = this.getUserData()
    if (migratedUser) return { user: migratedUser }

    logError('Nile did not return valid Amazon login data', LogPrefix.Nile)
    throw new Error('Could not prepare Amazon login')
  }

  static async login(
    data: NileRegisterData
  ): Promise<{ status: 'done' | 'failed'; user: NileUserData | undefined }> {
    const failed = { status: 'failed' as const, user: undefined }
    const { code, code_verifier, serial, client_id } = data
    if (
      ![code, code_verifier, serial, client_id].every(
        (value) => typeof value === 'string' && value.trim().length > 0
      )
    ) {
      return failed
    }

    try {
      const result = await libraryManagerMap['nile'].runRunnerCommand(
        [
          'register',
          '--code',
          code,
          '--code-verifier',
          code_verifier,
          '--serial',
          serial,
          '--client-id',
          client_id
        ],
        { abortId: 'nile-login', logSanitizer: authLogSanitizer }
      )
      if (result.abort || result.error) return failed

      // Human-readable log messages are not an authentication API. A valid
      // profile written by Nile is required, even when its output says success.
      const user = this.getUserData()
      if (!user) {
        logError('Nile did not save an Amazon user profile', LogPrefix.Nile)
        return failed
      }

      logInfo('Authentication successful', LogPrefix.Nile)
      return { status: 'done', user }
    } catch {
      // Helper errors can embed command arguments or token-bearing output.
      logError('Amazon authentication failed', LogPrefix.Nile)
      return failed
    }
  }

  static async logout() {
    const commandParts = ['auth', '--logout']

    const res = await libraryManagerMap['nile'].runRunnerCommand(commandParts, {
      abortId: 'nile-logout'
    })

    if (res.abort || res.error) {
      logError('Failed to logout from Amazon', LogPrefix.Nile)
      return
    }

    configStore.delete('userData')
    clearCache('nile')
    const ses = session.fromPartition('persist:amazon')
    ses.clearStorageData().catch(() => {})
    ses.clearCache().catch(() => {})
    ses.clearAuthCache().catch(() => {})
  }

  static getUserData(): NileUserData | undefined {
    // Nile < 1.2 stores customer_info in user.json. Newer Nile stores only the
    // public profile in current_user.json; it is authoritative when present.
    const legacy = !existsSync(nileUserData)
    const path = legacy ? join(nileConfigPath, 'user.json') : nileUserData
    if (!existsSync(path)) {
      configStore.delete('userData')
      return
    }

    try {
      const user = parseNileUserData(
        JSON.parse(readFileSync(path, 'utf-8')),
        legacy
      )
      if (user) {
        configStore.set('userData', user)
        return user
      }
    } catch {
      // A damaged profile should not crash startup or leak its contents.
      logError('Could not read the Nile user profile', LogPrefix.Nile)
    }

    configStore.delete('userData')
    return
  }

  public static isLoggedIn() {
    // Rehydrate the cache before the initial library refresh, including when
    // the user authenticated with the CLI in Heroic's NILE_CONFIG_PATH.
    return this.getUserData() || false
  }
}
