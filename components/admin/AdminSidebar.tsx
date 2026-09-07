'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase'
import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'

const menuItems = [
  {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
      </svg>
    ),
    label: 'Dashboard',
    href: '/admin',
  },
  {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
      </svg>
    ),
    label: 'Users',
    href: '/admin/users',
  },
  {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
      </svg>
    ),
    label: 'Activity Logs',
    href: '/admin/logs',
  },
  {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
    label: 'Settings',
    href: '/admin/settings',
  },
]

export default function AdminSidebar() {
  const pathname = usePathname()
  const router = useRouter()
  const supabase = createClient()
  const [loggingOut, setLoggingOut] = useState(false)
  const [collapsed, setCollapsed] = useState(false)

  useEffect(() => {
    document.documentElement.style.setProperty('--admin-sidebar-width', collapsed ? '76px' : '240px')
  }, [collapsed])

  const handleLogout = async () => {
    setLoggingOut(true)
    await supabase.auth.signOut()
    router.push('/admin-login')
  }

  const isActive = (href: string) => {
    if (href === '/admin') return pathname === '/admin'
    return pathname.startsWith(href)
  }

  return (
    <aside className={`fixed top-0 left-0 z-40 flex h-full flex-col border-r border-white/10 bg-black transition-all duration-300 ${collapsed ? 'w-[76px]' : 'w-[240px]'}`}>
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -left-16 top-10 h-40 w-40 rounded-full bg-white/10 blur-3xl" />
        <div className="absolute bottom-16 right-0 h-28 w-28 rounded-full bg-white/5 blur-2xl" />
      </div>
      {/* Logo */}
      <div className="relative border-b border-white/10 px-4 py-5">
        <div className="flex items-center justify-between gap-2">
        <motion.div whileHover={{ x: 3 }} className="flex min-w-0 items-center gap-2.5">
          <div className="w-7 h-7 bg-white rounded-lg flex items-center justify-center transition-transform duration-300 group-hover:rotate-6">
            <svg className="w-4 h-4" fill="none" stroke="#000000" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          {!collapsed && <div className="min-w-0">
            <p className="truncate text-sm font-black text-white">BrandWave</p>
            <p className="truncate text-[11px] font-bold text-white">Admin Panel</p>
          </div>}
        </motion.div>
        <button onClick={() => setCollapsed((value) => !value)} className="rounded-lg border border-white/20 p-1.5 text-white transition-colors hover:bg-white hover:text-black" title={collapsed ? 'Open sidebar' : 'Close sidebar'}>
          <svg className={`h-4 w-4 transition-transform ${collapsed ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        </div>
      </div>

      {/* Navigation */}
      <nav className="relative flex-1 px-3 py-4 space-y-1">
        {menuItems.map((item, idx) => {
          const active = isActive(item.href)
          return (
            <Link
              key={idx}
              href={item.href}
              className={`group flex items-center gap-3 rounded-lg px-3 py-2.5 text-[13px] font-black transition-all duration-300 ${
                active
                  ? 'text-black bg-white shadow-lg shadow-white/10'
                  : 'text-white hover:bg-white/10 hover:translate-x-1'
              }`}
              title={item.label}
            >
              <span className="transition-transform duration-300 group-hover:scale-110">{item.icon}</span>
              {!collapsed && <span className="truncate">{item.label}</span>}
            </Link>
          )
        })}
      </nav>

      {/* Admin Badge */}
      {!collapsed && <div className="relative px-3 pb-3">
        <motion.div whileHover={{ y: -3 }} className="rounded-xl p-3 flex items-center gap-3 border border-white/10 bg-white/5 transition-colors hover:border-white/25">
          <div className="w-7 h-7 rounded-lg bg-white/10 flex items-center justify-center text-sm">
            👑
          </div>
          <div>
            <p className="text-white text-xs font-black">Admin Access</p>
            <p className="text-white text-[10px] font-bold">Full permissions</p>
          </div>
        </motion.div>
      </div>}

      {/* Logout */}
      <div className="relative px-3 pb-4 border-t border-white/10 pt-3">
        <motion.button
          whileHover={{ x: 3 }}
          whileTap={{ scale: 0.98 }}
          onClick={handleLogout}
          disabled={loggingOut}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13px] font-black text-white hover:text-red-300 hover:bg-white/10 transition-all"
          title="Logout"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
          {!collapsed && <span>{loggingOut ? 'Logging out...' : 'Logout'}</span>}
        </motion.button>
      </div>
    </aside>
  )
}
