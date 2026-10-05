export interface UserProfile {
  id: string
  name: string
  email: string
  phone: string
  linkedin: string
  resume_text: string
  skills: string[]
  experience_years: number
  tone: 'professional' | 'friendly' | 'concise'
  gmail_connected: boolean
}

export interface FollowUp {
  id: string
  application_id: string
  scheduled_at: string
  sent_at: string | null
  subject: string | null
  body: string | null
  status: 'pending' | 'sending' | 'sent' | 'cancelled' | 'failed'
  sequence_number: number
}

/** Mirrors backend app/domain/state_machine.py */
export type ApplicationStatus =
  | 'DRAFT' | 'RESEARCHING' | 'READY' | 'SENDING' | 'SENT' | 'FOLLOW_UP_DUE' | 'FOLLOW_UP_SENT'
  | 'REPLIED' | 'INTERVIEW' | 'REJECTED' | 'WITHDRAWN'

export interface JobApplication {
  id: string
  company_name: string
  role_title: string
  jd_text: string
  company_research: string
  company_website: string | null
  required_skills: string[]
  source: 'screenshot' | 'linkedin_url' | 'manual'
  linkedin_job_url: string | null
  recipient_email: string | null
  recipient_name: string | null
  recipient_source: 'hunter' | 'guess' | 'user' | null
  email_subject: string | null
  email_body: string | null
  ai_provider_used: string
  prompt_version: string | null
  email_confidence: number | null
  last_error: string | null
  status: ApplicationStatus
  sent_at: string | null
  followup_scheduled_at: string | null
  followup_sent_at: string | null
  followup_count: number
  reply_received: boolean
  notes: string
  created_at: string
}

export type AppTab = 'capture' | 'email' | 'followups' | 'history' | 'profile'
export type AsyncStatus = 'idle' | 'loading' | 'success' | 'error'
