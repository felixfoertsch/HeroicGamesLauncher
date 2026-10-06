import {
  getAmazonAuthorizationCode,
  parseNileLoginData,
  parseNileUserData
} from 'common/nileAuth'

const loginData = {
  url: 'https://amazon.com/ap/signin?openid.return_to=https%3A%2F%2Fwww.amazon.com',
  client_id: 'test-client',
  code_verifier: 'test-verifier',
  serial: 'test-serial'
}

describe('Nile authentication data', () => {
  it('extracts only public fields from a current profile', () => {
    expect(
      parseNileUserData({ name: 'Test', user_id: 'id', token: 'secret' })
    ).toEqual({ name: 'Test', user_id: 'id' })
  })

  it('supports the pre-1.2 profile without copying tokens to Heroic', () => {
    expect(
      parseNileUserData(
        {
          extensions: {
            customer_info: { given_name: 'Test', user_id: 'id' }
          },
          tokens: { bearer: { refresh_token: 'secret' } }
        },
        true
      )
    ).toEqual({ name: 'Test', user_id: 'id' })
  })

  it.each([null, [], {}, { name: 'Test' }, { name: 'Test', user_id: '' }])(
    'rejects malformed current profiles: %j',
    (profile) => {
      expect(parseNileUserData(profile)).toBeUndefined()
    }
  )

  it.each([{}, { extensions: null }, { extensions: { customer_info: [] } }])(
    'rejects malformed legacy profiles: %j',
    (profile) => {
      expect(parseNileUserData(profile, true)).toBeUndefined()
    }
  )

  it('parses valid helper output without modifying the verifier', () => {
    expect(parseNileLoginData(JSON.stringify(loginData))).toEqual(loginData)
  })

  it.each(['', 'You are already logged in', 'null', '{bad json'])(
    'rejects non-login output: %s',
    (output) => {
      expect(parseNileLoginData(output)).toBeUndefined()
    }
  )

  it.each(['client_id', 'code_verifier', 'serial', 'url'])(
    'rejects a missing %s',
    (key) => {
      expect(
        parseNileLoginData(JSON.stringify({ ...loginData, [key]: '' }))
      ).toBeUndefined()
    }
  )

  it.each([
    'http://amazon.com/ap/signin',
    'https://amazon.com.attacker.example/ap/signin',
    'https://user:password@amazon.com/ap/signin',
    'javascript:alert(1)'
  ])('rejects an unsafe login URL: %s', (url) => {
    expect(
      parseNileLoginData(JSON.stringify({ ...loginData, url }))
    ).toBeUndefined()
  })
})

describe('Amazon authorization redirects', () => {
  it('extracts and URL-decodes a code from the requested return URL', () => {
    expect(
      getAmazonAuthorizationCode(
        'https://www.amazon.com/?openid.oa2.authorization_code=a%2Bb%26c',
        loginData.url
      )
    ).toBe('a+b&c')
  })

  it.each([
    'https://www.amazon.com/?unrelated=value',
    'https://www.amazon.com/?openid.oa2.authorization_code=',
    'http://www.amazon.com/?openid.oa2.authorization_code=secret',
    'https://www.amazon.com.attacker.example/?openid.oa2.authorization_code=secret',
    'https://www.amazon.com/ap/signin?openid.oa2.authorization_code=secret',
    'https://user@www.amazon.com/?openid.oa2.authorization_code=secret',
    'about:blank',
    'not a URL'
  ])('ignores non-callback navigation: %s', (url) => {
    expect(getAmazonAuthorizationCode(url, loginData.url)).toBeNull()
  })

  it('requires a valid expected return URL', () => {
    expect(
      getAmazonAuthorizationCode('https://www.amazon.com/?code=x', 'invalid')
    ).toBeNull()
    expect(
      getAmazonAuthorizationCode(
        'https://www.amazon.com/?openid.oa2.authorization_code=x',
        'https://amazon.com/ap/signin'
      )
    ).toBeNull()
  })
})
