import { http } from './api'
import type { JobApplication } from '../types'

export interface DraftPatch { subject?: string; body?: string; recipient_email?: string; notes?: string }

export interface JobPatch {
  company_name?: string; role_title?: string; jd_text?: string; required_skills?: string[]
  company_website?: string; recipient_name?: string; recipient_email?: string
}

export const applications = {
  /** Edit / confirm the extracted job (only allowed while DRAFT). */
  updateJob: (id: string, patch: JobPatch) => http.put<JobApplication>(`/applications/${id}`, patch).then((r) => r.data),
  list: () => http.get<JobApplication[]>('/applications').then((r) => r.data),
  get: (id: string) => http.get<JobApplication>(`/applications/${id}`).then((r) => r.data),
  updateDraft: (id: string, patch: DraftPatch) => http.put<JobApplication>(`/applications/${id}/email`, patch).then((r) => r.data),
  setStatus: (id: string, status: 'INTERVIEW' | 'REJECTED' | 'WITHDRAWN') =>
    http.put<JobApplication>(`/applications/${id}/status`, { status }).then((r) => r.data),
  markReplied: (id: string) => http.post<JobApplication>(`/applications/${id}/mark-replied`).then((r) => r.data),
  remove: (id: string) => http.delete(`/applications/${id}`).then(() => undefined),
}
