import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Mail, CheckCircle2, Loader2, Plus, X, User, Briefcase, Zap } from 'lucide-react'
import toast from 'react-hot-toast'
import clsx from 'clsx'
import { profile as profileApi, gmail } from '../../services/profile'
import { getErrorMessage } from '../../lib/errors'
import { useStore } from '../../store'
import type { UserProfile } from '../../types'

export default function ProfilePanel() {
  const { setProfile } = useStore()
  const qc = useQueryClient()
  const [form, setForm] = useState<Partial<UserProfile>>({})
  const [skillInput, setSkillInput] = useState('')

  const { data: profile, isLoading } = useQuery({
    queryKey: ['profile'],
    queryFn: async () => { const p = await profileApi.get(); setProfile(p); return p },
  })

  const { data: gmailStatus } = useQuery({
    queryKey: ['gmail-status'],
    queryFn: gmail.status,
    refetchInterval: 8_000,
  })

  useEffect(() => { if (profile) setForm(profile) }, [profile])

  const saveMutation = useMutation({
    mutationFn: () => profileApi.update(form),
    onSuccess: (p) => { setProfile(p); qc.invalidateQueries({ queryKey: ['profile'] }); toast.success('Profile saved') },
    onError: (err) => toast.error(getErrorMessage(err, 'Save failed')),
  })

  const connectGmail = async () => {
    try {
      window.open(await gmail.authUrl(), '_blank')
    } catch (err) {
      toast.error(getErrorMessage(err, 'Gmail OAuth not configured — add GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET to .env'))
    }
  }

  const addSkill = () => {
    if (!skillInput.trim()) return
    setForm({ ...form, skills: [...(form.skills || []), skillInput.trim()] })
    setSkillInput('')
  }

  if (isLoading) return (
    <div className="flex items-center justify-center h-full">
      <Loader2 className="w-8 h-8 text-violet-400 animate-spin" />
    </div>
  )

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="px-8 pt-8 pb-6 border-b border-white/5">
        <h1 className="text-2xl font-bold text-white mb-1">Your Profile</h1>
        <p className="text-slate-400 text-sm">Set up once — AI uses this to personalise every email</p>
      </div>

      <div className="flex-1 px-8 py-6 space-y-6">
        {/* Gmail */}
        <div className="bg-slate-800/40 border border-white/5 rounded-2xl p-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-red-500/10 flex items-center justify-center">
                <Mail className="w-5 h-5 text-red-400" />
              </div>
              <div>
                <p className="font-semibold text-white text-sm">Gmail</p>
                <p className="text-xs text-slate-400">
                  {gmailStatus?.connected ? gmailStatus.email : 'Not connected — needed to send emails'}
                </p>
              </div>
            </div>
            {gmailStatus?.connected ? (
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1 text-xs text-emerald-400">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Connected
                </span>
                <button onClick={async () => { await gmail.disconnect(); qc.invalidateQueries({ queryKey: ['gmail-status'] }); toast.success('Disconnected') }}
                  className="text-xs text-red-400 hover:text-red-300 transition-colors">
                  Disconnect
                </button>
              </div>
            ) : (
              <button onClick={connectGmail}
                className="bg-white text-slate-900 font-semibold text-sm px-4 py-2 rounded-xl hover:bg-slate-100 transition-colors">
                Connect Gmail
              </button>
            )}
          </div>
        </div>

        {/* Personal info */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <User className="w-4 h-4 text-slate-400" />
            <p className="text-sm font-semibold text-white">Personal info</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {[
              { key: 'name', label: 'Full name', placeholder: 'Arjun Sharma' },
              { key: 'email', label: 'Your email', placeholder: 'arjun@gmail.com' },
              { key: 'phone', label: 'Phone', placeholder: '+91 98765 43210' },
              { key: 'linkedin', label: 'LinkedIn URL', placeholder: 'linkedin.com/in/arjun' },
            ].map(({ key, label, placeholder }) => (
              <div key={key}>
                <label className="text-xs text-slate-500 mb-1 block">{label}</label>
                <input
                  value={(form as any)[key] || ''}
                  onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                  placeholder={placeholder}
                  className="w-full bg-slate-900/60 border border-white/8 rounded-xl px-3 py-2.5 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-violet-500/50 transition-colors"
                />
              </div>
            ))}
          </div>
        </div>

        {/* Experience + Tone */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Briefcase className="w-4 h-4 text-slate-400" />
            <p className="text-sm font-semibold text-white">Preferences</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-500 mb-1 block">Years of experience</label>
              <input type="number" min={0} max={50}
                value={form.experience_years || 0}
                onChange={(e) => setForm({ ...form, experience_years: parseInt(e.target.value) || 0 })}
                className="w-full bg-slate-900/60 border border-white/8 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-violet-500/50 transition-colors"
              />
            </div>
            <div>
              <label className="text-xs text-slate-500 mb-1 block">Email tone</label>
              <select value={form.tone || 'professional'} onChange={(e) => setForm({ ...form, tone: e.target.value as any })}
                className="w-full bg-slate-900/60 border border-white/8 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-violet-500/50 transition-colors">
                <option value="professional">Professional</option>
                <option value="friendly">Friendly</option>
                <option value="concise">Concise (short)</option>
              </select>
            </div>
          </div>
        </div>

        {/* Skills */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Zap className="w-4 h-4 text-slate-400" />
            <p className="text-sm font-semibold text-white">Skills</p>
          </div>
          <div className="flex flex-wrap gap-1.5 mb-2 min-h-[32px]">
            {(form.skills || []).map((s, i) => (
              <span key={i} className="flex items-center gap-1 text-xs bg-violet-500/10 border border-violet-500/20 text-violet-300 px-2.5 py-1 rounded-lg">
                {s}
                <button onClick={() => setForm({ ...form, skills: (form.skills || []).filter((_, j) => j !== i) })}
                  className="hover:text-red-400 transition-colors ml-0.5">
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <input value={skillInput} onChange={(e) => setSkillInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addSkill()}
              placeholder="Add skill — React, Python, SQL..."
              className="flex-1 bg-slate-900/60 border border-white/8 rounded-xl px-3 py-2.5 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-violet-500/50 transition-colors"
            />
            <button onClick={addSkill} className="bg-slate-700/60 hover:bg-slate-700 border border-white/8 text-slate-300 px-3 py-2 rounded-xl transition-colors">
              <Plus className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Resume */}
        <div>
          <label className="text-xs text-slate-500 mb-1.5 block font-medium">Resume / bio</label>
          <textarea
            value={form.resume_text || ''}
            onChange={(e) => setForm({ ...form, resume_text: e.target.value })}
            placeholder="Paste your full resume here. The AI uses this to match your experience to each role and write personalised emails..."
            rows={8}
            className="w-full bg-slate-900/60 border border-white/8 rounded-xl px-4 py-3 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-violet-500/50 resize-none leading-relaxed transition-colors"
          />
        </div>

        <button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}
          className="w-full flex items-center justify-center gap-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white font-semibold py-3 rounded-xl transition-colors">
          {saveMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
          Save Profile
        </button>
      </div>
    </div>
  )
}
