import { create } from 'zustand'

interface SidebarState {
  isOpen: boolean
  toggleSidebar: () => void
  setSidebarOpen: (isOpen: boolean) => void
}

export const useSidebarStore = create<SidebarState>()((set) => ({
  isOpen: true,
  toggleSidebar: () => set((state) => ({ isOpen: !state.isOpen })),
  setSidebarOpen: (isOpen) => set({ isOpen }),
}))

interface InformesSidebarState {
  isOpen: boolean
  toggleSidebar: () => void
  setSidebarOpen: (isOpen: boolean) => void
}

export const useInformesSidebarStore = create<InformesSidebarState>()((set) => ({
  isOpen: true,
  toggleSidebar: () => set((state) => ({ isOpen: !state.isOpen })),
  setSidebarOpen: (isOpen) => set({ isOpen }),
}))

