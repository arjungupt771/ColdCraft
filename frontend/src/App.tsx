import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import { useStore } from './store'
import { applications } from './services/applications'
import { followups } from './services/followups'
import Sidebar from './components/layout/Sidebar'
import CapturePanel from './features/capture/CapturePanel'
import EmailPanel from './features/email/EmailPanel'
import FollowUpsPanel from './features/followups/FollowUpsPanel'
import ApplicationsPanel from './features/applications/ApplicationsPanel'
import ProfilePanel from './features/profile/ProfilePanel'
import './index.css'

const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 10_000 } } })

function AppInner() {
  const { activeTab, setActiveTab, setApplications } = useStore()

  useQuery({
    queryKey: ['applications'],
    queryFn: async () => {
      const data = await applications.list()
      setApplications(data)
      return data
    },
  })

  const { data: dueFollowups = [] } = useQuery({
    queryKey: ['due-followups'],
    queryFn: followups.due,
    refetchInterval: 60_000,
  })

  return (
    <div className="flex h-screen bg-[#0c0e14] overflow-hidden">
      <Sidebar activeTab={activeTab} onChange={setActiveTab}
        badges={{ followups: dueFollowups.filter((f) => f.status === 'pending').length }} />
      <main className="flex-1 overflow-hidden">
        {activeTab === 'capture' && <CapturePanel />}
        {activeTab === 'email' && <EmailPanel />}
        {activeTab === 'followups' && <FollowUpsPanel />}
        {activeTab === 'history' && <ApplicationsPanel />}
        {activeTab === 'profile' && <ProfilePanel />}
      </main>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <AppInner />
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: { background: '#1e2030', color: '#e2e8f0', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '12px', fontSize: '13px' },
          success: { iconTheme: { primary: '#7c3aed', secondary: '#fff' } },
        }}
      />
    </QueryClientProvider>
  )
}
