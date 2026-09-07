'use client'

import { Suspense, useState, useEffect, useCallback, useRef } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { motion, AnimatePresence } from 'framer-motion'
import { authHeaders } from '@/lib/authHeaders'
import { useActiveBrand, brandLabel } from '@/lib/useActiveBrand'
import BrandSwitcher from '@/components/dashboard/BrandSwitcher'
import { brandFontVars } from '@/components/shared/brandFonts'
import '@/components/dashboard/dash.css'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface Product {
  name: string
  price: string
  description: string
  image_url: string
  category: string
}

interface BrandProfile {
  id: number
  business_name: string
  description: string
  website_url: string
  platform: string
  business_type: string
  product_categories: string[]
  price_range: string
  target_audience: string
  store_country: string | null
  store_currency: string | null
  store_currencies: string[] | null
  store_markets: { iso: string | null; name: string }[] | null
  store_country_source: 'auto' | 'manual'
  store_ships_worldwide: boolean
  social_links: Record<string, string>
  // 'manual' = user ne khud bhare; us soorat mein rescrape inhe nahi badalta.
  social_links_source: 'auto' | 'manual'
  // Contact page se aaye hue raabte ki tafseel (dono optional).
  contact_email: string | null
  contact_phone: string | null
  products: Product[]
  total_products: number
  total_all_products: number
  category: string | null
  category_counts: Record<string, number>
  offset: number
  limit: number
  created_at: string
  updated_at: string
}

/*
 * Pehle ye emoji map tha (facebook: '\u{1F4D8}' waghera). Emoji har OS par
 * apna rang le aata hai — teen-rang palette ka pehla shikar wohi tha.
 * Ab saade stroke paths, jo currentColor par chalte hain.
 */
const SOCIAL_ICONS: Record<string, string> = {
  facebook: 'M14 8.5h2.5V5.6h-2.2c-2.4 0-3.6 1.4-3.6 3.6V11H8.6v2.9h2.1V21h3v-7.1h2.3l.4-2.9h-2.7V9.4c0-.6.2-.9.9-.9Z',
  instagram: 'M7.6 3.5h8.8a4.1 4.1 0 0 1 4.1 4.1v8.8a4.1 4.1 0 0 1-4.1 4.1H7.6a4.1 4.1 0 0 1-4.1-4.1V7.6a4.1 4.1 0 0 1 4.1-4.1Zm4.4 4.9a3.6 3.6 0 1 0 0 7.2 3.6 3.6 0 0 0 0-7.2Zm5-.9h.01',
  twitter: 'M21 5.6a7.4 7.4 0 0 1-2.1.6 3.7 3.7 0 0 0 1.6-2 7.4 7.4 0 0 1-2.3.9 3.7 3.7 0 0 0-6.3 3.4A10.5 10.5 0 0 1 4.3 4.6a3.7 3.7 0 0 0 1.1 4.9 3.6 3.6 0 0 1-1.7-.5 3.7 3.7 0 0 0 3 3.6 3.7 3.7 0 0 1-1.7.1 3.7 3.7 0 0 0 3.5 2.6A7.5 7.5 0 0 1 3 16.9a10.5 10.5 0 0 0 5.7 1.7c6.8 0 10.6-5.7 10.6-10.6v-.5A7.5 7.5 0 0 0 21 5.6Z',
  whatsapp: 'M20.5 11.7a8.4 8.4 0 0 1-12.5 7.3L3.5 20.5l1.5-4.4a8.4 8.4 0 1 1 15.5-4.4ZM9 8.4c-.3 0-.6.1-.9.4-.3.4-1.1 1.1-1.1 2.6s1.1 3 1.3 3.2c.2.2 2.2 3.4 5.4 4.6 1.6.6 2.2.5 2.6.4.6-.1 1.8-.7 2-1.5.3-.7.3-1.4.2-1.5-.1-.2-.3-.2-.6-.4l-2-1c-.3-.1-.5-.1-.7.1l-.9 1.1c-.2.2-.3.2-.6.1a6.7 6.7 0 0 1-3.4-3c-.2-.3 0-.5.1-.7l.5-.6c.2-.2.2-.4.3-.6 0-.2 0-.4-.1-.6l-.8-2c-.2-.5-.4-.4-.6-.5H9Z',
  youtube: 'M21 8.2a2.6 2.6 0 0 0-1.8-1.8C17.6 6 12 6 12 6s-5.6 0-7.2.4A2.6 2.6 0 0 0 3 8.2 27 27 0 0 0 2.6 12 27 27 0 0 0 3 15.8a2.6 2.6 0 0 0 1.8 1.8C6.4 18 12 18 12 18s5.6 0 7.2-.4a2.6 2.6 0 0 0 1.8-1.8 27 27 0 0 0 .4-3.8 27 27 0 0 0-.4-3.8ZM10.2 14.6V9.4l4.5 2.6-4.5 2.6Z',
  tiktok: 'M15.4 3.5v9.9a3.6 3.6 0 1 1-3-3.6M15.4 3.5c.3 2.2 1.9 3.7 4.1 3.9M15.4 3.5h-2.9v9.9',
  linkedin: 'M7.4 9.6v9.4M7.4 5.6h.01M12 19v-5.3c0-1.4.9-2.4 2.3-2.4s2.3 1 2.3 2.4V19M12 9.6V19',
  pinterest: 'M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17ZM10.2 20.2 12 12.4M10.1 12.4a2.9 2.9 0 1 1 4.9-2.6c.4 2.1-.8 4.3-2.8 4.6',
}

const ICON_MAIL = 'M4 6.5h16v11H4zM4 7l8 6 8-6'
const ICON_PHONE = 'M6.5 4.5h3l1.5 3.5-2 1.4a11 11 0 0 0 5.6 5.6l1.4-2 3.5 1.5v3a1.5 1.5 0 0 1-1.6 1.5A15.5 15.5 0 0 1 5 6.1a1.5 1.5 0 0 1 1.5-1.6Z'

const ICON_LINK = 'M13.83 10.17a4 4 0 0 0-5.66 0l-4 4a4 4 0 1 0 5.66 5.66l1.1-1.1m-.76-4.9a4 4 0 0 0 5.66 0l4-4a4 4 0 0 0-5.66-5.66l-1.1 1.1'

/*
 * Woh platforms jo user khud bhar sakta hai — backend ke SOCIAL_DOMAINS ke
 * barabar (modules/scraping/extractor.py). Tarteeb wahi hai jis mein form
 * dikhta hai; placeholder sirf misal ke liye hai.
 */
const SOCIAL_PLATFORMS = [
  'instagram', 'facebook', 'tiktok', 'youtube',
  'twitter', 'whatsapp', 'linkedin', 'pinterest',
] as const

const SOCIAL_PLACEHOLDERS: Record<string, string> = {
  instagram: 'instagram.com/yourbrand',
  facebook: 'facebook.com/yourbrand',
  tiktok: 'tiktok.com/@yourbrand',
  youtube: 'youtube.com/@yourbrand',
  twitter: 'x.com/yourbrand',
  whatsapp: 'wa.me/923001234567',
  linkedin: 'linkedin.com/company/yourbrand',
  pinterest: 'pinterest.com/yourbrand',
}

// useSearchParams() needs a Suspense boundary — without one `next build` fails
// while prerendering this page.
export default function BrandProfilePage() {
  return (
    <Suspense
      fallback={
        <div className="bw-dash-boot"><span /></div>
      }
    >
      <BrandProfileView />
    </Suspense>
  )
}

function BrandProfileView() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const {
    activeBrandId, activeBrand, setActiveBrandId, userId, loading: brandsLoading,
  } = useActiveBrand()
  const [profile, setProfile] = useState<BrandProfile | null>(null)
  // Products profile se alag rakhe hain — pagination sirf inhein badalti hai.
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [rescrapingLoading, setRescrapingLoading] = useState(false)
  const [activeTab, setActiveTab] = useState<'overview' | 'products' | 'social'>('overview')
  const [productPage, setProductPage] = useState(0)
  const [productsLoading, setProductsLoading] = useState(false)
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null)
  const [editForm, setEditForm] = useState({ business_name: '', description: '', target_audience: '', business_type: '' })
  // Country override - detection ghalat ho to user khud theek kar sake.
  const [editingCountry, setEditingCountry] = useState(false)
  const [countryList, setCountryList] = useState<{ iso: string; name: string }[]>([])
  const [countryDraft, setCountryDraft] = useState('')
  const [savingCountry, setSavingCountry] = useState(false)
  const [countryError, setCountryError] = useState('')

  // Social links khud bharne ke liye — wahi shakl jo country editor ki hai.
  const [editingSocial, setEditingSocial] = useState(false)
  const [socialDraft, setSocialDraft] = useState<Record<string, string>>({})
  const [savingSocial, setSavingSocial] = useState(false)
  const [socialError, setSocialError] = useState('')
  const websiteUrl = searchParams.get('url')
  const urlBrandId = searchParams.get('brand_profile_id')
    ? Number(searchParams.get('brand_profile_id'))
    : null

  /*
   * ── Products pagination ──────────────────────────────────────────────────
   *
   * Pehle "Next" dabane par poora /profile endpoint dobara chalta tha: brand
   * description, social links, markets, category counts — sab wapas, sirf 20
   * naye products ke liye. Us ke oopar backend ORM `products` column bhi saath
   * laata tha (~0.8 MB), yani har click par ek se do second ka intezaar aur
   * grid ka blank ho jana.
   *
   * Ab teen cheezein:
   *   1. /api/scraping/products — sirf page + total, poora profile nahi.
   *   2. pageCache — dekha hua page dobara kholna sifar request leta hai
   *      (Previous hamesha foran).
   *   3. prefetch — mojooda page render hote hi agla page background mein
   *      utha liya jata hai, is liye "Next" par aksar network wait hi nahi.
   */
  const PRODUCTS_PER_PAGE = 20
  const pageCache = useRef(new Map<string, Product[]>())
  /**
   * Wo requests jo abhi chal rahi hain.
   *
   * Iske baghair prefetch aur user ka click ek hi page ki DO requests bhej
   * dete the: prefetch shuru hoti, user "Next" daba deta us se pehle ke wo
   * poori ho, aur pageCache abhi khali hota to dobara fetch ho jati. Ab dono
   * ek hi promise share karte hain.
   */
  const inFlight = useRef(new Map<string, Promise<Product[] | null>>())
  const cacheKey = (brandId: number, category: string | null, page: number) =>
    `${brandId}|${category ?? ''}|${page}`

  // Products server-side paginate hote hain — poora catalogue (7k-10k products,
  // ~5 MB) browser mein laane ki zaroorat nahi jab UI 20 dikhata hai.
  const fetchProfile = async (
    uid: string,
    page = 0,
    background = false,
    category: string | null = null,
    brandId: number | null = null,
  ) => {
    try {
      if (background) setProductsLoading(true)
      else setLoading(true)
      const params = new URLSearchParams({
        offset: String(page * PRODUCTS_PER_PAGE),
        limit: String(PRODUCTS_PER_PAGE),
      })
      if (category) params.set('category', category)
      // Tarteeb ahem hai:
      //   brandId  — caller ne saaf kaha kaunsa brand (switcher/rescrape)
      //   urlBrandId — pehli load par, jab scrape abhi yahan bheja hai
      //   activeBrandId — warna switcher ka mojooda selection
      // urlBrandId ko activeBrandId par tarjeeh isi liye hai ke scrape ke
      // foran baad context abhi purana brand hold kar raha hota hai.
      // ?url= sirf purane links ke liye fallback hai.
      const bid = brandId ?? urlBrandId ?? activeBrandId
      if (bid != null) params.set('brand_profile_id', String(bid))
      else if (websiteUrl) params.set('url', websiteUrl)
      const res = await fetch(`${API_URL}/api/scraping/profile/${uid}?${params.toString()}`, {
        headers: await authHeaders(),
      })
      if (!res.ok) { router.push('/business/scraping'); return }
      const data = await res.json()
      setProfile(data)
      // Products alag state mein rehte hain taake pagination unhein badal sake
      // bina poora profile object dobara banaye. Ye page cache mein bhi jata
      // hai — wapas isi page par aane par koi request nahi.
      const list: Product[] = data.products ?? []
      setProducts(list)
      pageCache.current.set(cacheKey(data.id, category, page), list)
      setEditForm({ business_name: data.business_name || '', description: data.description || '', target_audience: data.target_audience || '', business_type: data.business_type || '' })
    } catch { setError('Failed to load profile') }
    finally { setLoading(false); setProductsLoading(false) }
  }

  /**
   * Ek page ke products — sirf products, poora profile nahi.
   * Cache hit par koi request nahi jati.
   */
  const fetchProductPage = useCallback(async (
    uid: string,
    brandId: number,
    page: number,
    category: string | null,
  ): Promise<Product[] | null> => {
    const key = cacheKey(brandId, category, page)
    const cached = pageCache.current.get(key)
    if (cached) return cached

    // Wohi page pehle se raste mein hai (aksar prefetch) — usi ka intezaar
    // karo, nayi request mat bhejo.
    const pending = inFlight.current.get(key)
    if (pending) return pending

    const run = (async (): Promise<Product[] | null> => {
      const params = new URLSearchParams({
        offset: String(page * PRODUCTS_PER_PAGE),
        limit: String(PRODUCTS_PER_PAGE),
        brand_profile_id: String(brandId),
      })
      if (category) params.set('category', category)
      try {
        const res = await fetch(`${API_URL}/api/scraping/products/${uid}?${params.toString()}`, {
          headers: await authHeaders(),
        })
        if (!res.ok) return null
        const data = await res.json()
        const list: Product[] = data.products ?? []
        pageCache.current.set(key, list)
        return list
      } catch {
        return null
      } finally {
        inFlight.current.delete(key)
      }
    })()

    inFlight.current.set(key, run)
    return run
  }, [])

  /** Agla page chupke se cache mein — taake "Next" par intezaar na ho. */
  const prefetchNextPage = useCallback((
    uid: string,
    brandId: number,
    page: number,
    category: string | null,
    totalPages: number,
  ) => {
    const next = page + 1
    if (next >= totalPages) return
    const key = cacheKey(brandId, category, next)
    if (pageCache.current.has(key) || inFlight.current.has(key)) return
    // Natija sirf cache mein jata hai; nakami khamosh hai kyunke user ne abhi
    // kuch maanga hi nahi.
    void fetchProductPage(uid, brandId, next, category)
  }, [fetchProductPage])

  /*
   * ── URL <-> active brand ka sync ─────────────────────────────────────────
   *
   * Do bilkul mukhtalif soortein hain aur unhein alag karna zaroori hai:
   *
   *   ARRIVAL — `?brand_profile_id=` ki nayi value aayi (scrape ke baad,
   *     dashboard ke "Brand Profile" button se, ya kisi bhi link se). Yahan URL
   *     hukum hai: usay active brand bana do. Context us waqt kisi PURANE brand
   *     par ho sakta hai.
   *
   *   SWITCH — URL wohi hai lekin user ne switcher se brand badla. Yahan
   *     selection hukum hai: URL ko uske peeche le aao. Ye replace zaroori hai,
   *     warna URL aur selection hamesha ke liye alag reh jate — aur neeche wala
   *     load effect "URL abhi adopt nahi hui" samajh kar kabhi load hi na kare.
   *
   * Farq `seenUrlBrand` se pata chalta hai: agar urlBrandId ki value pichli
   * render se badli hai to ye arrival hai, warna switch.
   */
  const seenUrlBrand = useRef<number | null | undefined>(undefined)

  useEffect(() => {
    const isArrival = seenUrlBrand.current !== urlBrandId
    seenUrlBrand.current = urlBrandId
    if (urlBrandId == null) return

    if (isArrival) {
      if (activeBrandId !== urlBrandId) setActiveBrandId(urlBrandId)
      return
    }
    if (activeBrandId != null && activeBrandId !== urlBrandId) {
      router.replace(`/business/scraping/profile?brand_profile_id=${activeBrandId}`)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlBrandId, activeBrandId])

  /*
   * ── Profile load — SIRF EK effect ────────────────────────────────────────
   *
   * Pehle ye do effects the: ek `userId` par ("mount hote hi load karo") aur
   * ek `activeBrandId` par ("switcher badla to load karo"). Pehli load par
   * DONO chal jate the — userId pehle aati, phir activeBrandId resolve hoti
   * aur us waqt `profile` abhi null hota, to guard pass ho jata. Natija: har
   * baar profile page kholne par /profile ki DO identical requests (network
   * tab mein saaf nazar aati thin).
   *
   * Ab ek effect, jo us BRAND par chalta hai jo asal mein chahiye — aur ek hi
   * request bhejta hai.
   */
  // URL ne brand ka naam liya hai magar context ne usay abhi adopt nahi kiya:
  // ek render ruk jao (upar wala effect isay foran theek kar deta hai), warna
  // GALAT brand load ho kar phir badalta hai — do requests, aur ek jhalak
  // doosre brand ki.
  const urlBrandPending = urlBrandId != null && activeBrandId !== urlBrandId
  const targetBrandId = urlBrandPending ? null : activeBrandId

  useEffect(() => {
    if (!userId) return
    if (urlBrandPending) return
    // Brands abhi aa rahe hain — thehro.
    if (targetBrandId == null && brandsLoading) return
    // Brands aa gaye aur koi brand hi nahi (aur ?url= bhi nahi) — yahan
    // dikhane ke liye kuch nahi hai.
    if (targetBrandId == null && !websiteUrl) { router.push('/business/scraping'); return }
    // Yehi brand pehle se khula hai — dobara laane ki zaroorat nahi.
    if (profile && profile.id === targetBrandId) return

    /*
     * Brand badalne par pagination/filter ka reset — jaan boojh kar.
     *
     * Ye reset SIRF us waqt chalta hai jab upar ke saare guards guzar chuke
     * hon, yani hum waqai ek NAYE brand ka data laane ja rahe hain. Purane
     * brand ka page number naye brand par bilkul be-maani hota hai.
     *
     * React ka متبادل (`key` prop se poora component reset) yahan mehnga hai:
     * wo pehle se khula hua profile bhi gira dega aur brand switch par poora
     * skeleton wapas aa jayega — abhi background refresh hota hai.
     */
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setProductPage(0)
    setCategoryFilter(null)
    // targetBrandId EXPLICITLY pass hota hai, warna fetchProfile stale
    // urlBrandId par gir jata aur switch ka koi asar na hota.
    // background=true sirf tab jab pehle se koi profile khula ho — warna poora
    // page skeleton dikhaye.
    fetchProfile(userId, 0, profile != null, null, targetBrandId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, targetBrandId, urlBrandPending, brandsLoading])

  /*
   * Agla page pehle se utha lo.
   *
   * Products tab par aate hi (ya page badalte hi) agla page background mein
   * cache ho jata hai. Ye wo waqt use karta hai jab user mojooda 20 products
   * dekh raha hota hai — is liye "Next" par aksar koi network wait hota hi
   * nahi, page foran badal jata hai.
   */
  useEffect(() => {
    if (!profile || !userId || activeTab !== 'products') return
    const total = Math.max(1, Math.ceil((profile.total_products ?? 0) / PRODUCTS_PER_PAGE))
    prefetchNextPage(userId, profile.id, productPage, categoryFilter, total)
  }, [profile, userId, activeTab, productPage, categoryFilter, prefetchNextPage])

  // Dropdown ki list backend se aati hai taake wo ISO_COUNTRY_NAMES ke saath
  // sync rahe - frontend mein alag se hardcode karna diverge ho jata.
  useEffect(() => {
    if (!editingCountry || countryList.length) return
    fetch(`${API_URL}/api/scraping/countries`)
      .then(r => r.json())
      .then(j => setCountryList(j.data ?? []))
      .catch(() => setCountryError('Could not load country list'))
  }, [editingCountry, countryList.length])

  const handleSaveCountry = async () => {
    if (!profile || !countryDraft) return
    setSavingCountry(true)
    setCountryError('')
    try {
      // brand_profile_id zaroori hai - warna backend .first() par gir kar
      // multi-brand account mein GHALAT brand edit kar deta hai.
      const res = await fetch(
        `${API_URL}/api/scraping/profile/${userId}?brand_profile_id=${profile.id}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
          body: JSON.stringify({ store_country: countryDraft }),
        }
      )
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload?.detail || 'Could not save country')
      setEditingCountry(false)
      await fetchProfile(userId, productPage, true, categoryFilter, profile.id)
    } catch (e) {
      setCountryError(e instanceof Error ? e.message : 'Could not save country')
    } finally {
      setSavingCountry(false)
    }
  }

  /*
   * Social links khud bharna.
   *
   * Scraping har store par social links theek nahi nikal pati — kuch stores
   * unhe sirf JS widget mein rakhte hain, aur kabhi fetch hi adhoora aa jata
   * hai. Save karne par backend inhe "manual" nishani de deta hai, jis ke baad
   * rescrape inhe overwrite NAHI karta.
   */
  const openSocialEditor = () => {
    const draft: Record<string, string> = {}
    for (const p of SOCIAL_PLATFORMS) draft[p] = profile?.social_links?.[p] || ''
    setSocialDraft(draft)
    setSocialError('')
    setEditingSocial(true)
  }

  const handleSaveSocial = async () => {
    if (!profile) return
    setSavingSocial(true)
    setSocialError('')
    try {
      // brand_profile_id wahi wajah se zaroori hai jo country editor mein hai —
      // us ke baghair backend .first() par gir kar ghalat brand edit kar deta.
      const res = await fetch(
        `${API_URL}/api/scraping/profile/${userId}?brand_profile_id=${profile.id}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
          body: JSON.stringify({ social_links: socialDraft }),
        }
      )
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(payload?.detail || 'Could not save social links')
      setEditingSocial(false)
      await fetchProfile(userId, productPage, true, categoryFilter, profile.id)
    } catch (e) {
      setSocialError(e instanceof Error ? e.message : 'Could not save social links')
    } finally {
      setSavingSocial(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const res = await fetch(`${API_URL}/api/scraping/profile/${userId}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json', ...(await authHeaders()) }, body: JSON.stringify(editForm),
      })
      if (!res.ok) throw new Error('Save failed')
      setEditing(false)
      await fetchProfile(userId, productPage, true, categoryFilter, profile?.id ?? null)
    } catch { setError('Failed to save changes') }
    finally { setSaving(false) }
  }

  const handleRescrape = async () => {
    if (!profile) return
    setRescrapingLoading(true)
    try {
      const res = await fetch(`${API_URL}/api/scraping/rescrape`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
        body: JSON.stringify({ website_url: profile.website_url, user_id: userId }),
      })
      if (!res.ok) throw new Error('Rescrape failed')
      // Rescrape catalogue badal deta hai — page 0 se dobara load karo, aur
      // cached pages phenk do warna purane products dikhte rahenge.
      pageCache.current.clear()
      setProductPage(0)
      setCategoryFilter(null)
      await fetchProfile(userId, 0, true, null, profile.id)
    } catch { setError('Re-scraping failed') }
    finally { setRescrapingLoading(false) }
  }

  if (loading) {
    return <div className="bw-dash-boot"><span /></div>
  }

  if (!profile) return null

  // "the United States · USD", ya detect na hone par saaf "Not detected" —
  // backend "international" save karta hai jab country na mile.
  const detectedCountry =
    profile.store_country && profile.store_country !== 'international'
      ? profile.store_country.replace(/^the /, '')
      : null
  const currencyList = profile.store_currencies?.length
    ? profile.store_currencies
    : (profile.store_currency ? [profile.store_currency] : [])
  const marketLabel = [detectedCountry, currencyList.join('/')]
    .filter(Boolean)
    .join(' · ') || 'Not detected'
  // Home country ke ilawa baqi markets - international brands ke liye.
  const otherMarkets = (profile.store_markets ?? [])
    .slice(1)
    .map(m => m.name?.replace(/^the /, ''))
    .filter(Boolean)

  // Server pehle hi sirf current page bhejta hai — yahan slice karne ki zaroorat nahi
  const paginatedProducts = products
  const totalProducts = profile.total_products ?? paginatedProducts.length
  const totalPages = Math.max(1, Math.ceil(totalProducts / PRODUCTS_PER_PAGE))

  const goToPage = async (page: number) => {
    const clamped = Math.min(Math.max(page, 0), totalPages - 1)
    if (clamped === productPage) return
    const brandId = profile.id

    // Cache hit -> koi spinner, koi request, koi flicker. Bas naya page.
    const cached = pageCache.current.get(cacheKey(brandId, categoryFilter, clamped))
    if (cached) {
      setProductPage(clamped)
      setProducts(cached)
      prefetchNextPage(userId, brandId, clamped, categoryFilter, totalPages)
      return
    }

    setProductsLoading(true)
    setProductPage(clamped)
    const list = await fetchProductPage(userId, brandId, clamped, categoryFilter)
    if (list) setProducts(list)
    setProductsLoading(false)
    prefetchNextPage(userId, brandId, clamped, categoryFilter, totalPages)
  }

  // Filter badalne par hamesha page 0 par wapas jao — warna user page 5 par
  // ho aur nayi category mein sirf 2 pages hon to khali page milta.
  //
  // Category badalne se filtered total badal jata hai, is liye ye abhi bhi
  // poora /profile call karta hai (wahan se naya total_products aata hai).
  // Pagination ke bar-bar chalne wale raste par ab wo nahi hai.
  const selectCategory = (cat: string | null) => {
    if (cat === categoryFilter) return
    setCategoryFilter(cat)
    setProductPage(0)
    fetchProfile(userId, 0, true, cat, profile.id)
  }

  // Chips asli products se bante hain (category_counts), profile.product_categories
  // se nahi — warna LLM ki batayi hui categories ke (0) wale chips dikhte.
  const categoryChips = Object.entries(profile.category_counts || {})
    .sort((a, b) => b[1] - a[1])

  const socialEntries = Object.entries(profile.social_links || {}).filter(([, v]) => v)

  return (
    <main className={`bw-dash prf ${brandFontVars}`}>

      <div className="dsh">

        <div className="dsh__top">
          <div>
            <h1>Brand Profile</h1>
            <p className="dsh__sub">
              {activeBrand ? brandLabel(activeBrand) : 'Your scraped store data'}
            </p>
          </div>
          <div className="dsh__topactions">
            <BrandSwitcher />
            <button
              onClick={handleRescrape}
              disabled={rescrapingLoading}
              className="dsh__btn dsh__btn--ghost dsh__btn--sm"
            >
              {rescrapingLoading ? <span className="dsh__spin" /> : null}
              {rescrapingLoading ? 'Refreshing' : 'Refresh'}
            </button>
            <button
              onClick={() => setEditing(!editing)}
              className="dsh__btn dsh__btn--ink dsh__btn--sm"
            >
              {editing ? 'Cancel' : 'Edit'}
            </button>
          </div>
        </div>

        <div className="dsh__body">

          {error && (
            <div className="prf__banner">
              <span>{error}</span>
              <button onClick={() => setError('')} className="prf__bannerx" aria-label="Dismiss">
                &times;
              </button>
            </div>
          )}

          {/* Identity */}
          <section className="dsh__card prf__id">
            <div className="prf__idtop">
              <span className="prf__mark">
                {(profile.business_name || '?').trim().charAt(0).toUpperCase()}
              </span>
              <div className="prf__idmain">
                <div className="prf__idname">
                  <h2>{profile.business_name}</h2>
                  {profile.platform && <span className="prf__tag">{profile.platform}</span>}
                </div>
                {profile.description && <p className="prf__desc">{profile.description}</p>}
                <a href={profile.website_url} target="_blank" rel="noreferrer" className="prf__url">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6}
                    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d={ICON_LINK} />
                  </svg>
                  {profile.website_url}
                </a>
              </div>
            </div>
          </section>

          {/* Stats */}
          <section className="dsh__stats dsh__stats--4">
            <div className="dsh__stat">
              <span>Products</span>
              <strong>{totalProducts.toLocaleString()}</strong>
            </div>
            <div className="dsh__stat">
              <span>Categories</span>
              <strong>{(profile.product_categories || []).length.toLocaleString()}</strong>
            </div>
            <div className="dsh__stat">
              <span>Social links</span>
              <strong>{socialEntries.length.toLocaleString()}</strong>
            </div>
            <div className="dsh__stat">
              <span>Last updated</span>
              <strong>
                {profile.updated_at
                  ? new Date(profile.updated_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
                  : 'Today'}
              </strong>
            </div>
          </section>

          {/* Edit */}
          <AnimatePresence>
            {editing && (
              <motion.section
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="dsh__card"
                style={{ overflow: 'hidden' }}
              >
                <div className="dsh__cardhead"><h3>Edit profile</h3></div>
                <div className="prf__body">
                  <div className="prf__form">
                    {[
                      { label: 'Business name', key: 'business_name' },
                      { label: 'Business type', key: 'business_type' },
                    ].map(f => (
                      <div key={f.key}>
                        <label htmlFor={`f-${f.key}`}>{f.label}</label>
                        <input
                          id={`f-${f.key}`}
                          type="text"
                          value={editForm[f.key as keyof typeof editForm]}
                          onChange={e => setEditForm(prev => ({ ...prev, [f.key]: e.target.value }))}
                        />
                      </div>
                    ))}
                    <div className="prf__wide">
                      <label htmlFor="f-desc">Description</label>
                      <textarea
                        id="f-desc"
                        rows={3}
                        value={editForm.description}
                        onChange={e => setEditForm(prev => ({ ...prev, description: e.target.value }))}
                      />
                    </div>
                    <div className="prf__wide">
                      <label htmlFor="f-aud">Target audience</label>
                      <textarea
                        id="f-aud"
                        rows={2}
                        value={editForm.target_audience}
                        onChange={e => setEditForm(prev => ({ ...prev, target_audience: e.target.value }))}
                      />
                    </div>
                  </div>
                  <div className="prf__formfoot">
                    <button onClick={() => setEditing(false)} className="dsh__btn dsh__btn--ghost">
                      Cancel
                    </button>
                    <button onClick={handleSave} disabled={saving} className="dsh__btn dsh__btn--amber">
                      {saving ? <span className="dsh__spin" /> : null}
                      {saving ? 'Saving' : 'Save changes'}
                    </button>
                  </div>
                </div>
              </motion.section>
            )}
          </AnimatePresence>

          {/* Tabs */}
          <div className="prf__tabs">
            {(['overview', 'products', 'social'] as const).map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`prf__tab${activeTab === tab ? ' prf__tab--on' : ''}`}
              >
                {tab === 'overview' ? 'Overview' : tab === 'products' ? 'Products' : 'Social'}
                {tab === 'products' && <span className="prf__tabn">{totalProducts.toLocaleString()}</span>}
                {tab === 'social' && <span className="prf__tabn">{socialEntries.length}</span>}
              </button>
            ))}
          </div>

          <AnimatePresence mode="wait">
            {activeTab === 'overview' && (
              <motion.div key="overview" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }} className="prf__cols">

                <section className="dsh__card">
                  <div className="dsh__cardhead prf__sectionhead"><h3>Target audience</h3></div>
                  <div className="prf__body">
                    <p>{profile.target_audience || 'Not specified'}</p>
                  </div>
                </section>

                <section className="dsh__card">
                  <div className="dsh__cardhead prf__sectionhead"><h3>Business info</h3></div>
                  <div className="prf__body">
                    <div className="prf__kv">
                      <span className="prf__kvk">Type</span>
                      <span className="prf__tag">{profile.business_type || 'N/A'}</span>
                    </div>
                    <div className="prf__kv">
                      <span className="prf__kvk">Platform</span>
                      <span className="prf__tag">{profile.platform || 'N/A'}</span>
                    </div>

                    {/* Market — har LLM prompt (SEO keywords, blog, ad copy,
                        chatbot) isi ko feed hota hai, is liye ye dikhna bhi
                        chahiye aur theek bhi ho sakna chahiye. Detection
                        registered address se dhoka kha sakti hai: Maria.B ka
                        Shopify account Dubai mein hai magar brand Pakistani hai. */}
                    <div className="prf__market">
                      <div className="prf__markethead">
                        <span className="prf__kvk">
                          Market
                          {profile.store_country_source === 'manual' && (
                            <span className="prf__flag">corrected</span>
                          )}
                        </span>
                        {!editingCountry && (
                          <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <span className="prf__tag">{marketLabel}</span>
                            <button
                              onClick={() => {
                                setCountryDraft(profile.store_country || '')
                                setEditingCountry(true)
                              }}
                              className="dsh__link"
                            >
                              Edit
                            </button>
                          </span>
                        )}
                      </div>

                      {editingCountry && (
                        <>
                          <select
                            value={countryDraft}
                            onChange={e => setCountryDraft(e.target.value)}
                            className="prf__select"
                          >
                            <option value="">Select the home country...</option>
                            <option value="international">International / not country-specific</option>
                            {countryList.map(c => (
                              <option key={c.iso} value={c.name}>{c.name.replace(/^the /, '')}</option>
                            ))}
                          </select>
                          <p className="prf__note">
                            Where the brand is <strong>from</strong> — not where it ships or which
                            currency it prices in. All SEO, blog and ad copy use this.
                          </p>
                          {countryError && <p className="prf__note">{countryError}</p>}
                          <div className="prf__rowbtns">
                            <button
                              onClick={handleSaveCountry}
                              disabled={!countryDraft || savingCountry}
                              className="dsh__btn dsh__btn--ink dsh__btn--sm"
                            >
                              {savingCountry ? 'Saving' : 'Save'}
                            </button>
                            <button
                              onClick={() => { setEditingCountry(false); setCountryError('') }}
                              className="dsh__btn dsh__btn--ghost dsh__btn--sm"
                            >
                              Cancel
                            </button>
                          </div>
                        </>
                      )}

                      {!editingCountry && (otherMarkets.length > 0 || profile.store_ships_worldwide) && (
                        <p className="prf__note">
                          Also sells to: {otherMarkets.join(', ') || 'not detected'}
                          {profile.store_ships_worldwide && ' — ships worldwide'}
                        </p>
                      )}
                    </div>
                  </div>
                </section>

                {/* Poori chaurai — neeche wala "Catalogue" card hata diya gaya
                    hai (wo bilkul wohi chaar numbers dobara dikha raha tha jo
                    upar stat tiles me hain), is liye ye akela reh gaya. */}
                <section className="dsh__card prf__span">
                  <div className="dsh__cardhead prf__sectionhead"><h3>Product categories</h3></div>
                  <div className="prf__body">
                    <div className="prf__chips">
                      {categoryChips.length > 0
                        ? categoryChips.map(([cat, count]) => (
                          <button
                            key={cat}
                            onClick={() => { selectCategory(cat); setActiveTab('products') }}
                            title={`Show ${count.toLocaleString()} ${cat} products`}
                            className="prf__chip"
                          >
                            {cat}
                            <span className="prf__chipn">{count.toLocaleString()}</span>
                          </button>
                        ))
                        : <p>No categories detected</p>}
                    </div>
                  </div>
                </section>

              </motion.div>
            )}

            {activeTab === 'products' && (
              <motion.div key="products" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                {/* Category filter chips — counts poore catalogue se aate hain */}
                {categoryChips.length > 0 && (
                  <div className="prf__chips" style={{ marginBottom: 18 }}>
                    <button
                      onClick={() => selectCategory(null)}
                      disabled={productsLoading}
                      className={`prf__chip${categoryFilter === null ? ' prf__chip--on' : ''}`}
                    >
                      All
                      <span className="prf__chipn">{(profile.total_all_products ?? 0).toLocaleString()}</span>
                    </button>
                    {categoryChips.map(([cat, count]) => (
                      <button
                        key={cat}
                        onClick={() => selectCategory(cat)}
                        disabled={productsLoading}
                        className={`prf__chip${categoryFilter === cat ? ' prf__chip--on' : ''}`}
                      >
                        {cat}
                        <span className="prf__chipn">{count.toLocaleString()}</span>
                      </button>
                    ))}
                  </div>
                )}

                {paginatedProducts.length === 0 && !productsLoading ? (
                  <div className="prf__blank">
                    <h4>No products in this category</h4>
                    <button onClick={() => selectCategory(null)} className="dsh__btn dsh__btn--ghost dsh__btn--sm">
                      Show all products
                    </button>
                  </div>
                ) : (
                  /*
                   * Load ke dauran grid GAYAB nahi hoti — sirf halki si dhundli
                   * ho jati hai. Pehle poori grid unmount ho kar spinner aata
                   * tha, jis se har "Next" par safha uchalta tha aur susti aur
                   * ziyada mehsoos hoti thi.
                   */
                  <div
                    className="prf__grid"
                    style={{
                      opacity: productsLoading ? 0.45 : 1,
                      transition: 'opacity 0.15s ease',
                    }}
                  >
                    {paginatedProducts.map((product, i) => (
                      <div key={i} className="prf__prod">
                        <div className="prf__prodimg">
                          {product.image_url ? (
                            <img src={product.image_url} alt={product.name} />
                          ) : (
                            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                              strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                              <path d="M4 5.5h16v13H4zM4 15l4.5-4.5 4 4 3-2.5L20 16M9 9.5h.01" />
                            </svg>
                          )}
                        </div>
                        <div className="prf__prodbody">
                          <p className="prf__prodname">{product.name}</p>
                          <div className="prf__prodfoot">
                            <span className="prf__price">{product.price || 'N/A'}</span>
                            {product.category && <span className="prf__tag prf__tag--category">{product.category}</span>}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {totalPages > 1 && (
                  <div className="prf__pager">
                    <button
                      onClick={() => goToPage(productPage - 1)}
                      disabled={productPage === 0 || productsLoading}
                      className="dsh__btn dsh__btn--ghost dsh__btn--sm"
                    >
                      Previous
                    </button>
                    <span className="prf__pagen">
                      Page <b>{productPage + 1}</b> of <b>{totalPages}</b>
                    </span>
                    <button
                      onClick={() => goToPage(productPage + 1)}
                      disabled={productPage >= totalPages - 1 || productsLoading}
                      className="dsh__btn dsh__btn--ghost dsh__btn--sm"
                    >
                      Next
                    </button>
                  </div>
                )}
              </motion.div>
            )}

            {activeTab === 'social' && (
              <motion.div key="social" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                {/*
                  Raabta — aksar footer mein hota hi nahi, contact page se
                  aata hai (dekho scraper.py). Social cards se pehle isliye ke
                  email/phone brand se raabte ka sab se seedha zariya hai.
                */}
                {(profile.contact_email || profile.contact_phone) && (
                  <div className="prf__social" style={{ marginBottom: 14 }}>
                    {profile.contact_email && (
                      <a className="prf__soc" href={`mailto:${profile.contact_email}`}>
                        <span className="prf__socico">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6}
                            strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <path d={ICON_MAIL} />
                          </svg>
                        </span>
                        <span className="prf__socmain">
                          <span className="prf__socname">Email</span>
                          <span className="prf__socurl" style={{ display: 'block' }}>{profile.contact_email}</span>
                        </span>
                      </a>
                    )}
                    {profile.contact_phone && (
                      <a className="prf__soc" href={`tel:${profile.contact_phone.replace(/\s+/g, '')}`}>
                        <span className="prf__socico">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6}
                            strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <path d={ICON_PHONE} />
                          </svg>
                        </span>
                        <span className="prf__socmain">
                          <span className="prf__socname">Phone</span>
                          <span className="prf__socurl" style={{ display: 'block' }}>{profile.contact_phone}</span>
                        </span>
                      </a>
                    )}
                  </div>
                )}

                {socialEntries.length > 0 ? (
                  <div className="prf__social">
                    {socialEntries.map(([platform, link], i) => (
                      <a
                        key={i}
                        href={link}
                        target="_blank"
                        rel="noreferrer"
                        className={`prf__soc prf__soc--${platform.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
                      >
                        <span className="prf__socico">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6}
                            strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <path d={SOCIAL_ICONS[platform] || ICON_LINK} />
                          </svg>
                        </span>
                        <span className="prf__socmain">
                          <span className="prf__socname">{platform}</span>
                          <span className="prf__socurl" style={{ display: 'block' }}>{link}</span>
                        </span>
                        <svg className="prf__socout" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                          strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <path d="M10 6H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4M14 4h6m0 0v6m0-6L10 14" />
                        </svg>
                      </a>
                    ))}
                  </div>
                ) : (
                  <div className="prf__blank">
                    <h4>No social links found</h4>
                    {/*
                      Pehle yahan likha tha "This store does not have public
                      social media links" — jo aksar GHALAT hota hai. Store ke
                      links mojood hote hain, bas scraping unhe nahi pa sakti
                      (JS widget, ya adhoora fetch). Ab wajah bhi sahi likhi
                      hai aur user khud bhar bhi sakta hai.
                    */}
                    <p>
                      We could not detect them automatically. Some stores only
                      show their links through scripts we cannot read — you can
                      add them yourself.
                    </p>
                  </div>
                )}

                {/* ── Khud bharna / theek karna ────────────────────────── */}
                {!editingSocial ? (
                  <div style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                    <button type="button" className="dsh__btn dsh__btn--ink dsh__btn--sm" onClick={openSocialEditor}>
                      {socialEntries.length > 0 ? 'Edit links' : 'Add links manually'}
                    </button>
                    {profile.social_links_source === 'manual' && (
                      <span style={{ fontSize: 12, opacity: 0.7 }}>
                        Added by you — re-scraping will not overwrite these.
                      </span>
                    )}
                  </div>
                ) : (
                  <div style={{ marginTop: 16, maxWidth: 640 }}>
                    <p style={{ fontSize: 13, opacity: 0.75, marginBottom: 12 }}>
                      Paste your own page address for each platform. Leave a box
                      empty to remove it. Once saved, re-scraping the store will
                      keep what you entered.
                    </p>

                    <div style={{ display: 'grid', gap: 10 }}>
                      {SOCIAL_PLATFORMS.map(platform => (
                        <label key={platform} style={{ display: 'grid', gap: 4 }}>
                          <span style={{ fontSize: 12, fontWeight: 700, textTransform: 'capitalize' }}>
                            {platform}
                          </span>
                          <input
                            value={socialDraft[platform] ?? ''}
                            onChange={e =>
                              setSocialDraft(d => ({ ...d, [platform]: e.target.value }))
                            }
                            placeholder={SOCIAL_PLACEHOLDERS[platform]}
                            spellCheck={false}
                            style={{
                              padding: '9px 12px', borderRadius: 10,
                              border: '1px solid #d5d1c6', background: '#fbfaf7',
                              fontSize: 13, width: '100%',
                            }}
                          />
                        </label>
                      ))}
                    </div>

                    {socialError && (
                      <p className="prf__note">{socialError}</p>
                    )}

                    <div style={{ marginTop: 14, display: 'flex', gap: 10 }}>
                      <button
                        type="button"
                        className="dsh__btn dsh__btn--ink dsh__btn--sm"
                        onClick={handleSaveSocial}
                        disabled={savingSocial}
                      >
                        {savingSocial ? 'Saving…' : 'Save links'}
                      </button>
                      <button
                        type="button"
                        className="dsh__btn dsh__btn--ghost dsh__btn--sm"
                        onClick={() => { setEditingSocial(false); setSocialError('') }}
                        disabled={savingSocial}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </main>
  )
}
