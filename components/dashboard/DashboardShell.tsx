'use client'

import { useEffect, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import Sidebar from '@/components/dashboard/Sidebar'
import { createClient } from '@/lib/supabase'
import { useActiveBrand } from '@/lib/useActiveBrand'

/**
 * Dashboard ka sthaayi (persistent) shell — sidebar + content column.
 *
 * ── Ye component LAYOUT mein render hota hai, page mein NAHI ──────────────
 * Pehle har page apne andar `<Sidebar />` render karta tha (11 pages). App
 * Router har navigation par page component ko unmount kar deta hai, to sidebar
 * bhi har click par mit kar dobara ban'ta tha: collapsed/expanded state reset
 * ho jati thi, aur poora shell dobara render hota tha bajaye sirf content ke.
 *
 * Layout React tree mein navigations ke DARMIYAN zinda rehta hai. Yahan rakhne
 * se sidebar ek hi dafa mount hota hai aur click par sirf `children` badalte
 * hain — yani navigation foran mehsoos hoti hai.
 *
 * ZAROORI: kisi page ya nested layout mein `<Sidebar />` dobara mat render
 * karna — do sidebars render honge aur ye poora faida khatam ho jayega.
 *
 * ── Auth guard bhi yahan ──────────────────────────────────────────────────
 * Pehle har page khud `getSession()` kar ke /login bhejta tha (26 jagah). Ab
 * ek hi jagah. Do shartein zaroori hain, warna guard khud ek bug ban jata hai:
 *   1. `sessionChecked` se pehle kabhi redirect nahi — pehle render par session
 *      abhi resolve hi nahi hui hoti.
 *   2. Redirect se pehle session ki DOBARA tasdeeq — neeche wale effect ka
 *      comment batata hai kyun.
 */
export default function DashboardShell({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const supabase = useMemo(() => createClient(), [])
  const { user, userId, sessionChecked } = useActiveBrand()

  /*
   * Auth guard — redirect se PEHLE session ki dobara tasdeeq.
   *
   * Sirf context par bharosa karna kaafi nahi tha. Provider root layout mein
   * hai; login /login par hota hai aur uske baad app client-side /business par
   * jati hai — us lamhe context ka snapshot abhi "koi session nahi" ho sakta
   * hai, kyunke SIGNED_IN event abhi pohancha na ho. Us par redirect kar dene
   * ka natija wohi bug tha: login karo, /business ek pal ko dikhe, phir wapas
   * /login.
   *
   * getSession() localStorage/cookie se padhti hai — network par nahi jati —
   * is liye ye tasdeeq sasti hai. Session mile to hum rukte hain aur provider
   * ka auth listener state bhar deta hai.
   */
  useEffect(() => {
    if (!sessionChecked || userId) return
    let cancelled = false

    const verify = async () => {
      try {
        const { data } = await supabase.auth.getSession()
        if (cancelled) return
        if (!data?.session) router.replace('/login')
      } catch {
        // getSession bhi nakam (corrupt token) — matlab session nahi hai
        if (!cancelled) router.replace('/login')
      }
    }
    verify()

    return () => { cancelled = true }
  }, [sessionChecked, userId, router, supabase])

  return (
    <div className="flex min-h-screen">
      <Sidebar
        user={
          user
            ? {
                email: user.email ?? undefined,
                business_name: user.business_name ?? undefined,
              }
            : undefined
        }
      />
      <div
        className="min-w-0 flex-1 transition-[margin] duration-300"
        style={{ marginLeft: 'var(--dashboard-sidebar-width, 240px)' }}
      >
        {children}
      </div>
    </div>
  )
}
