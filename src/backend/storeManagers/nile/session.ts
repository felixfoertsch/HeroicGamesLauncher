import {
  createCipheriv,
  createDecipheriv,
  createHash,
  randomBytes
} from 'crypto'
import {
  existsSync,
  readFileSync,
  writeFileSync,
  renameSync,
  copyFileSync,
  chmodSync,
  constants
} from 'fs'
import { join } from 'path'

function record(value: unknown): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error('Invalid Amazon session structure')
  }
  return value as Record<string, unknown>
}

/** Repair Nile 1.2's legacy migration without exporting credentials or renewing their age. */
export function recoverNileSession(directory: string): boolean {
  const profile = join(directory, 'current_user.json')
  if (!existsSync(profile)) return false
  const { user_id } = record(
    JSON.parse(readFileSync(profile, 'utf8')) as unknown
  )
  if (typeof user_id !== 'string' || !user_id.trim()) return false
  const key = createHash('sha256').update(user_id).digest()
  const path = join(
    directory,
    `${createHash('md5').update(user_id).digest('hex')}.enc`
  )
  if (!existsSync(path)) return false
  const encrypted = readFileSync(path)
  const ivCipher = createDecipheriv('aes-256-ecb', key, null)
  ivCipher.setAutoPadding(false)
  const iv = Buffer.concat([
    ivCipher.update(encrypted.subarray(0, 16)),
    ivCipher.final()
  ])
  const cipher = createDecipheriv('aes-256-cbc', key, iv)
  const data = record(
    JSON.parse(
      Buffer.concat([
        cipher.update(encrypted.subarray(16)),
        cipher.final()
      ]).toString('utf8')
    ) as unknown
  )
  const metadata = data.NILE === undefined ? {} : record(data.NILE)
  if (metadata.token_obtain_time !== undefined) return false
  const bearer = record(record(data.tokens).bearer)
  if (typeof bearer.refresh_token !== 'string' || !bearer.refresh_token) {
    throw new Error('Amazon session needs sign-in')
  }
  data.NILE = { ...metadata, token_obtain_time: 1 }
  const nextIv = randomBytes(16)
  const encryptIv = createCipheriv('aes-256-ecb', key, null)
  encryptIv.setAutoPadding(false)
  const encrypt = createCipheriv('aes-256-cbc', key, nextIv)
  const output = Buffer.concat([
    encryptIv.update(nextIv),
    encryptIv.final(),
    encrypt.update(JSON.stringify(data)),
    encrypt.final()
  ])
  const backup = `${path}.before-session-recovery`
  if (!existsSync(backup)) copyFileSync(path, backup, constants.COPYFILE_EXCL)
  chmodSync(backup, 0o600)
  const temporary = `${path}.recovery-${process.pid}`
  writeFileSync(temporary, output, { mode: 0o600, flag: 'wx' })
  renameSync(temporary, path)
  return true
}
