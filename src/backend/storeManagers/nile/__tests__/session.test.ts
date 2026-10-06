import { createCipheriv, createDecipheriv, createHash } from 'crypto'
import { mkdtempSync, writeFileSync, readFileSync, rmSync, statSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { recoverNileSession } from '../session'

test('repairs migrated credentials, forces expiry, preserves private backup and is idempotent', () => {
  const directory = mkdtempSync(join(tmpdir(), 'nile-session-'))
  try {
    const uid = 'synthetic-user'
    writeFileSync(
      join(directory, 'current_user.json'),
      JSON.stringify({ user_id: uid })
    )
    const key = createHash('sha256').update(uid).digest()
    const path = join(
      directory,
      `${createHash('md5').update(uid).digest('hex')}.enc`
    )
    const iv = Buffer.alloc(16, 7)
    const ivCipher = createCipheriv('aes-256-ecb', key, null)
    ivCipher.setAutoPadding(false)
    const cipher = createCipheriv('aes-256-cbc', key, iv)
    const data = {
      tokens: { bearer: { refresh_token: 'synthetic', expires_in: 3600 } }
    }
    const original = Buffer.concat([
      ivCipher.update(iv),
      ivCipher.final(),
      cipher.update(JSON.stringify(data)),
      cipher.final()
    ])
    writeFileSync(path, original)
    expect(recoverNileSession(directory)).toBe(true)
    const encrypted = readFileSync(path)
    const decryptIv = createDecipheriv('aes-256-ecb', key, null)
    decryptIv.setAutoPadding(false)
    const newIv = Buffer.concat([
      decryptIv.update(encrypted.subarray(0, 16)),
      decryptIv.final()
    ])
    const decrypt = createDecipheriv('aes-256-cbc', key, newIv)
    const repaired = JSON.parse(
      Buffer.concat([
        decrypt.update(encrypted.subarray(16)),
        decrypt.final()
      ]).toString()
    )
    expect(repaired).toEqual({ ...data, NILE: { token_obtain_time: 1 } })
    expect(readFileSync(`${path}.before-session-recovery`)).toEqual(original)
    expect(statSync(`${path}.before-session-recovery`).mode & 0o777).toBe(0o600)
    expect(recoverNileSession(directory)).toBe(false)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})
