// Who's signed in. The desktop app keeps the token between launches (localStorage); a browser
// tab keeps it only until the tab closes (sessionStorage), so a shared computer doesn't hold a
// week-long token on disk. Any request the server rejects with 401 signs out here.
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { api, ApiError, configureApi, type User } from './api/client'
import { AuthContext } from './auth'
import { desktop } from './platform'

const TOKEN_KEY = 'collab.token'
const storage = () => (desktop ? window.localStorage : window.sessionStorage)

function storedToken(): string | null {
  try {
    return storage().getItem(TOKEN_KEY)
  } catch {
    return null // storage blocked: just don't remember the sign-in
  }
}

function storeToken(token: string | null) {
  try {
    if (token) storage().setItem(TOKEN_KEY, token)
    else storage().removeItem(TOKEN_KEY)
  } catch {
    // as above
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(storedToken)
  const [user, setUser] = useState<User | null>(null)
  const [checkError, setCheckError] = useState<string | null>(null)

  const signOut = useCallback(() => {
    storeToken(null)
    setToken(null)
    setUser(null)
  }, [])

  // Set synchronously during render, so a child's first request already carries the token.
  configureApi(token, signOut)

  useEffect(() => {
    if (token && !user) {
      api.me().then(setUser, (error: ApiError) => {
        if (error.status !== 401) setCheckError(error.message) // a 401 has already signed out
      })
    }
  }, [token, user])

  const signIn = useCallback(async (username: string, password: string) => {
    const result = await api.login(username, password)
    storeToken(result.token)
    configureApi(result.token, signOut)
    setCheckError(null)
    setToken(result.token)
    setUser(result.user)
  }, [signOut])

  const value = useMemo(
    () => ({ user, token, checking: token !== null && user === null, checkError, signIn, signOut }),
    [user, token, checkError, signIn, signOut],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
