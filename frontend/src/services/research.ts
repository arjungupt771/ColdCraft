import { http } from './api'
import type { JobApplication } from '../types'

export const research = {
  /** Extract the job from a URL only (status DRAFT). Follow with `run`. */
  fromUrl: (url: string, force = false) =>
    http.post<JobApplication>('/process-linkedin', { url }, { params: { research: false, force } }).then((r) => r.data),
  fromScreenshot: (image_base64: string, force = false) =>
    http.post<JobApplication>('/process-screenshot', { image_base64 }, { params: { research: false, force } }).then((r) => r.data),
  /** Company research + recruiter lookup → READY. Also the retry path. */
  run: (applicationId: string) => http.post<JobApplication>(`/applications/${applicationId}/research`).then((r) => r.data),
}
