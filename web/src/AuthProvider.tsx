// Who's signed in (#22). The token is kept in sessionStorage: it survives a refresh, but not
// closing the browser, and isn't shared with other tabs, so a second account in a second tab
// works (D-101). Any request the server rejects with 401 signs out here. The app shows the
// sign-in page at whatever URL you're on, so signing in again lands you back where you were.
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { api, ApiError, configureApi, type User } from './api/client'
import { AuthContext } from './auth'

const TOKEN_KEY = 'collab.token'

function storedToken(): string | null {
  try {
    return window.sessionStorage.getItem(TOKEN_KEY)
  } catch {
    return null // storage blocked: just don't remember the sign-in
  }
}

function storeToken(token: string | null) {
  try {
    if (token) window.sessionStorage.setItem(TOKEN_KEY, token)
    else window.sessionStorage.removeItem(TOKEN_KEY)
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
    setToken(result.token)
    setUser(result.user)
  }, [signOut])

  const value = useMemo(
    () => ({ user, checking: token !== null && user === null, checkError, signIn, signOut }),
    [user, token, checkError, signIn, signOut],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
