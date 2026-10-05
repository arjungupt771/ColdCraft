import { useState, useCallback, useRef } from 'react'
import { useDropzone } from 'react-dropzone'
import { Link2, Upload, CheckCircle2, Loader2, Search, Sparkles, ArrowRight, Globe, XCircle, RotateCw } from 'lucide-react'
import toast from 'react-hot-toast'
import clsx from 'clsx'
import { research } from '../../services/research'
import { applications } from '../../services/applications'
import type { JobPatch } from '../../services/applications'
import ExtractionPreview from './ExtractionPreview'
import { email } from '../../services/email'
import { getApiError, getErrorMessage } from '../../lib/errors'
import { useStore } from '../../store'
import type { AsyncStatus, JobApplication } from '../../types'

type StepKey = 'extract' | 'research' | 'email'

const STEPS = [
  { key: 'extract' as const, label: 'Read job details', loading: 'Reading job details…', done: 'Job details read', icon: Search },
  { key: 'research' as const, label: 'Research company', loading: 'Researching company…', done: 'Company research completed', icon: Globe },
  { key: 'email' as const, label: 'Write email', loading: 'Writing your email…', done: 'Email written', icon: Sparkles },
]

type StepState = { status: AsyncStatus; error?: string }
const INITIAL: Record<StepKey, StepState> = {
  extract: { status: 'idle' }, research: { status: 'idle' }, email: { status: 'idle' },
}
type Input = { kind: 'url' | 'screenshot'; value: string }
type InputMode = 'url' | 'screenshot'

export default function CapturePanel() {
  const { addApplication, updateApplication, setActiveApplication, setActiveTab } = useStore()
  const [mode, setMode] = useState<InputMode>('url')
  const [url, setUrl] = useState('')
  const [preview, setPreview] = useState<string | null>(null)
  const [steps, setSteps] = useState<Record<StepKey, StepState>>(INITIAL)
  const [failedStep, setFailedStep] = useState<StepKey | null>(null)
  const [extracted, setExtracted] = useState<JobApplication | null>(null)     // waiting for the user to confirm
  const [confirmError, setConfirmError] = useState<string | null>(null)
  const [duplicate, setDuplicate] = useState<{ message: string; existingId: string } | null>(null)
  const [saving, setSaving] = useState(false)
  const input = useRef<Input | null>(null)       // remembered so a retry doesn't re-ask
  const appId = useRef<string | null>(null)      // set once the job has been extracted

  const started = Object.values(steps).some((s) => s.status !== 'idle')
  const busy = Object.values(steps).some((s) => s.status === 'loading')
  const setStep = (k: StepKey, state: StepState) => setSteps((s) => ({ ...s, [k]: state }))

  const reset = () => {
    setSteps(INITIAL); setFailedStep(null); setExtracted(null); setConfirmError(null); setDuplicate(null)
    input.current = null; appId.current = null
  }

  /** Runs the pipeline from `from` onward; a failure stops at that step and offers Retry for just that step. */
  const runFrom = async (from: StepKey, force = false) => {
    let stage: StepKey = from
    setFailedStep(null)
    try {
      if (stage === 'extract') {
        setStep('extract', { status: 'loading' })
        const inp = input.current!
        const app = inp.kind === 'url' ? await research.fromUrl(inp.value, force) : await research.fromScreenshot(inp.value, force)
        appId.current = app.id
        addApplication(app)
        setStep('extract', { status: 'success' })
        setExtracted(app)                       // STOP here: the user reviews/edits before research and writing
        return
      }
      if (stage === 'research') {
        setStep('research', { status: 'loading' })
        const app = await research.run(appId.current!)
        updateApplication(app)
        setStep('research', { status: 'success' })
        stage = 'email'
      }
      if (stage === 'email') {
        setStep('email', { status: 'loading' })
        const app = await email.generate(appId.current!)
        updateApplication(app)
        setActiveApplication(app)
        setStep('email', { status: 'success' })
        toast.success(`✉️ Email ready for ${app.role_title} @ ${app.company_name}`)
        setActiveTab('email')
        setTimeout(reset, 400)
      }
    } catch (err) {
      const api = getApiError(err)
      if (api.code === 'duplicate_application' && api.existingId) {      // not a failure: you already have this job
        setSteps(INITIAL)
        setDuplicate({ message: api.message, existingId: api.existingId })
        return
      }
      setStep(stage, { status: 'error', error: getErrorMessage(err, 'This step failed') })
      setFailedStep(stage)
    }
  }

  /** Save the user's edits (if any), then continue: research → write email → open the Email tab. */
  const confirmExtraction = async (patch: JobPatch) => {
    if (!appId.current) return
    setSaving(true)
    setConfirmError(null)
    try {
      if (Object.keys(patch).length) updateApplication(await applications.updateJob(appId.current, patch))
    } catch (err) {
      setConfirmError(getErrorMessage(err, 'Could not save your edits'))
      setSaving(false)
      return
    }
    setSaving(false)
    setExtracted(null)
    void runFrom('research')
  }

  const discardExtraction = async () => {
    if (appId.current) {
      try { await applications.remove(appId.current) } catch { /* it stays in History as a draft */ }
    }
    reset()
  }

  const openExisting = async (id: string) => {
    try {
      setActiveApplication(await applications.get(id))
      setActiveTab('email')
    } catch (err) { toast.error(getErrorMessage(err, 'Could not open the existing application')) }
  }

  const retry = () => { if (failedStep) void runFrom(failedStep) }
  const captureAnyway = () => { setDuplicate(null); void runFrom('extract', true) }

  const handleUrl = () => {
    if (!url.trim()) { toast.error('Paste a job URL first'); return }
    reset()
    input.current = { kind: 'url', value: url.trim() }
    void runFrom('extract')
  }

  const onDrop = useCallback((files: File[]) => {
    const file = files[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (e) => {
      const dataUrl = e.target?.result as string
      setPreview(dataUrl)
      reset()
      input.current = { kind: 'screenshot', value: dataUrl.split(',')[1] }
      void runFrom('extract')
    }
    reader.readAsDataURL(file)
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop, accept: { 'image/*': ['.png', '.jpg', '.jpeg', '.webp'] },
    maxFiles: 1, disabled: busy || started || !!extracted || !!duplicate,
  })

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-8 pt-8 pb-6 border-b border-white/5">
        <h1 className="text-2xl font-bold text-white mb-1">New Application</h1>
        <p className="text-sm text-slate-400">Paste a job URL or drop a screenshot — AI does the rest</p>
      </div>

      <div className="flex-1 px-8 py-6 flex flex-col gap-6 overflow-y-auto">
        {/* Mode toggle */}
        <div className="flex bg-slate-800/50 rounded-xl p-1 w-fit">
          {([['url', Link2, 'Paste URL'], ['screenshot', Upload, 'Screenshot']] as const).map(([id, Icon, label]) => (
            <button key={id} onClick={() => setMode(id)}
              className={clsx('flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all',
                mode === id ? 'bg-violet-600 text-white shadow-lg' : 'text-slate-400 hover:text-white')}>
              <Icon className="w-4 h-4" />{label}
            </button>
          ))}
        </div>

        {duplicate && (
          <div className="rounded-xl border border-amber-500/25 bg-amber-500/10 p-4 max-w-2xl">
            <p className="text-sm text-amber-200 mb-3">{duplicate.message}</p>
            <div className="flex gap-2">
              <button onClick={() => openExisting(duplicate.existingId)}
                className="text-xs font-semibold text-white bg-violet-600 hover:bg-violet-500 px-3 py-1.5 rounded-lg">Open existing</button>
              <button onClick={captureAnyway}
                className="text-xs text-amber-200 border border-amber-500/30 hover:bg-amber-500/10 px-3 py-1.5 rounded-lg">Capture anyway</button>
              <button onClick={reset} className="text-xs text-slate-400 hover:text-slate-200 px-2">Cancel</button>
            </div>
          </div>
        )}

        {extracted ? (
          <ExtractionPreview app={extracted} busy={saving} error={confirmError}
            onConfirm={confirmExtraction} onDiscard={discardExtraction} />
        ) : started ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-6">
            <div className="space-y-3 w-full max-w-md">
              {STEPS.map((step) => {
                const st = steps[step.key]
                return (
                  <div key={step.key} className={clsx('rounded-xl border transition-all',
                    st.status === 'loading' && 'bg-violet-500/15 border-violet-500/25',
                    st.status === 'success' && 'bg-emerald-500/5 border-emerald-500/15',
                    st.status === 'error' && 'bg-red-500/10 border-red-500/25',
                    st.status === 'idle' && 'border-white/5 opacity-40')}>
                    <div className="flex items-center gap-3 px-4 py-3">
                      {st.status === 'loading' ? <Loader2 className="w-4 h-4 text-violet-400 animate-spin flex-shrink-0" />
                        : st.status === 'success' ? <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                        : st.status === 'error' ? <XCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
                        : <step.icon className="w-4 h-4 text-slate-500 flex-shrink-0" />}
                      <span className="text-sm font-medium text-white flex-1">
                        {st.status === 'loading' ? step.loading : st.status === 'success' ? step.done : step.label}
                      </span>
                    </div>
                    {st.status === 'error' && (
                      <div className="px-4 pb-3 -mt-1">
                        <p className="text-xs text-red-300 mb-2">{st.error}</p>
                        <button onClick={retry}
                          className="flex items-center gap-1 text-xs font-semibold text-white bg-red-500/30 hover:bg-red-500/50 px-3 py-1.5 rounded-lg transition-colors">
                          <RotateCw className="w-3 h-3" /> Retry {step.label.toLowerCase()}
                        </button>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
            {failedStep && (
              <button onClick={reset} className="text-xs text-slate-500 hover:text-slate-300">Start over</button>
            )}
          </div>
        ) : mode === 'url' ? (
          /* URL input */
          <div className="flex-1 flex flex-col gap-4">
            <div className="bg-slate-800/40 border border-white/5 rounded-2xl p-6 space-y-4">
              <div className="flex items-center gap-2 text-sm text-slate-400 mb-2">
                <Link2 className="w-4 h-4 text-violet-400" />
                Works with LinkedIn, Naukri, Indeed, company career pages
              </div>
              <div className="flex gap-3">
                <input
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleUrl()}
                  placeholder="https://linkedin.com/jobs/view/... or any job URL"
                  className="flex-1 bg-slate-900/60 border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-violet-500/50 transition-colors"
                />
                <button onClick={handleUrl} disabled={!url.trim()}
                  className="flex items-center gap-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white font-semibold px-5 py-3 rounded-xl transition-colors">
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* What happens next */}
            <div className="grid grid-cols-3 gap-3">
              {STEPS.map((step) => (
                <div key={step.key} className="bg-slate-800/30 border border-white/5 rounded-xl p-4 text-center">
                  <div className="w-8 h-8 rounded-lg bg-violet-500/10 flex items-center justify-center mx-auto mb-2">
                    <step.icon className="w-4 h-4 text-violet-400" />
                  </div>
                  <p className="text-xs text-slate-400">{step.loading.replace('…', '')}</p>
                </div>
              ))}
            </div>
          </div>
        ) : (
          /* Screenshot drop */
          <div className="flex-1 flex flex-col gap-4">
            <div {...getRootProps()} className={clsx(
              'flex-1 min-h-[280px] border-2 border-dashed rounded-2xl flex flex-col items-center justify-center gap-4 cursor-pointer transition-all',
              isDragActive ? 'border-violet-400 bg-violet-500/8' : 'border-slate-700 hover:border-slate-500 bg-slate-800/20'
            )}>
              <input {...getInputProps()} />
              {preview ? (
                <div className="flex flex-col items-center gap-3">
                  <img src={preview} alt="preview" className="max-h-40 rounded-lg object-contain opacity-50" />
                  <p className="text-sm text-slate-500">Drop another to replace</p>
                </div>
              ) : (
                <div className="text-center px-4">
                  <div className="w-14 h-14 rounded-2xl bg-slate-800 border border-white/5 flex items-center justify-center mx-auto mb-3">
                    <Upload className="w-6 h-6 text-slate-400" />
                  </div>
                  <p className="text-white font-medium mb-1">Drop your screenshot here</p>
                  <p className="text-sm text-slate-500">PNG, JPG, WEBP — LinkedIn, Naukri, any job board</p>
                </div>
              )}
            </div>
            <div className="flex items-center gap-2 text-xs text-slate-500 bg-slate-800/30 rounded-xl px-4 py-3">
              <kbd className="bg-slate-700 px-2 py-0.5 rounded text-[10px] font-mono">Ctrl+Shift+S</kbd>
              Global hotkey — captures screen from anywhere
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
