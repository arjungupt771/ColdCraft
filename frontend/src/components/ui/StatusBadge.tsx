import clsx from 'clsx'
import type { ApplicationStatus } from '../../types'
import { STATUS_LABEL, STATUS_STYLE } from '../../lib/status'

export default function StatusBadge({ status, className }: { status: ApplicationStatus; className?: string }) {
  return (
    <span className={clsx('inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border', STATUS_STYLE[status] ?? STATUS_STYLE.DRAFT, className)}>
      {STATUS_LABEL[status] ?? status}
    </span>
  )
}
