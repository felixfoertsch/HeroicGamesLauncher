import { prepareNileLogin } from 'common/nileAuth'
import type { NileLoginData } from 'common/types/nile'

const loginData = {
  url: 'https://www.amazon.com/ap/signin',
  client_id: 'test-client',
  code_verifier: 'test-verifier',
  serial: 'test-serial'
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: Error) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

beforeEach(() => jest.useFakeTimers())
afterEach(() => jest.useRealTimers())

describe('Nile preparation timeout', () => {
  it.each<NileLoginData>([
    loginData,
    { user: { user_id: 'test-id', name: 'Test' } }
  ])('accepts a result before the deadline: %j', async (data) => {
    const onTimeout = jest.fn()
    const preparation = prepareNileLogin(() => Promise.resolve(data), onTimeout)
    await expect(preparation.result).resolves.toEqual(data)
    expect(jest.getTimerCount()).toBe(0)
    await jest.advanceTimersByTimeAsync(30000)
    expect(onTimeout).not.toHaveBeenCalled()
  })

  it('clears the timer when preparation rejects before the deadline', async () => {
    const onTimeout = jest.fn()
    const preparation = prepareNileLogin(
      () => Promise.reject(new Error('Preparation failed')),
      onTimeout
    )
    await expect(preparation.result).rejects.toThrow('Preparation failed')
    expect(jest.getTimerCount()).toBe(0)
    expect(onTimeout).not.toHaveBeenCalled()
  })

  it('turns a synchronous request error into a settled promise', async () => {
    const preparation = prepareNileLogin(() => {
      throw new Error('IPC unavailable')
    }, jest.fn())
    await expect(preparation.result).rejects.toThrow('IPC unavailable')
    expect(jest.getTimerCount()).toBe(0)
  })

  it.each<NileLoginData>([
    loginData,
    { user: { user_id: 'test-id', name: 'Test' } }
  ])('waits for cleanup and discards a late success: %j', async (data) => {
    const request = deferred<NileLoginData>()
    const onTimeout = jest.fn()
    const preparation = prepareNileLogin(() => request.promise, onTimeout)
    const settled = jest.fn()
    const outcome = preparation.result.catch((error: unknown) => {
      settled()
      return error
    })

    await jest.advanceTimersByTimeAsync(29999)
    expect(onTimeout).not.toHaveBeenCalled()
    await jest.advanceTimersByTimeAsync(1)
    expect(onTimeout).toHaveBeenCalledTimes(1)
    expect(settled).not.toHaveBeenCalled()
    await jest.advanceTimersByTimeAsync(30000)
    expect(onTimeout).toHaveBeenCalledTimes(1)
    expect(settled).not.toHaveBeenCalled()

    request.resolve(data)
    expect(await outcome).toEqual(new Error('Could not prepare Amazon login'))
    expect(settled).toHaveBeenCalledTimes(1)
    expect(jest.getTimerCount()).toBe(0)
  })

  it('does not release Retry while an aborted command is still cached', async () => {
    const request = deferred<NileLoginData>()
    // Model callRunner: identical calls share one promise until its finally
    // handler has removed the command from commandsRunning.
    let running: Promise<NileLoginData> | undefined = request.promise.finally(
      () => {
        running = undefined
      }
    )
    const getLoginData = jest.fn(() => running ?? Promise.resolve(loginData))
    const abort = jest.fn()
    const preparation = prepareNileLogin(getLoginData, abort)
    let preparing = true
    const outcome = preparation.result
      .catch(() => undefined)
      .finally(() => {
        preparing = false
      })

    await jest.advanceTimersByTimeAsync(30000)
    expect(abort).toHaveBeenCalledTimes(1)
    expect(preparing).toBe(true)
    expect(running).toBeDefined()
    expect(getLoginData).toHaveBeenCalledTimes(1)

    request.reject(new Error('Aborted'))
    await outcome
    expect(preparing).toBe(false)
    expect(running).toBeUndefined()

    const retry = prepareNileLogin(getLoginData, abort)
    await expect(retry.result).resolves.toEqual(loginData)
    expect(getLoginData).toHaveBeenCalledTimes(2)
    expect(abort).toHaveBeenCalledTimes(1)
    expect(jest.getTimerCount()).toBe(0)
  })

  it('disposes the timeout without pretending the request has settled', async () => {
    const request = deferred<NileLoginData>()
    const onTimeout = jest.fn()
    const preparation = prepareNileLogin(() => request.promise, onTimeout)
    const settled = jest.fn()
    const outcome = preparation.result.then(settled)

    preparation.dispose()
    preparation.dispose()
    expect(jest.getTimerCount()).toBe(0)
    await jest.advanceTimersByTimeAsync(60000)
    expect(onTimeout).not.toHaveBeenCalled()
    expect(settled).not.toHaveBeenCalled()
    request.resolve(loginData)
    await outcome
    expect(settled).toHaveBeenCalledWith(loginData)
  })
})
