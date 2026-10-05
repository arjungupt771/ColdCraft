import { CheckCircle2, Loader2, XCircle, RotateCw } from 'lucide-react'
import clsx from 'clsx'
import type { AsyncStatus as Status } from '../../types'

interface Props {
  status: Status
  loadingText: string
  successText?: string
  error?: string | null
  onRetry?: () => void
  className?: string
}

/** idle → nothing; loading → spinner; success → ✓ message; error → ✗ message + Retry */
export default function AsyncStatus({ status, loadingText, successText, error, onRetry, className }: Props) {
  if (status === 'idle') return null
  return (
    <div role="status" aria-live="polite"
      className={clsx('flex items-center gap-2 text-sm rounded-xl px-3 py-2 border', className,
        status === 'loading' && 'text-violet-300 bg-violet-500/10 border-violet-500/20',
        status === 'success' && 'text-emerald-300 bg-emerald-500/10 border-emerald-500/20',
        status === 'error' && 'text-red-300 bg-red-500/10 border-red-500/20')}>
      {status === 'loading' && <Loader2 className="w-4 h-4 animate-spin flex-shrink-0" />}
      {status === 'success' && <CheckCircle2 className="w-4 h-4 flex-shrink-0" />}
      {status === 'error' && <XCircle className="w-4 h-4 flex-shrink-0" />}
      <span className="flex-1 min-w-0">
        {status === 'loading' && loadingText}
        {status === 'success' && (successText ?? 'Done')}
        {status === 'error' && (error || 'Failed')}
      </span>
      {status === 'error' && onRetry && (
        <button onClick={onRetry}
          className="flex items-center gap-1 text-xs font-semibold text-white bg-red-500/30 hover:bg-red-500/50 px-2.5 py-1 rounded-lg transition-colors">
          <RotateCw className="w-3 h-3" /> Retry
        </button>
      )}
    </div>
  )
}
