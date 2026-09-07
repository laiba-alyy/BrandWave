'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { motion } from 'framer-motion'
import { createClient } from '@/lib/supabase'
import AdminSidebar from '@/components/admin/AdminSidebar'
import { isAdmin } from '@/lib/rbac'
import Link from 'next/link'

interface User {
  id: string
  role: 'admin' | 'user'
}

interface Stats {
  totalUsers: number
  totalBusinesses: number
  activeUsers: number
}

export default function AdminDashboard() {
  const router = useRouter()
  const supabase = createClient()
  const [user, setUser] = useState<User | null>(null)
  const [stats, setStats] = useState<Stats>({ totalUsers: 0, totalBusinesses: 0, activeUsers: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [loggingOut, setLoggingOut] = useState(false)

  useEffect(() => {
    const checkAccess = async () => {
      try {
        const { data: { session } } = await supabase.auth.getSession()
        if (!session) { router.push('/admin-login'); return }
        const { data: userData, error: userError } = await supabase.from('users').select('id, role').eq('id', session.user.id).single()
        if (userError) throw userError
        if (!isAdmin(userData.role)) { router.push('/business'); return }
        setUser(userData)
        const { count: totalUsers } = await supabase.from('users').select('*', { count: 'exact', head: true })
        const { count: businessUsers } = await supabase.from('users').select('*', { count: 'exact', head: true }).eq('role', 'user')
        setStats({ totalUsers: totalUsers || 0, totalBusinesses: businessUsers || 0, activeUsers: Math.floor((businessUsers || 0) * 0.75) })
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load dashboard')
      } finally {
        setLoading(false)
      }
    }
    checkAccess()
  }, [router, supabase])

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-white">
        <div className="w-10 h-10 border-2 border-black border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (error || !user) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-white">
        <div className="text-center">
          <p className="text-red-400 font-bold mb-4">{error || 'Unauthorized'}</p>
          <button onClick={() => router.push('/admin-login')} className="px-6 py-2 rounded-lg text-white text-sm font-semibold bg-black hover:bg-gray-800 transition-all">
            Back to Login
          </button>
        </div>
      </div>
    )
  }

  const statCards = [
    { label: 'Total Users', value: stats.totalUsers, icon: '👥', color: '#7C3AED', bg: 'rgba(124,58,237,0.1)', border: 'rgba(124,58,237,0.2)' },
    { label: 'Business Owners', value: stats.totalBusinesses, icon: '🏢', color: '#10B981', bg: 'rgba(16,185,129,0.1)', border: 'rgba(16,185,129,0.2)' },
    { label: 'Active Users', value: stats.activeUsers, icon: '✅', color: '#3B82F6', bg: 'rgba(59,130,246,0.1)', border: 'rgba(59,130,246,0.2)' },
  ]

  const quickActions = [
    { icon: '👥', title: 'Manage Users', desc: 'View and manage all platform users', href: '/admin/users', color: '#7C3AED' },
    { icon: '📋', title: 'Activity Logs', desc: 'Monitor system activity and events', href: '/admin/logs', color: '#10B981' },
  ]

  const handleLogout = async () => {
    setLoggingOut(true)
    await supabase.auth.signOut()
    router.push('/admin-login')
  }

  return (
    <main className="flex min-h-screen bg-white">
      <AdminSidebar />

      <div className="flex-1 p-8 text-black transition-[margin] duration-300" style={{ marginLeft: 'var(--admin-sidebar-width, 240px)' }}>
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>

          {/* Header */}
          <div className="flex items-center justify-between mb-8">
            <div>
              <h1 className="text-3xl font-black text-black mb-1">Admin Dashboard</h1>
              <p className="text-gray-800 text-sm font-bold">Monitor and manage your BrandWave platform</p>
            </div>
            <motion.button
              whileHover={{ y: -2 }}
              whileTap={{ scale: 0.98 }}
              onClick={handleLogout}
              disabled={loggingOut}
              className="px-5 py-2.5 rounded-xl text-sm font-bold bg-black text-white shadow-sm hover:bg-gray-800 disabled:opacity-50 transition-all"
            >
              {loggingOut ? 'Logging out...' : 'Logout'}
            </motion.button>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
            {statCards.map((card, idx) => (
              <motion.div key={idx} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.1 }}
                whileHover={{ y: -6, scale: 1.02 }}
                className="rounded-2xl p-6 bg-white border border-gray-200 shadow-sm hover:shadow-xl hover:border-black/20 transition-all"
              >
                <div className="flex items-center justify-between mb-4">
                  <span className="text-2xl">{card.icon}</span>
                  <span className="text-xs font-bold px-2 py-1 rounded-full"
                    style={{ backgroundColor: card.bg, color: card.color, border: `1px solid ${card.border}` }}>
                    Active
                  </span>
                </div>
                <p className="text-4xl font-black text-black mb-1">{card.value}</p>
                <p className="text-gray-800 text-sm font-bold">{card.label}</p>
              </motion.div>
            ))}
          </div>

          {/* Quick Actions */}
          <div className="rounded-2xl p-6 bg-white border border-gray-200 shadow-sm">
            <h2 className="text-lg font-bold text-black mb-5">Quick Actions</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {quickActions.map((action, idx) => (
                <Link key={idx} href={action.href}>
                  <motion.div whileHover={{ y: -4, x: 3, scale: 1.01 }} whileTap={{ scale: 0.98 }}
                    className="group flex items-center gap-4 p-5 rounded-xl cursor-pointer transition-all bg-gray-50 border border-gray-200 hover:bg-black hover:border-black hover:shadow-xl">
                    <div className="w-12 h-12 rounded-xl flex items-center justify-center text-2xl flex-shrink-0 bg-white border border-gray-200 group-hover:scale-110 transition-transform">
                      {action.icon}
                    </div>
                    <div>
                      <p className="text-black group-hover:text-white font-bold text-sm">{action.title}</p>
                      <p className="text-gray-800 group-hover:text-white text-sm font-bold mt-0.5">{action.desc}</p>
                    </div>
                    <svg className="w-4 h-4 text-gray-800 group-hover:text-white ml-auto group-hover:translate-x-1 transition-all" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </motion.div>
                </Link>
              ))}
            </div>
          </div>
        </motion.div>
      </div>
    </main>
  )
}
