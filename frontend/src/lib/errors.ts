import axios from 'axios'

/** Best human-readable message from an axios/Error value. */
export function getErrorMessage(err: unknown, fallback = 'Something went wrong'): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg)   // FastAPI validation errors
    if (err.code === 'ERR_NETWORK') return 'Cannot reach the ColdCraft backend. Is it running on port 8000?'
    if (err.response?.status === 401) return 'Not authorised — check VITE_API_TOKEN matches API_TOKEN'
    if (err.response?.status === 429) return 'Too many requests — wait a moment and retry'
  }
  return err instanceof Error && err.message ? err.message : fallback
}

export interface ApiError { message: string; code?: string; existingId?: string; status?: number }

/** Like getErrorMessage, but keeps the backend's `code` / `existing_id` so the UI can react to them. */
export function getApiError(err: unknown): ApiError {
  const data = axios.isAxiosError(err) ? err.response?.data : undefined
  return {
    message: getErrorMessage(err),
    code: data?.code,
    existingId: data?.existing_id,
    status: axios.isAxiosError(err) ? err.response?.status : undefined,
  }
}
