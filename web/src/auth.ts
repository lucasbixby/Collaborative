// The signed-in user, shared through context; AuthProvider (AuthProvider.tsx) fills it in.
import { createContext, useContext } from 'react'

import type { User } from './api/client'

export interface Auth {
  user: User | null
  /** True while a stored token is being checked, so the app doesn't flash the sign-in page. */
  checking: boolean
  /** Why checking a stored token failed, other than a 401 (the server being down, say). */
  checkError: string | null
  signIn: (username: string, password: string) => Promise<void>
  signOut: () => void
}

export const AuthContext = createContext<Auth | null>(null)

export function useAuth(): Auth {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('useAuth needs an AuthProvider')
  return auth
}
