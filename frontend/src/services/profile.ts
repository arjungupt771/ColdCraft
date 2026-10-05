import { http } from './api'
import type { UserProfile } from '../types'

export const profile = {
  get: () => http.get<UserProfile>('/profile').then((r) => r.data),
  update: (data: Partial<UserProfile>) => http.put<UserProfile>('/profile', data).then((r) => r.data),
}

export const gmail = {
  authUrl: () => http.get<{ auth_url: string }>('/gmail/auth-url').then((r) => r.data.auth_url),
  status: () => http.get<{ connected: boolean; email?: string | null }>('/gmail/status').then((r) => r.data),
  disconnect: () => http.delete('/gmail/disconnect').then(() => undefined),
}
