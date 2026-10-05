import { create } from 'zustand'
import type { UserProfile, JobApplication, AppTab } from '../types'

interface Store {
  activeTab: AppTab
  profile: UserProfile | null
  applications: JobApplication[]
  activeApplication: JobApplication | null

  setActiveTab: (t: AppTab) => void
  setProfile: (p: UserProfile) => void
  setApplications: (apps: JobApplication[]) => void
  setActiveApplication: (app: JobApplication | null) => void
  updateApplication: (app: JobApplication) => void
  addApplication: (app: JobApplication) => void
}

export const useStore = create<Store>((set) => ({
  activeTab: 'capture',
  profile: null,
  applications: [],
  activeApplication: null,

  setActiveTab: (activeTab) => set({ activeTab }),
  setProfile: (profile) => set({ profile }),
  setApplications: (applications) => set({ applications }),
  setActiveApplication: (activeApplication) => set({ activeApplication }),
  updateApplication: (app) => set((s) => ({
    applications: s.applications.map((a) => a.id === app.id ? app : a),
    activeApplication: s.activeApplication?.id === app.id ? app : s.activeApplication,
  })),
  addApplication: (app) => set((s) => ({
    applications: s.applications.some((a) => a.id === app.id) ? s.applications : [app, ...s.applications],
  })),
}))
