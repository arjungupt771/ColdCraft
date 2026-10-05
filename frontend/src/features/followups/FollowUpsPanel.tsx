import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Clock, Send, X, Bell, CheckCircle2, AlertCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import clsx from 'clsx'
import { format, formatDistanceToNow, isPast } from 'date-fns'
import { followups as followupsApi } from '../../services/followups'
import { applications as applicationsApi } from '../../services/applications'
import { getErrorMessage } from '../../lib/errors'
import type { FollowUp, JobApplication } from '../../types'

function FollowUpCard({ fu, app }: { fu: FollowUp; app: JobApplication | undefined }) {
  const qc = useQueryClient()
  const isDue = isPast(new Date(fu.scheduled_at))

  const sendMutation = useMutation({
    mutationFn: () => followupsApi.send(fu.id),
    onSuccess: () => {
      toast.success('Follow-up sent!')
      qc.invalidateQueries({ queryKey: ['due-followups'] })
      qc.invalidateQueries({ queryKey: ['applications'] })
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Send failed')),
  })

  const cancelMutation = useMutation({
    mutationFn: () => followupsApi.cancel(fu.id),
    onSuccess: () => {
      toast.success('Follow-up cancelled')
      qc.invalidateQueries({ queryKey: ['due-followups'] })
    },
  })

  const ordinal = { 1: '1st', 2: '2nd', 3: '3rd' }[fu.sequence_number] || `${fu.sequence_number}th`

  return (
    <div className={clsx(
      'bg-slate-800/40 border rounded-2xl p-5 transition-all',
      isDue && fu.status === 'pending'
        ? 'border-amber-500/30 bg-amber-500/5'
        : 'border-white/5'
    )}>
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-full">
              {ordinal} follow-up
            </span>
            {fu.status === 'sent' && (
              <span className="flex items-center gap-1 text-xs text-emerald-400">
                <CheckCircle2 className="w-3 h-3" /> Sent
              </span>
            )}
            {fu.status === 'cancelled' && (
              <span className="text-xs text-slate-500">Cancelled</span>
            )}
          </div>
          <p className="font-semibold text-white">{app?.role_title || 'Unknown role'}</p>
          <p className="text-sm text-slate-400">{app?.company_name}</p>
        </div>
        <div className="text-right flex-shrink-0">
          {fu.status === 'pending' && (
            <div className={clsx('flex items-center gap-1 text-xs', isDue ? 'text-amber-400' : 'text-slate-400')}>
              {isDue ? <AlertCircle className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
              {isDue
                ? `Overdue — ${formatDistanceToNow(new Date(fu.scheduled_at))} ago`
                : `Due ${formatDistanceToNow(new Date(fu.scheduled_at), { addSuffix: true })}`
              }
            </div>
          )}
          {fu.sent_at && (
            <p className="text-xs text-slate-500">Sent {format(new Date(fu.sent_at), 'MMM d, yyyy')}</p>
          )}
        </div>
      </div>

      {/* Email preview */}
      {fu.subject && (
        <div className="bg-slate-900/60 rounded-xl p-3 mb-4">
          <p className="text-xs text-slate-500 mb-1">Subject: <span className="text-slate-300">{fu.subject}</span></p>
          {fu.body && (
            <p className="text-xs text-slate-400 line-clamp-3 leading-relaxed">{fu.body}</p>
          )}
        </div>
      )}

      {/* Actions */}
      {fu.status === 'pending' && (
        <div className="flex gap-2">
          <button
            onClick={() => sendMutation.mutate()}
            disabled={sendMutation.isPending}
            className="flex-1 flex items-center justify-center gap-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-sm font-semibold py-2 rounded-xl transition-colors"
          >
            {sendMutation.isPending
              ? <span className="animate-spin text-sm">⟳</span>
              : <Send className="w-4 h-4" />}
            Send Now
          </button>
          <button
            onClick={() => cancelMutation.mutate()}
            disabled={cancelMutation.isPending}
            className="flex items-center gap-1 bg-slate-700/60 hover:bg-slate-700 border border-white/8 text-slate-400 hover:text-white text-sm px-4 py-2 rounded-xl transition-colors"
          >
            <X className="w-3.5 h-3.5" /> Cancel
          </button>
        </div>
      )}
    </div>
  )
}

export default function FollowUpsPanel() {
  const { data: followups = [], isLoading } = useQuery({
    queryKey: ['due-followups'],
    queryFn: followupsApi.due,
    refetchInterval: 60_000,
  })

  const { data: applications = [] } = useQuery({
    queryKey: ['applications'],
    queryFn: applicationsApi.list,
  })

  const appMap = Object.fromEntries(applications.map((a) => [a.id, a]))
  const pending = followups.filter((f) => f.status === 'pending')
  const sent = followups.filter((f) => f.status === 'sent')
  const due = pending.filter((f) => isPast(new Date(f.scheduled_at)))

  return (
    <div className="flex flex-col h-full">
      <div className="px-8 pt-8 pb-6 border-b border-white/5 flex-shrink-0">
        <h1 className="text-2xl font-bold text-white mb-1">Follow-ups</h1>
        <p className="text-slate-400 text-sm">
          {due.length > 0
            ? <span className="text-amber-400 font-medium">{due.length} follow-up{due.length > 1 ? 's' : ''} due now</span>
            : 'All follow-ups on schedule'
          }
          {pending.length > 0 && ` · ${pending.length} pending`}
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-8 py-6 space-y-4">
        {isLoading ? (
          <div className="text-center py-12 text-slate-500">Loading...</div>
        ) : followups.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-16 h-16 rounded-3xl bg-slate-800/60 border border-white/5 flex items-center justify-center mx-auto mb-4">
              <Bell className="w-7 h-7 text-slate-500" />
            </div>
            <p className="text-white font-medium">No follow-ups scheduled</p>
            <p className="text-slate-500 text-sm mt-1">After sending an email, you'll be prompted to schedule a follow-up</p>
          </div>
        ) : (
          <>
            {due.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-amber-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                  <AlertCircle className="w-3.5 h-3.5" /> Due now
                </p>
                <div className="space-y-3">
                  {due.map((fu) => <FollowUpCard key={fu.id} fu={fu} app={appMap[fu.application_id]} />)}
                </div>
              </div>
            )}
            {pending.filter((f) => !isPast(new Date(f.scheduled_at))).length > 0 && (
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Upcoming</p>
                <div className="space-y-3">
                  {pending.filter((f) => !isPast(new Date(f.scheduled_at))).map((fu) => (
                    <FollowUpCard key={fu.id} fu={fu} app={appMap[fu.application_id]} />
                  ))}
                </div>
              </div>
            )}
            {sent.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Sent</p>
                <div className="space-y-3">
                  {sent.map((fu) => <FollowUpCard key={fu.id} fu={fu} app={appMap[fu.application_id]} />)}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
