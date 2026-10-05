import { useQueryClient } from '@tanstack/react-query'
import { Globe } from 'lucide-react'
import toast from 'react-hot-toast'
import AsyncStatus from '../../components/ui/AsyncStatus'
import { useAsyncAction } from '../../hooks/useAsyncAction'
import { research } from '../../services/research'
import { useStore } from '../../store'
import type { JobApplication } from '../../types'

/** Shown while an application hasn't finished research (status DRAFT). Offers Run/Retry. */
export default function ResearchStatus({ app }: { app: JobApplication }) {
  const qc = useQueryClient()
  const { updateApplication } = useStore()
  const action = useAsyncAction(async () => {
    const updated = await research.run(app.id)
    updateApplication(updated)
    qc.invalidateQueries({ queryKey: ['applications'] })
    toast.success('Company research completed')
    return updated
  })

  return (
    <div className="mx-8 mt-4 rounded-2xl border border-white/8 bg-slate-800/40 p-4">
      <div className="flex items-center gap-2 mb-1">
        <Globe className="w-4 h-4 text-violet-400" />
        <p className="text-sm font-medium text-white">Company research isn't done yet</p>
      </div>
      <p className="text-xs text-slate-400 mb-3">
        {app.last_error ? `Last attempt failed: ${app.last_error}` : 'Research must finish before an email can be written.'}
      </p>
      {action.status === 'idle'
        ? <button onClick={() => action.run()}
            className="bg-violet-600 hover:bg-violet-500 text-white text-sm font-semibold px-4 py-2 rounded-xl transition-colors">
            Research company
          </button>
        : <AsyncStatus status={action.status} loadingText="Researching company…"
            successText="Company research completed" error={action.error} onRetry={action.retry} />}
    </div>
  )
}
