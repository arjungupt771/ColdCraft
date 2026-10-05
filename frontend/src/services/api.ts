import axios from 'axios'

const token = import.meta.env.VITE_API_TOKEN as string | undefined

/** The single axios instance. Every service module goes through this. */
export const http = axios.create({
  baseURL: (import.meta.env.VITE_API_BASE_URL as string | undefined) || '/api/v1',
  timeout: 120_000,                       // AI steps can take a while; backend has its own 30s/provider cap
  headers: token ? { 'X-API-Token': token } : undefined,
})

export default http
