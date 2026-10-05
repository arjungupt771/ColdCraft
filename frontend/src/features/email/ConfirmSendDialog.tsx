import { useState } from 'react'
import { AlertTriangle, Send } from 'lucide-react'

interface Props {
  to: string
  subject: string
  body: string
  isGuess: boolean                 // recipient is an unconfirmed careers@ guess
  busy: boolean
  onCancel: () => void
  onConfirm: (confirmUnverified: boolean) => void
}

/** Last checkpoint before an email leaves: shows exactly what will be sent, and to whom. */
export default function ConfirmSendDialog({ to, subject, body, isGuess, busy, onCancel, onConfirm }: Props) {
  const [ack, setAck] = useState(false)
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-6" role="dialog" aria-modal="true">
      <div className="bg-[#14161f] border border-white/10 rounded-2xl w-full max-w-lg p-5 space-y-3">
        <h2 className="text-lg font-semibold text-white">Send this email?</h2>
        <div className="text-sm space-y-1">
          <p><span className="text-slate-500">To:</span> <span className="text-white">{to}</span></p>
          <p><span className="text-slate-500">Subject:</span> <span className="text-white">{subject}</span></p>
        </div>
        <pre className="max-h-48 overflow-y-auto whitespace-pre-wrap text-xs text-slate-300 bg-slate-900/60 border border-white/5 rounded-lg p-3 font-sans">{body}</pre>
        {isGuess && (
          <label className="flex items-start gap-2 text-xs text-amber-200 bg-amber-500/10 border border-amber-500/25 rounded-lg p-3 cursor-pointer">
            <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} className="mt-0.5" />
            <span><AlertTriangle className="inline w-3.5 h-3.5 mr-1" />
              {to} is a <b>guessed</b> address, not a confirmed recruiter contact. It may bounce or reach the wrong person. Send anyway.</span>
          </label>
        )}
        <p className="text-xs text-slate-500">This sends once and can't be undone.</p>
        <div className="flex gap-2 justify-end">
          <button onClick={onCancel} disabled={busy} className="text-sm text-slate-300 px-4 py-2 rounded-xl border border-white/10 hover:bg-white/5 disabled:opacity-40">Back to edit</button>
          <button onClick={() => onConfirm(isGuess && ack)} disabled={busy || (isGuess && !ack)}
            className="flex items-center gap-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white font-semibold px-4 py-2 rounded-xl text-sm">
            <Send className="w-4 h-4" /> {busy ? 'Sending…' : 'Send now'}
          </button>
        </div>
      </div>
    </div>
  )
}
