import type { User } from './types'

const TOKEN_KEY = 'moyin.token'
const USER_KEY = 'moyin.user'

export const session = {
  getToken(): string {
    return localStorage.getItem(TOKEN_KEY) ?? ''
  },
  getUser(): User | null {
    const raw = localStorage.getItem(USER_KEY)
    if (!raw) return null
    try {
      return JSON.parse(raw) as User
    } catch {
      return null
    }
  },
  save(token: string, user: User) {
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  },
  isLoggedIn() {
    return Boolean(localStorage.getItem(TOKEN_KEY))
  },
}
