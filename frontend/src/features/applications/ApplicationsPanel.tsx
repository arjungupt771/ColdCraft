import { useQuery } from '@tanstack/react-query'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Send, Link2, Camera, MessageSquare, Cpu, Trash2, Ban } from 'lucide-react'
import toast from 'react-hot-toast'
import clsx from 'clsx'
import { format } from 'date-fns'
import { applications } from '../../services/applications'
import StatusBadge from '../../components/ui/StatusBadge'
import { GROUPS, canDelete, canWithdraw, isAwaitingReply } from '../../lib/status'
import { getErrorMessage } from '../../lib/errors'
import { useStore } from '../../store'
import type { JobApplication } from '../../types'

function AppCard({ app, onSelect }: { app: JobApplication; onSelect: () => void }) {
  const qc = useQueryClient()
  const { updateApplication } = useStore()

  const replyMutation = useMutation({
    mutationFn: () => applications.markReplied(app.id),
    onSuccess: (updated) => {
      updateApplication(updated)
      qc.invalidateQueries({ queryKey: ['applications'] })
      qc.invalidateQueries({ queryKey: ['due-followups'] })
      toast.success('Marked as replied — follow-ups cancelled')
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Could not mark as replied')),
  })

  const outcomeMutation = useMutation({
    mutationFn: (status: 'INTERVIEW' | 'REJECTED' | 'WITHDRAWN') => applications.setStatus(app.id, status),
    onSuccess: (updated) => { updateApplication(updated); qc.invalidateQueries({ queryKey: ['applications'] }) },
    onError: (err) => toast.error(getErrorMessage(err, 'Could not update status')),
  })

  const deleteMutation = useMutation({
    mutationFn: () => applications.remove(app.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['applications'] }); qc.invalidateQueries({ queryKey: ['due-followups'] }); toast.success('Deleted') },
    onError: (err) => toast.error(getErrorMessage(err, 'Could not delete')),
  })
  const withdraw = () => { if (window.confirm(`Withdraw your application to ${app.company_name}? Pending follow-ups will be cancelled.`)) outcomeMutation.mutate('WITHDRAWN') }
  const remove = () => { if (window.confirm(`Delete ${app.role_title} @ ${app.company_name} permanently?`)) deleteMutation.mutate() }

  return (
    <div className="bg-slate-800/30 border border-white/5 hover:border-white/10 rounded-2xl p-4 transition-all group">
      <div className="flex items-start justify-between mb-3">
        <button onClick={onSelect} className="flex-1 text-left min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <StatusBadge status={app.status} />
            <span className={clsx('flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border',
              app.source === 'linkedin_url'
                ? 'text-blue-400 bg-blue-500/8 border-blue-500/15'
                : 'text-slate-500 bg-slate-700/30 border-white/8')}>
              {app.source === 'linkedin_url' ? <Link2 className="w-3 h-3" /> : <Camera className="w-3 h-3" />}
              {app.source === 'linkedin_url' ? 'URL' : 'Screenshot'}
            </span>
            {app.ai_provider_used && (
              <span className={clsx('flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border',
                app.ai_provider_used === 'groq'
                  ? 'text-violet-400 bg-violet-500/8 border-violet-500/15'
                  : 'text-blue-400 bg-blue-500/8 border-blue-500/15')}>
                <Cpu className="w-3 h-3" /> {app.ai_provider_used}
              </span>
            )}
          </div>
          <p className="font-semibold text-white truncate">{app.role_title}</p>
          <p className="text-sm text-slate-400 truncate">{app.company_name}</p>
        </button>
        <div className="text-right ml-3 flex-shrink-0">
          <p className="text-xs text-slate-500">{format(new Date(app.created_at), 'MMM d')}</p>
          {app.followup_count > 0 && (
            <p className="text-xs text-amber-400 mt-0.5">{app.followup_count} follow-up{app.followup_count > 1 ? 's' : ''}</p>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between">
        <div className="flex flex-wrap gap-1">
          {(app.required_skills || []).slice(0, 3).map((s) => (
            <span key={s} className="text-xs bg-slate-800 text-slate-500 px-1.5 py-0.5 rounded">{s}</span>
          ))}
        </div>
        {isAwaitingReply(app.status) && (
          <button
            onClick={() => replyMutation.mutate()}
            disabled={replyMutation.isPending}
            className="flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 bg-emerald-500/8 hover:bg-emerald-500/15 border border-emerald-500/20 px-2.5 py-1 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
          >
            <MessageSquare className="w-3 h-3" /> Got a reply
          </button>
        )}
        {app.status === 'REPLIED' && (
          <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <button onClick={() => outcomeMutation.mutate('INTERVIEW')} disabled={outcomeMutation.isPending}
              className="text-xs text-fuchsia-300 bg-fuchsia-500/10 border border-fuchsia-500/20 px-2.5 py-1 rounded-lg">Interview</button>
            <button onClick={() => outcomeMutation.mutate('REJECTED')} disabled={outcomeMutation.isPending}
              className="text-xs text-red-300 bg-red-500/10 border border-red-500/20 px-2.5 py-1 rounded-lg">Rejected</button>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between mt-2">
        <p className="text-xs text-slate-600 truncate">{app.recipient_email}</p>
        <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {canWithdraw(app.status) && (
            <button onClick={withdraw} disabled={outcomeMutation.isPending} title="Withdraw"
              className="text-slate-500 hover:text-slate-200 p-1"><Ban className="w-3.5 h-3.5" /></button>
          )}
          {canDelete(app.status) && (
            <button onClick={remove} disabled={deleteMutation.isPending} title="Delete"
              className="text-slate-500 hover:text-red-400 p-1"><Trash2 className="w-3.5 h-3.5" /></button>
          )}
        </div>
      </div>
      {app.last_error && app.status === 'READY' && <p className="text-xs text-red-400/80 mt-1 truncate" title={app.last_error}>⚠ {app.last_error}</p>}
    </div>
  )
}

export default function ApplicationsPanel() {
  const { setActiveApplication, setActiveTab, setApplications } = useStore()
  const qc = useQueryClient()
  const [filter, setFilter] = useState<string>('all')

  const { data = [], isLoading } = useQuery({
    queryKey: ['applications'],
    queryFn: async () => {
      const data = await applications.list()
      setApplications(data)
      return data
    },
    refetchInterval: 30_000,
  })

  const dueCount = data.filter((a) => a.status === 'FOLLOW_UP_DUE').length
  const stats = [
    { label: 'Total', value: data.length },
    { label: 'Sent', value: data.filter((a) => !!a.sent_at).length },      // includes ones later replied/rejected
    { label: 'Replied', value: data.filter((a) => a.reply_received).length },
    { label: 'Follow-up due', value: dueCount },
  ]
  const groups = GROUPS.map((g) => ({ ...g, items: data.filter((a) => g.statuses.includes(a.status)) }))
    .filter((g) => g.items.length > 0 && (filter === 'all' || filter === g.id))

  return (
    <div className="flex flex-col h-full">
      <div className="px-8 pt-8 pb-6 border-b border-white/5 flex-shrink-0">
        <h1 className="text-2xl font-bold text-white mb-4">Outreach History</h1>
        <div className="grid grid-cols-4 gap-3">
          {stats.map((s) => (
            <div key={s.label} className="bg-slate-800/40 border border-white/5 rounded-xl p-3 text-center">
              <p className="text-2xl font-black text-white">{s.value}</p>
              <p className="text-xs text-slate-500 mt-0.5">{s.label}</p>
            </div>
          ))}
        </div>
        <div className="flex gap-2 mt-4">
          {[{ id: 'all', title: 'All' }, ...GROUPS].map((g) => (
            <button key={g.id} onClick={() => setFilter(g.id)}
              className={clsx('text-xs px-3 py-1.5 rounded-lg border transition-colors',
                filter === g.id ? 'bg-violet-600 border-violet-500 text-white' : 'border-white/10 text-slate-400 hover:text-white')}>
              {g.title}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-8 py-5 space-y-5">
        {isLoading ? (
          <div className="text-center py-12 text-slate-500">Loading...</div>
        ) : data.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-16 h-16 rounded-3xl bg-slate-800/60 border border-white/5 flex items-center justify-center mx-auto mb-4">
              <Send className="w-7 h-7 text-slate-500" />
            </div>
            <p className="text-white font-medium">No applications yet</p>
            <p className="text-slate-500 text-sm mt-1">Capture a JD to start your outreach</p>
          </div>
        ) : (
          <>
            {groups.map((g) => (
              <div key={g.id}>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">{g.title} · {g.items.length}</p>
                <div className="space-y-2">
                  {g.items.map((app) => (
                    <AppCard key={app.id} app={app} onSelect={() => { setActiveApplication(app); setActiveTab('email') }} />
                  ))}
                </div>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  )
}
