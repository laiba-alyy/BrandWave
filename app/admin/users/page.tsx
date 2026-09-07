'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { motion } from 'framer-motion'
import { createClient } from '@/lib/supabase'
import AdminSidebar from '@/components/admin/AdminSidebar'
import { isAdmin } from '@/lib/rbac'

interface UserData {
  id: string
  email: string
  business_name: string
  role: 'admin' | 'user'
  email_verified: boolean
  created_at: string
}

export default function UsersPage() {
  const router = useRouter()
  const supabase = createClient()
  const [users, setUsers] = useState<UserData[]>([])
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')

  useEffect(() => {
    const fetchUsers = async () => {
      try {
        const { data: { session } } = await supabase.auth.getSession()
        if (!session) { router.push('/admin-login'); return }
        const { data: userData } = await supabase.from('users').select('id, role').eq('id', session.user.id).single()
        if (!isAdmin(userData?.role)) { router.push('/business'); return }
        const { data: allUsers, error } = await supabase.from('users').select('*').order('created_at', { ascending: false })
        if (error) throw error
        setUsers(allUsers || [])
      } catch (err) {
        console.error('Error fetching users:', err)
      } finally {
        setLoading(false)
      }
    }
    fetchUsers()
  }, [router, supabase])

  const handleDeleteUser = async (userId: string, userEmail: string) => {
    if (!confirm(`Are you sure you want to delete ${userEmail}?`)) return
    try {
      setDeleting(userId)
      const { error } = await supabase.from('users').delete().eq('id', userId)
      if (error) throw error
      setUsers(users.filter(u => u.id !== userId))
    } catch (err) {
      console.error('Error deleting user:', err)
      alert('Failed to delete user')
    } finally {
      setDeleting(null)
    }
  }

  const filteredUsers = users.filter(u =>
    u.email.toLowerCase().includes(searchTerm.toLowerCase()) ||
    u.business_name?.toLowerCase().includes(searchTerm.toLowerCase())
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-white">
        <div className="w-10 h-10 border-2 border-black border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <main className="flex min-h-screen bg-white">
      <AdminSidebar />

      <div className="flex-1 p-8 text-black transition-[margin] duration-300" style={{ marginLeft: 'var(--admin-sidebar-width, 240px)' }}>
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>

          {/* Header */}
          <div className="flex items-center justify-between mb-8">
            <div>
              <h1 className="text-3xl font-black text-black mb-1">User Management</h1>
              <p className="text-gray-800 text-sm font-bold">Manage all BrandWave users</p>
            </div>
            <motion.div whileHover={{ y: -2 }} className="px-4 py-2 rounded-xl text-sm font-bold bg-black text-white shadow-sm">
              {users.length} Total Users
            </motion.div>
          </div>

          {/* Search */}
          <div className="mb-6 relative">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-800" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              placeholder="Search by email or business name..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              className="w-full pl-10 pr-4 py-3 rounded-xl text-sm text-black placeholder-gray-400 focus:outline-none transition-all bg-white border border-gray-200 shadow-sm focus:border-black focus:shadow-lg"
            />
          </div>

          {/* Table */}
          <div className="rounded-2xl overflow-hidden bg-white border border-gray-200 shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50">
                    {['Email', 'Business Name', 'Role', 'Verified', 'Joined', 'Actions'].map(h => (
                      <th key={h} className="px-5 py-4 text-left text-xs font-black uppercase tracking-wider text-black">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {filteredUsers.map((userData, idx) => (
                    <motion.tr
                      key={userData.id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: idx * 0.03 }}
                      whileHover={{ scale: 1.005 }}
                      className="hover:bg-gray-50 transition-colors"
                    >
                      <td className="px-5 py-4 text-sm text-black font-bold">{userData.email}</td>
                      <td className="px-5 py-4 text-sm font-bold text-black">{userData.business_name || '—'}</td>
                      <td className="px-5 py-4">
                        <span className="text-xs font-bold px-2.5 py-1 rounded-full"
                          style={userData.role === 'admin'
                            ? { backgroundColor: 'rgba(124,58,237,0.15)', color: '#A78BFA', border: '1px solid rgba(124,58,237,0.2)' }
                            : { backgroundColor: 'rgba(59,130,246,0.15)', color: '#60A5FA', border: '1px solid rgba(59,130,246,0.2)' }}>
                          {userData.role === 'admin' ? '👑 Admin' : '👤 User'}
                        </span>
                      </td>
                      <td className="px-5 py-4">
                        <span className="text-xs font-bold px-2.5 py-1 rounded-full"
                          style={userData.email_verified
                            ? { backgroundColor: 'rgba(16,185,129,0.15)', color: '#10B981', border: '1px solid rgba(16,185,129,0.2)' }
                            : { backgroundColor: 'rgba(239,68,68,0.15)', color: '#F87171', border: '1px solid rgba(239,68,68,0.2)' }}>
                          {userData.email_verified ? '✓ Verified' : '✗ Pending'}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-sm font-bold text-black">
                        {new Date(userData.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-5 py-4">
                        <motion.button
                          whileHover={{ scale: 1.05 }}
                          whileTap={{ scale: 0.95 }}
                          onClick={() => handleDeleteUser(userData.id, userData.email)}
                          disabled={deleting === userData.id}
                          className="text-xs font-semibold px-3 py-1.5 rounded-lg transition-all disabled:opacity-50"
                          style={{ backgroundColor: 'rgba(239,68,68,0.1)', color: '#F87171', border: '1px solid rgba(239,68,68,0.2)' }}
                        >
                          {deleting === userData.id ? 'Deleting...' : 'Delete'}
                        </motion.button>
                      </td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            </div>

            {filteredUsers.length === 0 && (
              <div className="text-center py-12">
                <p className="text-gray-800 text-sm font-bold">No users found</p>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="mt-4 flex items-center justify-between">
            <p className="text-gray-800 text-sm font-bold">
              Showing <span className="text-black font-semibold">{filteredUsers.length}</span> of{' '}
              <span className="text-black font-semibold">{users.length}</span> users
            </p>
          </div>
        </motion.div>
      </div>
    </main>
  )
}
