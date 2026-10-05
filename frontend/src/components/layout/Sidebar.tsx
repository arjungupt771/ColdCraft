import { Camera, Mail, Clock, User, Bell } from 'lucide-react'
import clsx from 'clsx'
import type { AppTab } from '../../types'

const NAV: { id: AppTab; icon: typeof Camera; label: string }[] = [
  { id: 'capture', icon: Camera, label: 'Capture' },
  { id: 'email', icon: Mail, label: 'Email' },
  { id: 'followups', icon: Bell, label: 'Follow-ups' },
  { id: 'history', icon: Clock, label: 'History' },
  { id: 'profile', icon: User, label: 'Profile' },
]

interface Props { activeTab: AppTab; onChange: (t: AppTab) => void; badges?: Partial<Record<AppTab, number>> }

export default function Sidebar({ activeTab, onChange, badges = {} }: Props) {
  return (
    <aside className="w-[72px] bg-[#0a0c12] border-r border-white/4 flex flex-col items-center py-5 gap-1.5 flex-shrink-0">
      <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-violet-600 to-violet-800 flex items-center justify-center mb-5 shadow-lg shadow-violet-900/30">
        <span className="text-white font-black text-sm tracking-tight">CC</span>
      </div>
      {NAV.map(({ id, icon: Icon, label }) => {
        const badge = badges[id]
        return (
          <button key={id} onClick={() => onChange(id)} title={label} aria-label={label}
            className={clsx('relative w-11 h-11 rounded-2xl flex items-center justify-center transition-all duration-150',
              activeTab === id ? 'bg-violet-600 text-white shadow-lg shadow-violet-900/40'
                : 'text-slate-500 hover:text-slate-300 hover:bg-white/5')}>
            <Icon className="w-5 h-5" />
            {badge != null && badge > 0 && (
              <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 bg-amber-500 rounded-full text-[10px] font-bold text-white flex items-center justify-center px-1">
                {badge}
              </span>
            )}
          </button>
        )
      })}
    </aside>
  )
}
