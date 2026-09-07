'use client'

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import type { Session } from '@supabase/supabase-js'
import { createClient } from '@/lib/supabase'
import { authHeaders } from '@/lib/authHeaders'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const STORAGE_KEY = 'brandwave.activeBrandId'

export interface BrandSummary {
  id: number
  business_name: string | null
  website_url: string
  platform: string | null
  logo_url: string | null
  product_count: number
  created_at: string | null
}

/** Sidebar/header ko jo chahiye — `users` table se ek hi baar. */
export interface DashboardUser {
  email: string | null
  business_name: string | null
}

interface ActiveBrandContextValue {
  brands: BrandSummary[]
  activeBrand: BrandSummary | null
  /** The id every module should scope its requests to. Null until brands load. */
  activeBrandId: number | null
  loading: boolean
  error: string
  setActiveBrandId: (id: number) => void
  refreshBrands: () => Promise<void>
  userId: string
  /**
   * `users` row — poore app mein SIRF yahan fetch hoti hai.
   *
   * Pehle har page apne mount par `getSession()` + `from('users').select()`
   * chalata tha (26 jagah). Wo row kabhi badalti nahi, aur har navigation par
   * do sequential Supabase round-trips (~300-500 ms) ka matlab tha ke har
   * click ke baad safha khaali baitha rehta tha. Ab ek dafa, app load par.
   */
  user: DashboardUser | null
  /**
   * Session check mukammal ho gaya (chahe session mila ho ya nahi).
   *
   * Auth guard isi par chalta hai: `sessionChecked && !userId` -> /login.
   * Iske baghair pages pehle render par hi redirect kar dete, kyunke us waqt
   * userId abhi khaali hota hai.
   */
  sessionChecked: boolean
}

const ActiveBrandContext = createContext<ActiveBrandContextValue | null>(null)

export function brandLabel(brand: BrandSummary | null): string {
  if (!brand) return ''
  if (brand.business_name) return brand.business_name
  return brand.website_url.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '')
}

/**
 * Persisted active brand id, ya null.
 *
 * Provider isay khud bhi use karta hai, lekin export hone ki asli wajah AI
 * Assistant widget hai: uska pehla message provider ke brands load hone se
 * pehle bhi ja sakta hai, aur us waqt `activeBrandId` abhi null hota hai.
 * Aisi soorat mein widget yahan se last selected brand utha leta hai bajaye
 * "koi brand select nahi hai" kehne ke.
 */
export function readStoredActiveBrandId(): number | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = Number(raw)
    return Number.isFinite(parsed) ? parsed : null
  } catch {
    return null
  }
}

/**
 * Har module ko batata hai ke user is waqt kaunsa brand dekh raha hai.
 *
 * Isse pehle har module apna brand khud "most recent profile" utha kar decide
 * karta tha — do stores wale account ko doosre brand ka data dikh jata tha bina
 * kisi error ke. Ab active brand ek hi jagah tay hota hai aur localStorage mein
 * persist hota hai.
 */
export function ActiveBrandProvider({ children }: { children: ReactNode }) {
  const supabase = useMemo(() => createClient(), [])
  const [userId, setUserId] = useState('')
  const [brands, setBrands] = useState<BrandSummary[]>([])
  const [activeBrandId, setActiveBrandIdState] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [user, setUser] = useState<DashboardUser | null>(null)
  const [sessionChecked, setSessionChecked] = useState(false)
  // Watchdog ke liye — track karta hai ke loading resolve ho chuki hai ya nahi
  const resolvedRef = useRef(false)

  /**
   * `users` row ek dafa. Nakami par chup — sidebar us soorat mein email/initial
   * ke baghair render karta hai, jo page block karne se behtar hai.
   */
  const loadUser = useCallback(async (uid: string) => {
    try {
      const { data } = await supabase
        .from('users')
        .select('email, business_name')
        .eq('id', uid)
        .single()
      if (data) setUser(data as DashboardUser)
    } catch {
      // sidebar gracefully degrade karta hai
    }
  }, [supabase])

  const loadBrands = useCallback(async (uid: string) => {
    try {
      const res = await fetch(`${API_URL}/api/scraping/my-brands/${uid}`, {
        headers: await authHeaders(),
      })
      if (!res.ok) throw new Error(`Failed to load brands (${res.status})`)
      const json = await res.json()
      const list: BrandSummary[] = json.data ?? []
      setBrands(list)
      setError('')

      // Stored choice tabhi valid hai jab wo brand abhi bhi maujood ho —
      // warna pehla brand default ban jata hai.
      const stored = readStoredActiveBrandId()

      const valid = stored != null && list.some((b) => b.id === stored)
      const next = valid ? stored : list[0]?.id ?? null
      setActiveBrandIdState(next)
      if (next != null) {
        try {
          window.localStorage.setItem(STORAGE_KEY, String(next))
        } catch {
          // private mode — in-memory selection still works
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load brands')
    } finally {
      resolvedRef.current = true
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    /** Ek session (ya uski ghair-mojoodgi) ko state par laago karta hai. */
    const applySession = async (session: Session | null) => {
      if (cancelled) return
      if (!session) {
        setUserId('')
        setUser(null)
        setBrands([])
        setActiveBrandIdState(null)
        resolvedRef.current = true
        setSessionChecked(true)
        setLoading(false)
        return
      }
      setUserId(session.user.id)
      setSessionChecked(true)
      // PARALLEL — ye do requests ek doosre par depend nahi karti. Sequential
      // chalane par har app load par ek fazool round-trip (~150-300 ms) lagta.
      await Promise.all([loadBrands(session.user.id), loadUser(session.user.id)])
    }

    const init = async () => {
      // getSession() throw kar sakta hai (network, corrupt stored session).
      // Pehle yahan koi try/catch nahi tha, to throw hone par `loading` hamesha
      // true reh jata tha — aur BrandSwitcher permanently skeleton render karta
      // tha, yani click karne ke liye koi button hi nahi hota tha.
      try {
        const { data, error: sessionError } = await supabase.auth.getSession()
        if (sessionError) throw sessionError
        await applySession(data?.session ?? null)
      } catch (e) {
        /*
         * "Invalid Refresh Token: Refresh Token Not Found" — browser mein ek
         * marra hua token para hai (DB reset, revoked session, ya refresh token
         * pehle hi use ho gaya). Usay wahin chhodne ka matlab hai ke HAR
         * getSession() yehi error phenkti rahegi aur user kabhi andar nahi aa
         * sakega. Local sign-out us storage ko saaf kar deta hai — server par
         * kuch nahi bhejta — to agli login koshish saaf slate se shuru hoti hai.
         */
        const msg = e instanceof Error ? e.message : ''
        if (/refresh token/i.test(msg)) {
          try { await supabase.auth.signOut({ scope: 'local' }) } catch { /* ignore */ }
        } else {
          setError(msg || 'Could not load your brands')
        }
        await applySession(null)
      }
    }
    init()

    /*
     * ── Auth state ko live sunna ZAROORI hai ─────────────────────────────────
     *
     * Ye provider ROOT layout mein hai, is liye iska init effect poore app ki
     * zindagi mein SIRF EK BAAR chalta hai. Login /login par hota hai, yani us
     * waqt tak ye pehle hi "koi session nahi" tay kar chuka hota hai. Root
     * layout navigate karne par remount nahi hota, to login ke baad bhi userId
     * khali reh jata — aur DashboardShell ka auth guard user ko foran /login
     * par wapas phenk deta. Bilkul yehi bug tha: login -> /business ek pal ke
     * liye -> phir wapas /login.
     *
     * onAuthStateChange se provider ko SIGNED_IN / SIGNED_OUT / TOKEN_REFRESHED
     * sab pata chalta hai, to state hamesha asli auth ke saath chalti hai.
     */
    const { data: authSub } = supabase.auth.onAuthStateChange((event, session) => {
      // INITIAL_SESSION wohi hai jo init() pehle hi handle kar raha hai —
      // dobara chalane se my-brands ki ek fazool request jati.
      if (event === 'INITIAL_SESSION') return
      if (event === 'TOKEN_REFRESHED' && session) {
        // Sirf token badla hai, user wohi hai — brands dobara laane ki zaroorat
        // nahi. Ye har ghante chalta hai.
        setUserId(session.user.id)
        setSessionChecked(true)
        return
      }
      void applySession(session ?? null)
    })

    // WATCHDOG — `loading` kabhi permanently true nahi reh sakta.
    //
    // BrandSwitcher loading par ek non-interactive skeleton render karta hai.
    // Agar getSession()/fetch kisi wajah se kabhi resolve hi na ho (hanging
    // promise, auth lock, dead network), to user ko sirf grey placeholder
    // dikhta hai aur click karne ke liye koi button hi nahi hota — bilkul
    // wahi symptom jo report hua tha.
    //
    // Is liye ek hard deadline: 8s baad loading zabardasti khatam, aur error
    // state dikhti hai jismein retry button hota hai.
    const watchdog = setTimeout(() => {
      if (!resolvedRef.current) {
        setError('Brands took too long to load')
        setSessionChecked(true)
        setLoading(false)
      }
    }, 8000)

    return () => {
      cancelled = true
      authSub.subscription.unsubscribe()
      clearTimeout(watchdog)
    }
  }, [supabase, loadBrands, loadUser])

  const setActiveBrandId = useCallback((id: number) => {
    setActiveBrandIdState(id)
    try {
      window.localStorage.setItem(STORAGE_KEY, String(id))
    } catch {
      // ignore
    }
  }, [])

  const refreshBrands = useCallback(async () => {
    if (userId) await loadBrands(userId)
  }, [userId, loadBrands])

  const activeBrand = useMemo(
    () => brands.find((b) => b.id === activeBrandId) ?? null,
    [brands, activeBrandId]
  )

  const value = useMemo<ActiveBrandContextValue>(
    () => ({
      brands, activeBrand, activeBrandId, loading, error,
      setActiveBrandId, refreshBrands, userId, user, sessionChecked,
    }),
    [brands, activeBrand, activeBrandId, loading, error,
     setActiveBrandId, refreshBrands, userId, user, sessionChecked]
  )

  return <ActiveBrandContext.Provider value={value}>{children}</ActiveBrandContext.Provider>
}

/**
 * Modules isse active brand padhte hain.
 * Provider ke bahar call karne par safe defaults milte hain, taake koi page
 * crash na kare agar wo abhi provider ke andar wrap nahi hua.
 */
export function useActiveBrand(): ActiveBrandContextValue {
  const ctx = useContext(ActiveBrandContext)
  if (ctx) return ctx

  // Provider ke bahar: safe defaults milte hain taake page crash na ho, LEKIN
  // setActiveBrandId ek no-op hai — yani switcher khulega to sahi, magar brand
  // select karne par KUCH NAHI hoga, bilkul khamoshi se. Ye galti dhoondni
  // mushkil hai, is liye dev mein loudly warn karte hain.
  if (process.env.NODE_ENV !== 'production') {
    console.error(
      '[useActiveBrand] used outside <ActiveBrandProvider>. ' +
      'Brand selection will silently do nothing. ' +
      'Wrap the route in app/business/layout.tsx (or add the provider to its layout).'
    )
  }

  return {
    brands: [],
    activeBrand: null,
    activeBrandId: null,
    loading: false,
    error: '',
    setActiveBrandId: () => {},
    refreshBrands: async () => {},
    userId: '',
    user: null,
    sessionChecked: false,
  }
}

/** `?brand_profile_id=` query fragment — null-safe. */
export function brandParam(activeBrandId: number | null): string {
  return activeBrandId != null ? `brand_profile_id=${activeBrandId}` : ''
}
