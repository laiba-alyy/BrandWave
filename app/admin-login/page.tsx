'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase'
import Link from 'next/link'
import { motion } from 'framer-motion'

export default function AdminLogin() {
  const router = useRouter()
  const supabase = createClient()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [showPassword, setShowPassword] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      setLoading(true)
      setError('')
      const { data, error: signInError } = await supabase.auth.signInWithPassword({ email, password })
      if (signInError) throw signInError
      const { data: userData } = await supabase
        .from('users').select('role').eq('id', data.user.id).single()
      if (userData?.role !== 'admin') throw new Error('Only admins can access this area')
      router.push('/admin')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
      setLoading(false)
    }
  }

  const handleGoogle = async () => {
    try {
      setLoading(true)
      sessionStorage.setItem('selectedRole', 'admin')
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: `${window.location.origin}/auth/callback`,
          queryParams: { prompt: 'select_account' },
        },
      })
      if (error) throw error
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Google login failed')
      setLoading(false)
    }
  }

  return (
    <main className="min-h-screen flex" style={{ backgroundColor: '#000000' }}>

      {/* Left Panel — Black Branding */}
      <div
        className="hidden lg:flex lg:w-5/12 flex-col justify-between p-12 relative overflow-hidden"
        style={{ backgroundColor: '#000000' }}
      >
        {/* Geometric SVG Background */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <svg
            className="absolute top-0 right-0 w-full h-full opacity-20"
            viewBox="0 0 400 600"
            fill="none"
          >
            <polygon points="200,50 380,300 200,550 20,300" stroke="white" strokeWidth="0.5" fill="none" />
            <polygon points="200,100 340,300 200,500 60,300" stroke="white" strokeWidth="0.5" fill="none" />
            <polygon points="200,150 300,300 200,450 100,300" stroke="white" strokeWidth="0.5" fill="none" />
            <line x1="200" y1="50" x2="200" y2="550" stroke="white" strokeWidth="0.3" />
            <line x1="20" y1="300" x2="380" y2="300" stroke="white" strokeWidth="0.3" />
            <circle cx="200" cy="300" r="80" stroke="white" strokeWidth="0.5" fill="none" />
            <circle cx="200" cy="300" r="140" stroke="white" strokeWidth="0.3" fill="none" />
          </svg>
        </div>

        {/* Logo */}
        <div className="relative z-10">
          <Link href="/" className="flex items-center gap-2.5 mb-16">
            <div className="w-8 h-8 bg-white rounded-lg flex items-center justify-center">
              <svg className="w-4 h-4" fill="none" stroke="#000" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <span className="text-white font-bold text-lg">BrandWave</span>
          </Link>

          <h1 className="text-4xl font-black text-white leading-tight mb-4">
            Admin
            <br />
            Control Panel
          </h1>
          <p className="text-white text-sm font-bold leading-relaxed mb-8 max-w-xs">
            Restricted access. Only authorized administrators can sign in to this panel.
          </p>

          <div className="space-y-3">
            {[
              { icon: '👥', text: 'Manage all users' },
              { icon: '📋', text: 'View activity logs' },
              { icon: '⚙️', text: 'System settings' },
              { icon: '📊', text: 'Full platform analytics' },
            ].map((item, i) => (
              <div
                key={i}
                className="flex items-center gap-3 p-3 rounded-xl border border-white/10 bg-white/5"
              >
                <span className="text-base">{item.icon}</span>
                <span className="text-white text-sm font-bold">{item.text}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Bottom Warning Card */}
        <div className="relative z-10 p-4 rounded-xl border border-red-500/20 bg-red-500/5 flex items-start gap-3">
          <svg
            className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <p className="text-red-200 text-xs font-bold leading-relaxed">
            This area is restricted to BrandWave administrators only. Unauthorized access attempts are logged.
          </p>
        </div>
      </div>

      {/* Right Panel — Form */}
      <div className="flex-1 flex items-center justify-center p-8 bg-white">
        <div className="w-full max-w-sm">
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}>

            {/* Header */}
            <div className="mb-7">
              <h2 className="text-2xl font-black text-gray-900 mb-1">Admin Login</h2>
              <p className="text-gray-800 text-sm font-bold">Sign in to your admin dashboard</p>
            </div>

            {/* Error */}
            {error && (
              <div className="mb-5 p-3 rounded-lg text-xs font-bold text-red-600 bg-red-50 border border-red-200">
                {error}
              </div>
            )}

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-4">

              {/* Email */}
              <div>
                <label className="block text-sm font-black text-black mb-1.5">
                  Email Address
                </label>
                <div className="relative">
                  <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-800"
                    fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                      d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                  <input
                    type="email"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    placeholder="admin@example.com"
                    required
                    className="w-full pl-9 pr-4 py-3 text-sm font-bold border border-gray-300 rounded-lg bg-gray-50 text-black placeholder-gray-500 focus:outline-none focus:border-black focus:bg-white transition-all"
                  />
                </div>
              </div>

              {/* Password */}
              <div>
                <label className="block text-sm font-black text-black mb-1.5">
                  Password
                </label>
                <div className="relative">
                  <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-800"
                    fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                      d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                  </svg>
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    placeholder="••••••••••"
                    required
                    className="w-full pl-9 pr-10 py-3 text-sm font-bold border border-gray-300 rounded-lg bg-gray-50 text-black placeholder-gray-500 focus:outline-none focus:border-black focus:bg-white transition-all"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-800 hover:text-gray-600 transition-colors"
                  >
                    {showPassword ? (
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                          d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                      </svg>
                    ) : (
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                          d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                          d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>

              {/* Submit */}
              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 bg-black text-white font-black rounded-lg text-sm hover:bg-gray-900 transition-all disabled:opacity-50 mt-2"
              >
                {loading ? 'Signing in...' : 'Sign In'}
              </button>
            </form>

            {/* Divider */}
            <div className="relative my-5">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-200" />
              </div>
              <div className="relative flex justify-center text-xs">
                <span className="px-2 bg-white text-gray-800 font-bold">or continue with</span>
              </div>
            </div>
            {/* Google */}
            <button
              onClick={handleGoogle}
              disabled={loading}
              className="w-full py-3 font-bold rounded-lg text-sm border border-gray-300 hover:bg-gray-50 transition-all flex items-center justify-center gap-3 text-black disabled:opacity-50"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.77 3.28-8.03z" />
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-1.01.68-2.3 1.09-3.71 1.09-2.85 0-5.27-1.925-6.14-4.5H3.36v2.86C5.08 20.7 8.41 23 12 23z" />
                <path fill="#FBBC04" d="M5.84 14.09c-.22-.68-.35-1.41-.35-2.09s.13-1.41.35-2.09V6.62H3.36C2.43 8.64 2 10.74 2 12c0 1.26.43 2.36 1.36 3.38l2.48-1.29z" />
                <path fill="#EA4335" d="M12 5.38c1.4 0 2.67.47 3.66 1.45l2.73-2.73C17.46 2.09 14.97 1 12 1c-3.59 0-6.92 2.3-8.64 5.62l2.48 1.29c.87-2.58 3.29-4.53 6.16-4.53z" />
              </svg>
              {loading ? 'Redirecting...' : 'Continue with Google'}
            </button>

            {/* Back */}
            <p className="text-center text-sm font-bold text-gray-800 mt-6">
              Not an admin?{' '}
              <Link href="/login" className="text-gray-900 font-semibold hover:underline">
                Go back
              </Link>
            </p>
          </motion.div>
        </div>
      </div>
    </main>
  )
}

