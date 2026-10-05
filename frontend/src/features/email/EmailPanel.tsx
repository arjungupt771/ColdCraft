import { useState, useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Send, RefreshCw, CheckCircle2, Cpu, Link2, Camera, Clock, AlertTriangle } from 'lucide-react'
import toast from 'react-hot-toast'
import clsx from 'clsx'
import { applications } from '../../services/applications'
import { email } from '../../services/email'
import { followups } from '../../services/followups'
import { useStore } from '../../store'
import { useAsyncAction } from '../../hooks/useAsyncAction'
import AsyncStatus from '../../components/ui/AsyncStatus'
import StatusBadge from '../../components/ui/StatusBadge'
import { isSent } from '../../lib/status'
import { getErrorMessage } from '../../lib/errors'
import ResearchStatus from '../research/ResearchStatus'
import ConfirmSendDialog from './ConfirmSendDialog'

export default function EmailPanel() {
  const { activeApplication, updateApplication, setActiveTab } = useStore()
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [recipient, setRecipient] = useState('')
  const qc = useQueryClient()
  const [fuDays, setFuDays] = useState(5)
  const [showFUOptions, setShowFUOptions] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)


  // Hooks must run on every render, so they sit above the early return below.
  const generate = useAsyncAction(async (id: string) => {
    const updated = await email.generate(id)
    updateApplication(updated)
    toast.success(`Regenerated via ${updated.ai_provider_used}`)
    return updated
  })

  const send = useAsyncAction(async (id: string, to: string, subj: string, text: string, confirmUnverified: boolean) => {
    try {
      await applications.updateDraft(id, { subject: subj, body: text, recipient_email: to })   // keep edits even if sending fails
      const updated = await email.send({ application_id: id, recipient_email: to, subject: subj, body: text, confirm_unverified: confirmUnverified })
      updateApplication(updated)
      qc.invalidateQueries({ queryKey: ['applications'] })
      toast.success('Sent via Gmail!')
      setShowFUOptions(true)
      return updated
    } finally {
      setShowConfirm(false)
      qc.invalidateQueries({ queryKey: ['applications'] })
      try { updateApplication(await applications.get(id)) } catch { /* keep what we have */ }   // status / last_error
    }
  })

  const schedule = useAsyncAction(async (id: string, days: number) => {
    const fu = await followups.schedule(id, days)
    updateApplication({ ...(useStore.getState().applications.find((a) => a.id === id)!), followup_scheduled_at: fu.scheduled_at })
    qc.invalidateQueries({ queryKey: ['due-followups'] })
    toast.success(`Follow-up scheduled in ${days} days`)
    setShowFUOptions(false)
    return fu
  })

  useEffect(() => {
    if (activeApplication) {
      setSubject(activeApplication.email_subject || '')
      setBody(activeApplication.email_body || '')
      setRecipient(activeApplication.recipient_email || '')
    }
  }, [activeApplication?.id, activeApplication?.email_subject, activeApplication?.email_body, activeApplication?.recipient_email])

  if (!activeApplication) return (
    <div className="flex flex-col items-center justify-center h-full text-center px-6 gap-4">
      <div className="w-16 h-16 rounded-3xl bg-slate-800/60 border border-white/5 flex items-center justify-center">
        <Send className="w-7 h-7 text-slate-500" />
      </div>
      <div>
        <p className="text-white font-semibold">No email drafted yet</p>
        <p className="text-slate-500 text-sm mt-1">Process a job posting first</p>
      </div>
      <button onClick={() => setActiveTab('capture')}
        className="bg-violet-600 hover:bg-violet-500 text-white font-semibold px-5 py-2.5 rounded-xl text-sm transition-colors">
        Capture a JD
      </button>
    </div>
  )

  const app = activeApplication
  const sent = isSent(app.status)
  const needsResearch = app.status === 'DRAFT' || app.status === 'RESEARCHING'
  const editable = app.status === 'READY'

  const recipientIsGuess = app.recipient_source === 'guess' && recipient.trim().toLowerCase() === (app.recipient_email || '').toLowerCase()
  const sending = app.status === 'SENDING' || send.isLoading

  const handleSend = () => {                       // Review → confirm dialog → send
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(recipient.trim())) { toast.error('Enter a valid recipient email'); return }
    if (!subject.trim() || !body.trim()) { toast.error('Subject and body are required'); return }
    setShowConfirm(true)
  }

  // Both "not connected" and "authorization expired" messages point to Profile
  const sendNeedsGmail = send.status === 'error' && !!send.error?.includes('Profile')

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-8 pt-7 pb-5 border-b border-white/5 flex-shrink-0">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className={clsx('flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border',
                app.source === 'linkedin_url'
                  ? 'bg-blue-500/10 border-blue-500/20 text-blue-400'
                  : 'bg-slate-700/50 border-white/10 text-slate-400')}>
                {app.source === 'linkedin_url' ? <Link2 className="w-3 h-3" /> : <Camera className="w-3 h-3" />}
                {app.source === 'linkedin_url' ? 'LinkedIn URL' : 'Screenshot'}
              </span>
              {app.ai_provider_used && (
                <span className={clsx('flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border',
                  app.ai_provider_used === 'groq'
                    ? 'bg-violet-500/10 border-violet-500/20 text-violet-400'
                    : 'bg-blue-500/10 border-blue-500/20 text-blue-400')}>
                  <Cpu className="w-3 h-3" />
                  {app.ai_provider_used === 'groq' ? 'Groq' : 'Gemini'}
                </span>
              )}
            </div>
            <h1 className="text-xl font-bold text-white">{app.role_title}</h1>
            <p className="text-slate-400 text-sm">{app.company_name}</p>
          </div>
          <div className="flex flex-col items-end gap-1">
            <StatusBadge status={app.status} />
            {app.email_confidence != null && app.email_body && (
              <span title={`Model self-assessment · prompt ${app.prompt_version ?? 'n/a'}`}
                className="text-[11px] text-slate-500">
                confidence {Math.round(app.email_confidence * 100)}% · {app.prompt_version ?? ''}
              </span>
            )}
            {app.followup_scheduled_at && (
              <span className="flex items-center gap-1 text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-1 rounded-lg">
                <Clock className="w-3 h-3" /> Follow-up scheduled
              </span>
            )}
          </div>
        </div>

        {/* Research snippet */}
        {app.company_research && (
          <div className="mt-4 bg-slate-800/40 border border-white/5 rounded-xl px-4 py-3">
            <p className="text-xs text-slate-500 font-medium uppercase tracking-wide mb-1">Company Intel</p>
            <p className="text-xs text-slate-300 line-clamp-2 leading-relaxed">{app.company_research}</p>
          </div>
        )}
      </div>

      {needsResearch && <ResearchStatus app={app} />}
      {app.status === 'SENDING' && (
        <p className="mx-8 mt-4 text-sm text-violet-200 bg-violet-500/10 border border-violet-500/20 rounded-xl px-4 py-2.5">
          This email is being sent… it can't be edited or sent again until that finishes.
        </p>
      )}
      {app.status === 'READY' && app.last_error && generate.status !== 'loading' && send.status !== 'loading' && (
        <p className="mx-8 mt-4 text-sm text-red-200 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-2.5">
          Last attempt failed: {app.last_error}
        </p>
      )}

      {/* Email form */}
      <div className="flex-1 flex flex-col px-8 py-5 gap-4 overflow-y-auto min-h-0">
        <div>
          <label className="text-xs text-slate-500 mb-1.5 block font-medium">To</label>
          <input value={recipient} onChange={(e) => setRecipient(e.target.value)}
            placeholder="recruiter@company.com"
            disabled={!editable}
            className="w-full bg-slate-800/40 border border-white/8 rounded-xl px-4 py-2.5 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-violet-500/50 disabled:opacity-50 transition-colors" />
          {recipientIsGuess && editable && (
            <p className="flex items-center gap-1.5 text-xs text-amber-300 mt-1.5">
              <AlertTriangle className="w-3.5 h-3.5" /> Guessed address — replace it with a real recruiter email if you can.
            </p>
          )}
          {app.recipient_source === 'hunter' && editable && <p className="text-xs text-emerald-400/80 mt-1.5">Found via Hunter.io</p>}
        </div>
        <div>
          <label className="text-xs text-slate-500 mb-1.5 block font-medium">Subject</label>
          <input value={subject} onChange={(e) => setSubject(e.target.value)}
            disabled={!editable}
            className="w-full bg-slate-800/40 border border-white/8 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-violet-500/50 disabled:opacity-50 transition-colors" />
        </div>
        <div className="flex-1 flex flex-col">
          <label className="text-xs text-slate-500 mb-1.5 block font-medium">Email body</label>
          <textarea value={body} onChange={(e) => setBody(e.target.value)}
            disabled={!editable}
            className="flex-1 min-h-[180px] bg-slate-800/40 border border-white/8 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-violet-500/50 disabled:opacity-50 resize-none leading-relaxed transition-colors" />
        </div>

        {/* Skills */}
        {app.required_skills?.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {app.required_skills.slice(0, 8).map((s) => (
              <span key={s} className="text-xs bg-slate-800/60 border border-white/8 text-slate-400 px-2 py-0.5 rounded-md">{s}</span>
            ))}
          </div>
        )}
      </div>

      {/* Follow-up scheduler (appears after send) */}
      {showFUOptions && (
        <div className="mx-8 mb-4 bg-amber-500/8 border border-amber-500/20 rounded-2xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Clock className="w-4 h-4 text-amber-400" />
            <p className="text-sm font-medium text-white">Schedule a follow-up?</p>
          </div>
          <p className="text-xs text-slate-400 mb-3">AI will write and schedule a follow-up email automatically.</p>
          <div className="flex items-center gap-3">
            <select value={fuDays} onChange={(e) => setFuDays(Number(e.target.value))}
              className="bg-slate-800 border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none">
              {[3,5,7,10,14].map((d) => <option key={d} value={d}>In {d} days</option>)}
            </select>
            <button onClick={() => schedule.run(app.id, fuDays)} disabled={schedule.isLoading}
              className="flex-1 bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white text-sm font-semibold py-1.5 rounded-lg transition-colors">
              {schedule.isLoading ? 'Scheduling...' : 'Schedule Follow-up'}
            </button>
            <button onClick={() => setShowFUOptions(false)} className="text-xs text-slate-500 hover:text-slate-300 px-2">Skip</button>
          </div>
          <AsyncStatus className="mt-3" status={schedule.status === 'success' ? 'idle' : schedule.status}
            loadingText="Writing and scheduling follow-up…" error={schedule.error} onRetry={schedule.retry} />
        </div>
      )}

      {/* Async feedback for generate / send */}
      <div className="px-8 flex flex-col gap-2">
        <AsyncStatus status={generate.status === 'success' ? 'idle' : generate.status}
          loadingText="Writing a new draft…" error={generate.error} onRetry={generate.retry} />
        <AsyncStatus status={send.status === 'success' ? 'idle' : send.status}
          loadingText="Sending via Gmail…" error={send.error} onRetry={sendNeedsGmail ? undefined : send.retry} />
        {sendNeedsGmail && (
          <button onClick={() => setActiveTab('profile')} className="self-start text-xs text-violet-300 hover:text-violet-200 underline">
            Connect Gmail in Profile
          </button>
        )}
      </div>

      {/* Actions */}
      <div className="px-8 pb-6 pt-3 flex gap-2 flex-shrink-0">
        <button onClick={() => generate.run(app.id)} disabled={generate.isLoading || !editable || needsResearch || sending}
          className="flex items-center gap-2 bg-slate-800/60 hover:bg-slate-700/60 border border-white/8 disabled:opacity-40 text-slate-300 text-sm font-medium px-4 py-2.5 rounded-xl transition-colors">
          <RefreshCw className={clsx('w-4 h-4', generate.isLoading && 'animate-spin')} />
          {app.email_body ? 'Regenerate' : 'Write email'}
        </button>
        <button onClick={handleSend} disabled={sending || !editable || !body.trim()}
          className="flex-1 flex items-center justify-center gap-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white font-semibold py-2.5 rounded-xl text-sm transition-colors">
          {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : sent ? <CheckCircle2 className="w-4 h-4" /> : <Send className="w-4 h-4" />}
          {sent ? 'Sent ✓' : sending ? 'Sending...' : 'Review & send'}
        </button>
      </div>

      {showConfirm && (
        <ConfirmSendDialog to={recipient.trim()} subject={subject.trim()} body={body} isGuess={recipientIsGuess}
          busy={send.isLoading} onCancel={() => setShowConfirm(false)}
          onConfirm={(confirmUnverified) => send.run(app.id, recipient.trim(), subject.trim(), body, confirmUnverified)} />
      )}
    </div>
  )
}

function Loader2({ className }: { className: string }) {
  return <svg className={clsx('animate-spin', className)} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
}
