import { useState } from 'react'
import { Trash2, Sparkles, AlertTriangle } from 'lucide-react'
import AsyncStatus from '../../components/ui/AsyncStatus'
import type { JobPatch } from '../../services/applications'
import type { JobApplication } from '../../types'

interface Props {
  app: JobApplication
  busy: boolean
  error?: string | null
  onConfirm: (patch: JobPatch) => void
  onDiscard: () => void
}

const field = 'w-full bg-slate-900/60 border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-violet-500/50'

/** Step 2 of the flow: show what the AI extracted and let the user fix it before any email is written. */
export default function ExtractionPreview({ app, busy, error, onConfirm, onDiscard }: Props) {
  const [company, setCompany] = useState(app.company_name)
  const [role, setRole] = useState(app.role_title)
  const [jd, setJd] = useState(app.jd_text)
  const [skills, setSkills] = useState((app.required_skills || []).join(', '))
  const [website, setWebsite] = useState(app.company_website || '')
  const [recruiter, setRecruiter] = useState(app.recipient_name || '')
  const [recruiterEmail, setRecruiterEmail] = useState(app.recipient_email || '')

  const valid = company.trim() && role.trim() && jd.trim()
  const thinJd = jd.trim().length < 200

  const confirm = () => {
    const patch: JobPatch = {}
    if (company.trim() !== app.company_name) patch.company_name = company.trim()
    if (role.trim() !== app.role_title) patch.role_title = role.trim()
    if (jd.trim() !== app.jd_text) patch.jd_text = jd.trim()
    const list = skills.split(/[,\n]/).map((s) => s.trim()).filter(Boolean)
    if (list.join('|') !== (app.required_skills || []).join('|')) patch.required_skills = list
    if (website.trim() !== (app.company_website || '')) patch.company_website = website.trim()
    if (recruiter.trim() !== (app.recipient_name || '')) patch.recipient_name = recruiter.trim()
    if (recruiterEmail.trim() && recruiterEmail.trim() !== (app.recipient_email || '')) patch.recipient_email = recruiterEmail.trim()
    onConfirm(patch)
  }

  return (
    <div className="flex-1 flex flex-col gap-4 max-w-2xl">
      <div>
        <h2 className="text-lg font-semibold text-white">Check what the AI found</h2>
        <p className="text-xs text-slate-400">Fix anything wrong — the email is written from exactly this.</p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <label className="text-xs text-slate-500">Company<input className={field} value={company} onChange={(e) => setCompany(e.target.value)} /></label>
        <label className="text-xs text-slate-500">Role<input className={field} value={role} onChange={(e) => setRole(e.target.value)} /></label>
        <label className="text-xs text-slate-500">Company website<input className={field} value={website} placeholder="optional" onChange={(e) => setWebsite(e.target.value)} /></label>
        <label className="text-xs text-slate-500">Key skills (comma-separated)<input className={field} value={skills} onChange={(e) => setSkills(e.target.value)} /></label>
        <label className="text-xs text-slate-500">Recruiter name<input className={field} value={recruiter} placeholder="only if the posting names one" onChange={(e) => setRecruiter(e.target.value)} /></label>
        <label className="text-xs text-slate-500">Recruiter email<input className={field} value={recruiterEmail} placeholder="optional — we'll look one up" onChange={(e) => setRecruiterEmail(e.target.value)} /></label>
      </div>
      <label className="text-xs text-slate-500 flex flex-col gap-1">Job description
        <textarea className={`${field} min-h-[160px] resize-y leading-relaxed`} value={jd} onChange={(e) => setJd(e.target.value)} />
      </label>
      {thinJd && (
        <p className="flex items-center gap-2 text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2">
          <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" /> The description is short, so the email will be fairly generic. Paste more of the posting if you can.
        </p>
      )}
      <AsyncStatus status={error ? 'error' : 'idle'} loadingText="" error={error} />
      <div className="flex gap-2">
        <button onClick={onDiscard} disabled={busy}
          className="flex items-center gap-2 text-sm text-slate-300 bg-slate-800/60 hover:bg-slate-700/60 border border-white/8 px-4 py-2.5 rounded-xl disabled:opacity-40">
          <Trash2 className="w-4 h-4" /> Discard
        </button>
        <button onClick={confirm} disabled={busy || !valid}
          className="flex-1 flex items-center justify-center gap-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white font-semibold py-2.5 rounded-xl text-sm transition-colors">
          <Sparkles className="w-4 h-4" /> Looks right — research &amp; write email
        </button>
      </div>
    </div>
  )
}
