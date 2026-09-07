/* eslint-disable @typescript-eslint/no-explicit-any */
'use client'

import { useState, useEffect, useMemo, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { motion } from 'framer-motion'
import { createClient } from '@/lib/supabase'
import { authHeaders } from '@/lib/authHeaders'
import { useActiveBrand } from '@/lib/useActiveBrand'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function ProfilePage() {
  const router = useRouter()
  const supabase = useMemo(() => createClient(), [])
  // user/userId ab shared context se — har navigation par dobara fetch nahi hote
  const { user: ctxUser, userId: ctxUserId } = useActiveBrand()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [user, setUser] = useState<any>(null)
  const [userId, setUserId] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [savedSection, setSavedSection] = useState<string | null>(null)
  const [uploadingAvatar, setUploadingAvatar] = useState(false)
  const [activeTab, setActiveTab] = useState('personal')
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deleteEmail, setDeleteEmail] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [changingPassword, setChangingPassword] = useState(false)
  const [passwordData, setPasswordData] = useState({ current: '', new: '', confirm: '' })
  const [passwordError, setPasswordError] = useState('')
  const [passwordSuccess, setPasswordSuccess] = useState(false)

  const [profile, setProfile] = useState({
    full_name: '',
    phone_number: '',
    avatar_url: '',
    business_name: '',
    business_role: '',
    notify_escalation: true,
    notify_weekly_report: true,
    notify_new_conversation: true,
    notify_marketing_tips: false,
    notification_frequency: 'instant',
    two_factor_enabled: false,
    timezone: '',
  })

  /*
   * `users` row ab context se aati hai (ActiveBrandProvider, ek dafa) — yahan
   * se wo query nikal chuki hai. getSession() baaqi hai kyunke is page ko
   * `auth_provider` chahiye jo sirf session par hota hai; wo local storage se
   * padhta hai, network par nahi jata.
   */
  useEffect(() => {
    if (!ctxUserId) return
    const init = async () => {
      const { data: { session } } = await supabase.auth.getSession()
      setUser({
        email: ctxUser?.email ?? undefined,
        business_name: ctxUser?.business_name ?? undefined,
        auth_provider: session?.user.app_metadata?.provider || 'email',
      })
      setUserId(ctxUserId)

      try {
        const res = await fetch(`${API_URL}/api/profile/${ctxUserId}`, {
          headers: await authHeaders(),
        })
        if (res.ok) {
          const data = await res.json()
          if (data.data) {
            setProfile(prev => ({ ...prev, ...data.data }))
            if (!data.data.business_name && ctxUser?.business_name) {
              setProfile(prev => ({ ...prev, business_name: ctxUser.business_name as string }))
            }
          }
        }
      } catch {}
      setLoading(false)
    }
    init()
  }, [ctxUserId, ctxUser, supabase])

  const handleSaveProfile = async () => {
    setSaving(true)
    try {
      const res = await fetch(`${API_URL}/api/profile/${userId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
        body: JSON.stringify({
          full_name: profile.full_name,
          phone_number: profile.phone_number,
          business_name: profile.business_name,
          business_role: profile.business_role,
          timezone: profile.timezone,
        }),
      })
      if (res.ok) {
        setSavedSection('personal')
        setTimeout(() => setSavedSection(null), 2000)
      }
    } catch {}
    setSaving(false)
  }

  const handleSaveNotifications = async () => {
    setSaving(true)
    try {
      const res = await fetch(`${API_URL}/api/profile/${userId}/notifications`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
        body: JSON.stringify({
          notify_escalation: profile.notify_escalation,
          notify_weekly_report: profile.notify_weekly_report,
          notify_new_conversation: profile.notify_new_conversation,
          notify_marketing_tips: profile.notify_marketing_tips,
          notification_frequency: profile.notification_frequency,
        }),
      })
      if (res.ok) {
        setSavedSection('notifications')
        setTimeout(() => setSavedSection(null), 2000)
      }
    } catch {}
    setSaving(false)
  }

  const handleAvatarUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadingAvatar(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch(`${API_URL}/api/profile/${userId}/avatar`, {
        method: 'POST',
        headers: { ...(await authHeaders()) },
        body: formData,
      })
      if (res.ok) {
        const data = await res.json()
        setProfile(prev => ({ ...prev, avatar_url: data.avatar_url }))
      }
    } catch {}
    setUploadingAvatar(false)
  }

  const handleRemoveAvatar = async () => {
    try {
      const res = await fetch(`${API_URL}/api/profile/${userId}/avatar`, {
        method: 'DELETE',
        headers: await authHeaders(),
      })
      if (res.ok) setProfile(prev => ({ ...prev, avatar_url: '' }))
    } catch {}
  }

  const handleChangePassword = async () => {
    setPasswordError('')
    setPasswordSuccess(false)

    if (passwordData.new !== passwordData.confirm) {
      setPasswordError('New passwords do not match')
      return
    }
    if (passwordData.new.length < 6) {
      setPasswordError('Password must be at least 6 characters')
      return
    }

    setChangingPassword(true)
    try {
      const { error } = await supabase.auth.updateUser({ password: passwordData.new })
      if (error) {
        setPasswordError(error.message)
      } else {
        setPasswordSuccess(true)
        setPasswordData({ current: '', new: '', confirm: '' })
        setTimeout(() => setPasswordSuccess(false), 3000)
      }
    } catch {}
    setChangingPassword(false)
  }

  const handleDeleteAccount = async () => {
    if (deleteEmail !== user?.email) return
    setDeleting(true)
    try {
      const { data: { session } } = await supabase.auth.getSession()
      const res = await fetch(`${API_URL}/api/auth/delete-account/${userId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${session?.access_token}`,
        },
        body: JSON.stringify({ dry_run: false }),
      })
      if (res.ok) {
        await supabase.auth.signOut()
        router.push('/login')
      } else {
        const data = await res.json()
        alert(data.detail || 'Deletion failed')
      }
    } catch {}
    setDeleting(false)
  }

  const getInitials = () => {
    if (profile.full_name) {
      return profile.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
    }
    return user?.email?.[0]?.toUpperCase() || 'U'
  }

  const tabs = [
    { id: 'personal', label: 'Personal Info' },
    { id: 'account', label: 'Account Settings' },
    { id: 'notifications', label: 'Notifications' },
    { id: 'danger', label: 'Danger Zone' },
  ]

  if (loading) {
    return (
      <main className="min-h-screen bg-white">
        <div className="flex items-center justify-center py-24">
          <div className="w-8 h-8 border-2 border-black border-t-transparent rounded-full animate-spin" />
        </div>
      </main>
    )
  }

  return (
    <main className="min-h-screen bg-gray-50">

      <div>
        {/* Header */}
        <div className="bg-black text-white px-8 py-10">
          <div className="max-w-4xl mx-auto flex items-center gap-6">
            {/* Avatar */}
            <div className="relative group">
              {profile.avatar_url ? (
                <img
                  src={profile.avatar_url}
                  alt="Avatar"
                  className="w-20 h-20 rounded-full object-cover border-2 border-white"
                />
              ) : (
                <div className="w-20 h-20 rounded-full bg-white text-black flex items-center justify-center text-2xl font-black">
                  {getInitials()}
                </div>
              )}
              <button
                onClick={() => fileInputRef.current?.click()}
                className="absolute inset-0 rounded-full bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"
              >
                <span className="text-white text-xs font-bold">
                  {uploadingAvatar ? '...' : 'Edit'}
                </span>
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".jpg,.jpeg,.png,.webp"
                className="hidden"
                onChange={handleAvatarUpload}
              />
            </div>

            <div>
              <h1 className="text-2xl font-black">
                {profile.full_name || 'Set your name'}
              </h1>
              <p className="text-white/70 text-sm mt-1">{user?.email}</p>
              <div className="flex items-center gap-2 mt-2">
                {profile.business_role && (
                  <span className="text-xs px-3 py-1 rounded-full bg-white/20 text-white font-medium">
                    {profile.business_role}
                  </span>
                )}
                <span className="text-xs px-3 py-1 rounded-full bg-green-500/20 text-green-300 font-medium">
                  Verified
                </span>
                {user?.auth_provider === 'google' && (
                  <span className="text-xs px-3 py-1 rounded-full bg-blue-500/20 text-blue-300 font-medium">
                    Google Connected
                  </span>
                )}
              </div>
            </div>

            {profile.avatar_url && (
              <button
                onClick={handleRemoveAvatar}
                className="ml-auto text-xs text-white/50 hover:text-white/80 underline"
              >
                Remove photo
              </button>
            )}
          </div>
        </div>

        {/* Tabs */}
        <div className="border-b border-gray-200 bg-white sticky top-0 z-10">
          <div className="max-w-4xl mx-auto flex">
            {tabs.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-6 py-3 text-sm font-semibold border-b-2 transition-all ${
                  activeTab === tab.id
                    ? 'border-black text-black'
                    : 'border-transparent text-gray-400 hover:text-gray-700'
                } ${tab.id === 'danger' ? 'ml-auto text-red-400 hover:text-red-600' : ''}`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        <div className="max-w-4xl mx-auto p-8">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
          >
            {/* ── Personal Info ── */}
            {activeTab === 'personal' && (
              <div className="space-y-6">
                <div>
                  <h2 className="text-lg font-bold text-gray-900 mb-1">Personal Information</h2>
                  <p className="text-gray-500 text-sm">Update your personal details and business information</p>
                </div>

                <div className="bg-white rounded-2xl border border-gray-200 p-6 space-y-5">
                  {/* Full Name */}
                  <div>
                    <label className="text-sm font-semibold text-gray-700 block mb-1">Full Name</label>
                    <input
                      type="text"
                      value={profile.full_name || ''}
                      onChange={e => setProfile(p => ({ ...p, full_name: e.target.value }))}
                      placeholder="Enter your full name"
                      className="w-full px-4 py-3 rounded-xl border border-gray-200 text-sm focus:outline-none focus:border-black transition-colors"
                    />
                  </div>

                  {/* Email — Read Only */}
                  <div>
                    <label className="text-sm font-semibold text-gray-700 block mb-1">Email Address</label>
                    <div className="w-full px-4 py-3 rounded-xl bg-gray-50 border border-gray-100 text-sm text-gray-500 flex items-center justify-between">
                      <span>{user?.email}</span>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700 font-medium">Verified</span>
                    </div>
                  </div>

                  {/* Phone */}
                  <div>
                    <label className="text-sm font-semibold text-gray-700 block mb-1">Phone Number</label>
                    <input
                      type="tel"
                      value={profile.phone_number || ''}
                      onChange={e => setProfile(p => ({ ...p, phone_number: e.target.value }))}
                      placeholder="+92 3XX XXXXXXX"
                      className="w-full px-4 py-3 rounded-xl border border-gray-200 text-sm focus:outline-none focus:border-black transition-colors"
                    />
                  </div>

                  {/* Business Name */}
                  <div>
                    <label className="text-sm font-semibold text-gray-700 block mb-1">Business Name</label>
                    <input
                      type="text"
                      value={profile.business_name || ''}
                      onChange={e => setProfile(p => ({ ...p, business_name: e.target.value }))}
                      placeholder="Your business name"
                      className="w-full px-4 py-3 rounded-xl border border-gray-200 text-sm focus:outline-none focus:border-black transition-colors"
                    />
                  </div>

                  {/* Business Role */}
                  <div>
                    <label className="text-sm font-semibold text-gray-700 block mb-1">Business Role</label>
                    <select
                      value={profile.business_role || ''}
                      onChange={e => setProfile(p => ({ ...p, business_role: e.target.value }))}
                      className="w-full px-4 py-3 rounded-xl border border-gray-200 text-sm focus:outline-none focus:border-black transition-colors bg-white"
                    >
                      <option value="">Select your role</option>
                      <option value="Owner">Business Owner</option>
                      <option value="Manager">Manager</option>
                      <option value="Marketing Head">Marketing Head</option>
                      <option value="Developer">Developer</option>
                      <option value="Other">Other</option>
                    </select>
                  </div>

                  {/* Timezone */}
                  <div>
                    <label className="text-sm font-semibold text-gray-700 block mb-1">Timezone</label>
                    <select
                      value={profile.timezone || ''}
                      onChange={e => setProfile(p => ({ ...p, timezone: e.target.value }))}
                      className="w-full px-4 py-3 rounded-xl border border-gray-200 text-sm focus:outline-none focus:border-black transition-colors bg-white"
                    >
                      <option value="">Select timezone</option>
                      <option value="Asia/Karachi">Pakistan (PKT, UTC+5)</option>
                      <option value="Asia/Dubai">UAE (GST, UTC+4)</option>
                      <option value="Asia/Kolkata">India (IST, UTC+5:30)</option>
                      <option value="Europe/London">UK (GMT/BST)</option>
                      <option value="America/New_York">US Eastern (EST/EDT)</option>
                      <option value="America/Los_Angeles">US Pacific (PST/PDT)</option>
                    </select>
                  </div>

                  {/* Save */}
                  <div className="flex items-center justify-between pt-2">
                    <motion.button
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                      onClick={handleSaveProfile}
                      disabled={saving}
                      className={`px-6 py-3 rounded-xl text-sm font-bold transition-all ${
                        savedSection === 'personal'
                          ? 'bg-green-600 text-white'
                          : 'bg-black text-white hover:bg-gray-900'
                      } disabled:opacity-50`}
                    >
                      {saving ? 'Saving...' : savedSection === 'personal' ? '✓ Saved!' : 'Save Changes'}
                    </motion.button>
                  </div>
                </div>
              </div>
            )}

            {/* ── Account Settings ── */}
            {activeTab === 'account' && (
              <div className="space-y-6">
                <div>
                  <h2 className="text-lg font-bold text-gray-900 mb-1">Account Settings</h2>
                  <p className="text-gray-500 text-sm">Manage your password and security settings</p>
                </div>

                {/* Change Password */}
                <div className="bg-white rounded-2xl border border-gray-200 p-6 space-y-4">
                  <h3 className="text-sm font-bold text-gray-900">Change Password</h3>

                  {user?.auth_provider === 'google' ? (
                    <div className="bg-blue-50 border border-blue-100 rounded-xl p-4">
                      <p className="text-sm text-blue-700">
                        Your account is connected via Google. Password is managed by your Google account.
                      </p>
                    </div>
                  ) : (
                    <>
                      <input
                        type="password"
                        placeholder="New password"
                        value={passwordData.new}
                        onChange={e => setPasswordData(p => ({ ...p, new: e.target.value }))}
                        className="w-full px-4 py-3 rounded-xl border border-gray-200 text-sm focus:outline-none focus:border-black"
                      />
                      <input
                        type="password"
                        placeholder="Confirm new password"
                        value={passwordData.confirm}
                        onChange={e => setPasswordData(p => ({ ...p, confirm: e.target.value }))}
                        className="w-full px-4 py-3 rounded-xl border border-gray-200 text-sm focus:outline-none focus:border-black"
                      />
                      {passwordError && (
                        <p className="text-red-500 text-xs font-medium">{passwordError}</p>
                      )}
                      {passwordSuccess && (
                        <p className="text-green-600 text-xs font-bold">✓ Password updated successfully!</p>
                      )}
                      <motion.button
                        whileHover={{ scale: 1.02 }}
                        onClick={handleChangePassword}
                        disabled={changingPassword}
                        className="px-5 py-2.5 bg-black text-white rounded-xl text-sm font-bold hover:bg-gray-900 disabled:opacity-50"
                      >
                        {changingPassword ? 'Updating...' : 'Update Password'}
                      </motion.button>
                    </>
                  )}
                </div>

                {/* Connected Accounts */}
                <div className="bg-white rounded-2xl border border-gray-200 p-6">
                  <h3 className="text-sm font-bold text-gray-900 mb-4">Connected Accounts</h3>
                  <div className="flex items-center justify-between p-4 rounded-xl bg-gray-50">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-white border border-gray-200 flex items-center justify-center">
                        <svg className="w-5 h-5" viewBox="0 0 24 24">
                          <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/>
                          <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                          <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                          <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                        </svg>
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-gray-900">Google</p>
                        <p className="text-xs text-gray-500">
                          {user?.auth_provider === 'google' ? 'Connected' : 'Not connected'}
                        </p>
                      </div>
                    </div>
                    <span className={`text-xs px-3 py-1 rounded-full font-medium ${
                      user?.auth_provider === 'google'
                        ? 'bg-green-100 text-green-700'
                        : 'bg-gray-100 text-gray-500'
                    }`}>
                      {user?.auth_provider === 'google' ? 'Active' : 'Inactive'}
                    </span>
                  </div>
                </div>

                {/* Two Factor */}
                <div className="bg-white rounded-2xl border border-gray-200 p-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-sm font-bold text-gray-900">Two-Factor Authentication</h3>
                      <p className="text-xs text-gray-500 mt-1">Add an extra layer of security to your account</p>
                    </div>
                    <button
                      className={`relative w-12 h-6 rounded-full transition-colors ${
                        profile.two_factor_enabled ? 'bg-black' : 'bg-gray-300'
                      }`}
                      onClick={() => setProfile(p => ({ ...p, two_factor_enabled: !p.two_factor_enabled }))}
                    >
                      <span className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                        profile.two_factor_enabled ? 'translate-x-6' : 'translate-x-0.5'
                      }`} />
                    </button>
                  </div>
                  {profile.two_factor_enabled && (
                    <div className="mt-4 p-4 bg-yellow-50 border border-yellow-100 rounded-xl">
                      <p className="text-xs text-yellow-700">
                        Two-factor authentication setup will be available in the next update.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── Notifications ── */}
            {activeTab === 'notifications' && (
              <div className="space-y-6">
                <div>
                  <h2 className="text-lg font-bold text-gray-900 mb-1">Notification Preferences</h2>
                  <p className="text-gray-500 text-sm">Control what notifications you receive</p>
                </div>

                <div className="bg-white rounded-2xl border border-gray-200 p-6 space-y-4">
                  <h3 className="text-sm font-bold text-gray-900 mb-2">Email Notifications</h3>

                  {[
                    { key: 'notify_escalation', label: 'Chatbot Escalation Alerts', desc: 'Get notified when a customer conversation needs human attention' },
                    { key: 'notify_weekly_report', label: 'Weekly SEO Report', desc: 'Receive a weekly summary of your SEO performance' },
                    { key: 'notify_new_conversation', label: 'New Conversation Alerts', desc: 'Get notified when a new customer starts a chat' },
                    { key: 'notify_marketing_tips', label: 'Marketing Tips & Updates', desc: 'Receive tips and platform update notifications' },
                  ].map(item => (
                    <div key={item.key} className="flex items-center justify-between py-3 border-b border-gray-50 last:border-0">
                      <div>
                        <p className="text-sm font-semibold text-gray-900">{item.label}</p>
                        <p className="text-xs text-gray-500 mt-0.5">{item.desc}</p>
                      </div>
                      <button
                        className={`relative w-12 h-6 rounded-full transition-colors ${
                          (profile as any)[item.key] ? 'bg-black' : 'bg-gray-300'
                        }`}
                        onClick={() => setProfile(p => ({ ...p, [item.key]: !(p as any)[item.key] }))}
                      >
                        <span className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                          (profile as any)[item.key] ? 'translate-x-6' : 'translate-x-0.5'
                        }`} />
                      </button>
                    </div>
                  ))}
                </div>

                {/* Frequency */}
                <div className="bg-white rounded-2xl border border-gray-200 p-6">
                  <h3 className="text-sm font-bold text-gray-900 mb-4">Notification Frequency</h3>
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      { value: 'instant', label: 'Instant', desc: 'Get notified immediately' },
                      { value: 'daily', label: 'Daily Digest', desc: 'Once per day summary' },
                      { value: 'weekly', label: 'Weekly Summary', desc: 'Once per week roundup' },
                    ].map(freq => (
                      <button
                        key={freq.value}
                        onClick={() => setProfile(p => ({ ...p, notification_frequency: freq.value }))}
                        className={`p-4 rounded-xl border text-left transition-all ${
                          profile.notification_frequency === freq.value
                            ? 'border-black bg-black text-white'
                            : 'border-gray-200 hover:border-gray-400'
                        }`}
                      >
                        <p className={`text-sm font-bold ${
                          profile.notification_frequency === freq.value ? 'text-white' : 'text-gray-900'
                        }`}>{freq.label}</p>
                        <p className={`text-xs mt-1 ${
                          profile.notification_frequency === freq.value ? 'text-white/70' : 'text-gray-500'
                        }`}>{freq.desc}</p>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Save */}
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={handleSaveNotifications}
                  disabled={saving}
                  className={`px-6 py-3 rounded-xl text-sm font-bold transition-all ${
                    savedSection === 'notifications'
                      ? 'bg-green-600 text-white'
                      : 'bg-black text-white hover:bg-gray-900'
                  } disabled:opacity-50`}
                >
                  {saving ? 'Saving...' : savedSection === 'notifications' ? '✓ Saved!' : 'Save Preferences'}
                </motion.button>
              </div>
            )}

            {/* ── Danger Zone ── */}
            {activeTab === 'danger' && (
              <div className="space-y-6">
                <div>
                  <h2 className="text-lg font-bold text-red-600 mb-1">Danger Zone</h2>
                  <p className="text-gray-500 text-sm">Irreversible actions — proceed with caution</p>
                </div>

                <div className="bg-white rounded-2xl border border-red-200 p-6 space-y-6">
                  {/* Delete Account */}
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-sm font-bold text-gray-900">Delete Account</h3>
                      <p className="text-xs text-gray-500 mt-1">
                        Permanently delete your account and all associated data including brand profiles,
                        SEO audits, chatbots, ads, and conversations. This cannot be undone.
                      </p>
                    </div>
                    <motion.button
                      whileHover={{ scale: 1.02 }}
                      onClick={() => setShowDeleteModal(true)}
                      className="px-5 py-2.5 bg-red-600 text-white rounded-xl text-sm font-bold hover:bg-red-700 shrink-0"
                    >
                      Delete Account
                    </motion.button>
                  </div>
                </div>
              </div>
            )}
          </motion.div>
        </div>

        {/* Delete Modal */}
        {showDeleteModal && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="bg-white rounded-2xl p-6 max-w-md w-full"
            >
              <h3 className="text-lg font-bold text-gray-900 mb-2">Delete Account</h3>
              <p className="text-sm text-gray-600 mb-4">
                This will permanently delete your account and ALL associated data:
              </p>
              <ul className="text-xs text-gray-500 space-y-1 mb-4 pl-4">
                <li>All brand profiles and scraped data</li>
                <li>All SEO audits, keywords, and blog articles</li>
                <li>All chatbot instances and conversations</li>
                <li>All generated advertisements</li>
                <li>Your user profile and settings</li>
              </ul>
              <p className="text-sm font-semibold text-gray-900 mb-2">
                Type <span className="text-red-600">{user?.email}</span> to confirm:
              </p>
              <input
                type="text"
                value={deleteEmail}
                onChange={e => setDeleteEmail(e.target.value)}
                placeholder="Enter your email"
                className="w-full px-4 py-3 rounded-xl border border-gray-200 text-sm mb-4 focus:outline-none focus:border-red-500"
              />
              <div className="flex gap-3">
                <button
                  onClick={() => { setShowDeleteModal(false); setDeleteEmail('') }}
                  className="flex-1 px-4 py-3 rounded-xl border border-gray-200 text-sm font-semibold text-gray-700 hover:bg-gray-50"
                >
                  Cancel
                </button>
                <motion.button
                  whileHover={{ scale: deleteEmail === user?.email ? 1.02 : 1 }}
                  onClick={handleDeleteAccount}
                  disabled={deleteEmail !== user?.email || deleting}
                  className="flex-1 px-4 py-3 rounded-xl bg-red-600 text-white text-sm font-bold disabled:opacity-30 hover:bg-red-700"
                >
                  {deleting ? 'Deleting...' : 'Permanently Delete'}
                </motion.button>
              </div>
            </motion.div>
          </div>
        )}
      </div>
    </main>
  )
}
