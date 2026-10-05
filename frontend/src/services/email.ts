import { http } from './api'
import type { JobApplication } from '../types'

export const email = {
  generate: (application_id: string) =>
    http.post<JobApplication>('/generate-email', { application_id }).then((r) => r.data),
  send: (data: { application_id: string; recipient_email: string; subject: string; body: string; confirm_unverified?: boolean }) =>
    http.post<JobApplication>('/send-email', data).then((r) => r.data),
}
