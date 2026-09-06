import type { NileLoginData, NileLoginUrl, NileUserData } from './types/nile'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

/** Return only public profile fields, never Nile's stored authentication tokens. */
export function parseNileUserData(
  value: unknown,
  legacy = false
): NileUserData | undefined {
  if (!isRecord(value)) return
  if (legacy) {
    if (!isRecord(value.extensions)) return
    value = value.extensions.customer_info
    if (!isRecord(value)) return
  }

  const name = legacy ? value.given_name : value.name
  const user_id = value.user_id
  if (!isNonEmptyString(name) || !isNonEmptyString(user_id)) return
  return { name, user_id }
}

/** Invalid/empty helper output must not be used as a webview URL. */
export function parseNileLoginData(output: string): NileLoginUrl | undefined {
  try {
    const data: unknown = JSON.parse(output)
    if (!isRecord(data)) return
    const { url, code_verifier, serial, client_id } = data
    if (
      !isNonEmptyString(url) ||
      !isNonEmptyString(code_verifier) ||
      !isNonEmptyString(serial) ||
      !isNonEmptyString(client_id)
    ) {
      return
    }
    const parsed = new URL(url)
    if (
      parsed.protocol !== 'https:' ||
      !['amazon.com', 'www.amazon.com'].includes(parsed.hostname) ||
      parsed.username ||
      parsed.password ||
      parsed.port
    ) {
      return
    }
    return { url, code_verifier, serial, client_id }
  } catch {
    // JSON/URL errors can contain credentials; do not log the input or error.
    return
  }
}

/** Only consume codes from the return URL requested by this login attempt. */
export function getAmazonAuthorizationCode(
  pageUrl: string,
  loginUrl: string
): string | null {
  try {
    const returnTo = new URL(loginUrl).searchParams.get('openid.return_to')
    if (!returnTo) return null
    const expected = new URL(returnTo)
    const actual = new URL(pageUrl)
    if (
      expected.protocol !== 'https:' ||
      !['amazon.com', 'www.amazon.com'].includes(expected.hostname) ||
      actual.origin !== expected.origin ||
      actual.pathname !== expected.pathname ||
      actual.username ||
      actual.password
    ) {
      return null
    }
    const code = actual.searchParams.get('openid.oa2.authorization_code')
    return isNonEmptyString(code) ? code : null
  } catch {
    return null
  }
}

/**
 * Report a timeout immediately, but settle only after the runner request does.
 * Retrying before then can reuse callRunner's still-cached, aborted command.
 */
export function prepareNileLogin(
  getLoginData: () => Promise<NileLoginData>,
  onTimeout: () => void
): { result: Promise<NileLoginData>; dispose: () => void } {
  let timedOut = false
  const timeout = setTimeout(() => {
    timedOut = true
    onTimeout()
  }, 30000)

  const result = (async () => {
    try {
      const data = await getLoginData()
      if (timedOut) throw new Error('Could not prepare Amazon login')
      return data
    } finally {
      clearTimeout(timeout)
    }
  })()

  return { result, dispose: () => clearTimeout(timeout) }
}
