'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase'
import { useEffect, useState } from 'react'

interface SidebarProps {
  user?: {
    email?: string
    business_name?: string
  }
}

interface SubMenuItem {
  label: string
  href: string
  exact?: boolean
}

interface MenuItem {
  icon: React.ReactNode
  label: string
  href: string
  children?: SubMenuItem[]
}

const menuItems: MenuItem[] = [
  {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
      </svg>
    ),
    label: 'Dashboard',
    href: '/business',
  },
  {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
      </svg>
    ),
    label: 'Data Scraping',
    href: '/business/scraping',
  },
  {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
      </svg>
    ),
    label: 'AI Ad Generator',
    href: "/business/ads-generation"
  },
  {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
      </svg>
    ),
    label: 'AI Video Ads',
    href: '/business/video-ads',
    children: [
      { label: 'Create Video', href: '/business/video-ads', exact: true },
      { label: 'Video Gallery', href: '/business/video-ads/gallery' },
    ],
  },
  {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11 3.055A9.001 9.001 0 1020.945 13H11V3.055z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20.488 9H15V3.512A9.025 9.025 0 0120.488 9z" />
      </svg>
    ),
    label: 'SEO Optimization',
    href: '/business/seo',
  },
  {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    label: 'Sentiment Analysis',
    href: '/business/sentiment',
  },
  {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
      </svg>
    ),
    label: 'Brand Insights',
    href: '/business/improvement',
  },
  {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
      </svg>
    ),
    label: 'Chatbot',
    href: '/business/chatbot',
    children: [
      { label: 'My Bots', href: '/business/chatbot', exact: true },
      { label: 'Conversations', href: '/business/chatbot/conversations' },
    ],
  },
  /*
   * "Automation" (/business/automation) aur "Reports" (/business/reports)
   * yahan se hata diye gaye hain — un dono ka koi page app/business ke andar
   * mojood nahi tha, is liye click karne par sidhe 404 milta tha. Jab ye
   * modules banein, entries wapas add kar dena.
   */
  {
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
    label: 'Settings',
    href: '/profile',
  },
]

export default function Sidebar({ user }: SidebarProps) {
  const pathname = usePathname()
  const router = useRouter()
  const supabase = createClient()
  const [loggingOut, setLoggingOut] = useState(false)
  const [collapsed, setCollapsed] = useState(false)

  useEffect(() => {
    const width = collapsed ? '76px' : '240px'
    document.documentElement.style.setProperty('--dashboard-sidebar-width', width)
  }, [collapsed])

  const handleLogout = async () => {
    setLoggingOut(true)
    await supabase.auth.signOut()
    router.push('/')
  }

  const isActive = (href: string) => {
    // '/business' har /business/* ka prefix hai, to startsWith use karne par
    // Dashboard HAR module page par highlighted reh jata. Ye entry sirf apne
    // exact route par active hoti hai.
    if (href === '/business') return pathname === '/business'
    return pathname.startsWith(href)
  }

  /**
   * Sub-link tabhi active hai jab uska href match kare AUR koi sibling zyada
   * specific match na kare — warna "My Bots" (/business/chatbot) har nested
   * route par highlight ho jata, chahe Conversations khuli ho.
   */
  const isChildActive = (siblings: SubMenuItem[], child: SubMenuItem) => {
    const matches = (item: SubMenuItem) =>
      item.exact ? pathname === item.href : pathname.startsWith(item.href)

    if (!pathname.startsWith(child.href)) return false

    const bestMatch = siblings
      .filter((s) => pathname.startsWith(s.href))
      .sort((a, b) => b.href.length - a.href.length)[0]

    if (bestMatch && bestMatch.href !== child.href) return false
    return child.exact ? matches(child) || pathname.startsWith(`${child.href}/`) : true
  }

  return (
    <aside
      className={`fixed top-0 left-0 z-40 flex h-full flex-col transition-all duration-300 ${collapsed ? 'w-[76px]' : 'w-[240px]'}`}
      style={{ backgroundColor: '#000000' }}
    >
      {/* Logo */}
      <div className="px-4 py-5">
        <div className="flex items-center justify-between gap-2">
        <Link href="/business/scraping" className="flex min-w-0 items-center gap-2.5">
          <div className="w-7 h-7 bg-white rounded-lg flex items-center justify-center flex-shrink-0">
            <svg className="w-4 h-4" fill="none" stroke="#000000" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          {!collapsed && <span className="truncate text-sm font-black text-white">BrandWave</span>}
        </Link>
        <button onClick={() => setCollapsed((value) => !value)} className="rounded-lg border border-white/20 p-1.5 text-white transition-colors hover:bg-white hover:text-black" title={collapsed ? 'Open sidebar' : 'Close sidebar'}>
          <svg className={`h-4 w-4 transition-transform ${collapsed ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-2 overflow-y-auto space-y-0.5">
        {menuItems.map((item, idx) => {
          const active = isActive(item.href)
          const showChildren = !collapsed && item.children && active

          return (
            <div key={idx}>
              <Link
                href={item.href}
                className="group flex items-center gap-2 text-[13px] font-black"
                title={item.label}
              >
                <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors ${
                  active
                    ? 'bg-[#f0a63c] text-black hover:bg-[#e59a2c]'
                    : 'text-white hover:bg-white/10'
                }`}>
                  {item.icon}
                </span>
                {!collapsed && (
                  <span className={`flex min-h-9 min-w-0 flex-1 items-center rounded-lg px-3 py-2 transition-colors ${
                    active
                      ? 'bg-[#f0a63c] text-black hover:bg-[#e59a2c]'
                      : 'text-white hover:bg-white/10'
                  }`}>
                    <span className="truncate">{item.label}</span>
                  </span>
                )}
              </Link>

              {showChildren && (
                <div className="mt-0.5 mb-1 ml-[26px] border-l border-white/15 pl-2 space-y-0.5">
                  {item.children!.map((child) => (
                    <Link
                      key={child.href}
                      href={child.href}
                      className={`block rounded-lg px-3 py-2 text-[12px] font-bold transition-all duration-150 ${
                        isChildActive(item.children!, child)
                          ? 'bg-[#f0a63c] text-black'
                          : 'text-white hover:bg-white/10'
                      }`}
                      title={child.label}
                    >
                      <span className="truncate">{child.label}</span>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </nav>

      {/* User Profile at bottom */}
      <div
        className="px-3 pb-5 pt-3 border-t border-white/10"
      >
        <div
          className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-white/5 transition-colors cursor-pointer"
          onClick={() => router.push('/profile')}
        >
          <div className="w-7 h-7 rounded-full bg-white/15 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
            {(user?.business_name || user?.email || 'U')[0].toUpperCase()}
          </div>
          {!collapsed && <div className="flex-1 min-w-0">
            <p className="text-white text-[12px] font-semibold truncate">
              {user?.business_name || 'Business Owner'}
            </p>
            <p className="text-white text-[10px] font-bold truncate">
              {user?.email || ''}
            </p>
          </div>}
          <button
            onClick={(e) => {
              e.stopPropagation()
              handleLogout()
            }}
            disabled={loggingOut}
            className="text-white transition-colors p-1 flex-shrink-0 hover:text-white/80"
            title="Logout"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
          </button>
        </div>
      </div>
    </aside>
  )
}
