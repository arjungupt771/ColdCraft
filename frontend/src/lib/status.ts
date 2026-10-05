import type { ApplicationStatus } from '../types'

/** Statuses meaning "the first email has gone out". */
export const SENT_STATUSES: ApplicationStatus[] = [
  'SENT', 'FOLLOW_UP_DUE', 'FOLLOW_UP_SENT', 'REPLIED', 'INTERVIEW',
]
/** Statuses where we're waiting on a reply (follow-ups and "got a reply" apply). */
export const AWAITING_REPLY: ApplicationStatus[] = ['SENT', 'FOLLOW_UP_DUE', 'FOLLOW_UP_SENT']
export const CLOSED: ApplicationStatus[] = ['REJECTED', 'WITHDRAWN']

/** History groups, in lifecycle order. */
export const GROUPS: { id: string; title: string; statuses: ApplicationStatus[] }[] = [
  { id: 'progress', title: 'In progress', statuses: ['DRAFT', 'RESEARCHING', 'READY', 'SENDING'] },
  { id: 'waiting', title: 'Waiting for reply', statuses: ['SENT', 'FOLLOW_UP_DUE', 'FOLLOW_UP_SENT'] },
  { id: 'outcome', title: 'Outcome', statuses: ['REPLIED', 'INTERVIEW', 'REJECTED', 'WITHDRAWN'] },
]
export const canWithdraw = (s: ApplicationStatus) => !['SENDING', 'REJECTED', 'WITHDRAWN'].includes(s)
export const canDelete = (s: ApplicationStatus) => ['DRAFT', 'READY', 'REJECTED', 'WITHDRAWN'].includes(s)

export const isSent = (s: ApplicationStatus) => SENT_STATUSES.includes(s)
export const isAwaitingReply = (s: ApplicationStatus) => AWAITING_REPLY.includes(s)
export const canEditDraft = (s: ApplicationStatus) => s === 'READY' || s === 'DRAFT'

export const STATUS_LABEL: Record<ApplicationStatus, string> = {
  DRAFT: 'Needs research', RESEARCHING: 'Researching…', READY: 'Ready to send', SENDING: 'Sending…', SENT: 'Sent',
  FOLLOW_UP_DUE: 'Follow-up due', FOLLOW_UP_SENT: 'Follow-up sent', REPLIED: 'Replied',
  INTERVIEW: 'Interview', REJECTED: 'Rejected', WITHDRAWN: 'Withdrawn',
}

export const STATUS_STYLE: Record<ApplicationStatus, string> = {
  DRAFT: 'text-slate-300 bg-slate-500/10 border-slate-500/20',
  RESEARCHING: 'text-violet-400 bg-violet-500/10 border-violet-500/20',
  READY: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
  SENDING: 'text-violet-300 bg-violet-500/10 border-violet-500/20 animate-pulse',
  SENT: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
  FOLLOW_UP_DUE: 'text-orange-400 bg-orange-500/10 border-orange-500/20',
  FOLLOW_UP_SENT: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20',
  REPLIED: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  INTERVIEW: 'text-fuchsia-400 bg-fuchsia-500/10 border-fuchsia-500/20',
  REJECTED: 'text-red-400 bg-red-500/10 border-red-500/20',
  WITHDRAWN: 'text-slate-400 bg-slate-500/10 border-slate-500/20',
}
