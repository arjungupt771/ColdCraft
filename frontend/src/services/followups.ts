import { http } from './api'
import type { FollowUp } from '../types'

export const followups = {
  schedule: (application_id: string, days_after_send: number, custom_note?: string) =>
    http.post<FollowUp>('/followups/schedule', { application_id, days_after_send, custom_note }).then((r) => r.data),
  due: () => http.get<FollowUp[]>('/followups/due').then((r) => r.data),
  forApplication: (appId: string) => http.get<FollowUp[]>(`/followups/${appId}`).then((r) => r.data),
  send: (id: string) => http.post<FollowUp>(`/followups/${id}/send`).then((r) => r.data),
  cancel: (id: string) => http.post(`/followups/${id}/cancel`).then((r) => r.data),
}
