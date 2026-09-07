'use client'

import { useState, useEffect, useMemo } from 'react'
import Link from 'next/link'
import { useActiveBrand, brandLabel } from '@/lib/useActiveBrand'
import BrandSwitcher from '@/components/dashboard/BrandSwitcher'
import {
    adsApi, toImageUrl, downloadFile, downloadAdPackage, GENERATION_MODES,
  OutOfCreditsError,
  type Brand, type Product, type GenerationMode,
} from '@/lib/adsApi'

const ASPECT_RATIOS = [
  { key: 'instagram_square', label: 'Instagram Square', dims: '1080x1080', gradient: 'from-[#8b877d] to-[#56544d]' },
  { key: 'story', label: 'Story', dims: '1080x1920', gradient: 'from-[#8b877d] to-[#8b877d]' },
  { key: 'banner', label: 'Banner', dims: '1920x1080', gradient: 'from-[#d08a12] to-[#a8620d]' },
]

const MOODS = ['Festive & Warm', 'Minimal & Elegant', 'Bold & Vibrant', 'Luxury & Premium', 'Seasonal Sale']
const OCCASIONS = ['None', 'Wedding', 'Eid', 'Everyday', 'Casual', 'Corporate']
const CTA_GOALS = ['Shop Now', 'Limited Time Offer', 'New Arrival', 'Learn More']
const PLATFORMS = ['Instagram Post', 'Facebook Ad', 'Website Banner', 'Story']

type AdsGenerationResult = {
  success: boolean
  ad_id: number
  ad_image_url: string
  product_name: string
  headline: string
  caption: string
  hashtags: string[]
}

type AdsSession = {
  selectedBrand: Brand | null
  selectedProduct: Product | null
  result: AdsGenerationResult | null
  videoUrl: string | null
  generationMode: GenerationMode
  aspectRatio: string
  mood: string
  occasion: string
  ctaGoal: string
  platform: string
  customPrompt: string
  /** Jo user image PAR likhwana chahta hai. Purani sessions mein nahi hai. */
  adText?: string
}

function readAdsSession(): AdsSession | null {
  if (typeof window === 'undefined') return null
  const saved = sessionStorage.getItem('ads_session')
  if (!saved) return null
  try {
    return JSON.parse(saved) as AdsSession
  } catch {
    return null
  }
}

export default function AdsGenerationPage() {
  const {
    activeBrandId, activeBrand, setActiveBrandId, userId: ctxUserId,
    brands: ctxBrands, error: ctxBrandsError,
  } = useActiveBrand()
    // userId ab SEEDHA context se — pehle ek local state thi jise ek effect
  // context se sync karta tha. Wo effect kuch bhi nahi karta tha siwaye ek
  // extra render ke (aur react-hooks lint ne usay theek hi pakra tha).
  const userId = ctxUserId

  /*
   * Brands ab CONTEXT se aate hain, is page ki apni fetch se nahi.
   *
   * Pehle yahan `adsApi.getMyBrands()` chalti thi — ek poora network
   * round-trip HAR dafa jab ye page khulta. ActiveBrandProvider wahi list
   * app load par EK dafa le chuka hota hai, is liye wo request sirf intezaar
   * ka sabab thi: brand ka naam aur switcher dono chand second khali rehte.
   * Ab dono foran bhar jate hain aur switcher se brand badalna instant hai.
   */
  const brands = ctxBrands as unknown as Brand[]
  const brandsError = ctxBrandsError
  // selectedBrand ab STATE nahi, DERIVED hai. Pehle ye alag state thi jise ek
  // effect global switcher ke saath sync karta tha — do sources of truth, aur
  // effect har brand change par cascading render karta tha. Ab switcher hi
  // single source hai.
  // Array.isArray ka pehra: agar API kabhi array ke bajaye error object de de
  // to page crash na kare. (adsApi ab bhi guard karti hai — ye doosri deewar.)
  const selectedBrand = useMemo<Brand | null>(
    () => (Array.isArray(brands) ? brands.find((b) => b.id === activeBrandId) ?? null : null),
    [brands, activeBrandId]
  )

  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<Product[]>([])
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)
  const [searching, setSearching] = useState(false)
  const [showSearchModal, setShowSearchModal] = useState(false)

  // Default "scene": product ki photo bilkul waisi hi rehti hai. "on_model"
  // sirf un garment photos ke liye hai jin mein koi model nahi hai.
  const [generationMode, setGenerationMode] = useState<GenerationMode>('scene')
  const [aspectRatio, setAspectRatio] = useState('instagram_square')
  const [platform, setPlatform] = useState(PLATFORMS[0])
  const [ctaGoal, setCtaGoal] = useState(CTA_GOALS[0])
  const [mood, setMood] = useState(MOODS[0])
  const [occasion, setOccasion] = useState(OCCASIONS[0])
    const [customPrompt, setCustomPrompt] = useState('')
  // User ka apna text jo IMAGE PAR chhapega. Khali chhoro to AI ka headline.
  const [adText, setAdText] = useState('')
  // Credits khatam — ye alag state hai kyunke iska panel bhi alag hai aur
  // "try again" button us par dikhana bemani hai.
    const [outOfCredits, setOutOfCredits] = useState('')
  // Baqi nakamiyan. Pehle ye `alert()` mein jati thin — browser ka modal, jo
  // demo mein bhadda lagta hai aur backend ka poora message kaat deta hai.
  const [genError, setGenError] = useState('')

  const [generating, setGenerating] = useState(false)
  const [generatingVideo, setGeneratingVideo] = useState(false)
  const [result, setResult] = useState<AdsGenerationResult | null>(null)
  const [videoUrl, setVideoUrl] = useState<string | null>(null)

  const [hydrated, setHydrated] = useState(false)

  const selectedBrandLabel = selectedBrand?.business_name || selectedBrand?.website_url || 'No brand selected'
  const selectedProductLabel = selectedProduct?.name || 'No product selected'
  const canSearch = Boolean(selectedBrand && searchQuery.trim().length >= 2)

  useEffect(() => {
    const saved = readAdsSession()
    if (saved) {
      /*
     * Ye restore ek EFFECT mein hi hona chahiye.
     *
     * sessionStorage server par mojood nahi hai. Agar in fields ko lazy
     * useState initializer se bhara jaye to server khali form render karega
     * aur client bhara hua — yani hydration mismatch, jo React ke liye asli
     * error hai. Effect hydration ke BAAD chalta hai, is liye dono taraf ka
     * pehla render ek jaisa rehta hai.
     *
     * react-hooks/set-state-in-effect isi ko pakarta hai, magar is soorat
     * mein koi mehfooz متبادل nahi — browser-only state ko restore karne ka
     * yehi tareeqa hai.
     */
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (saved.selectedProduct) setSelectedProduct(saved.selectedProduct)
      if (saved.result) setResult(saved.result)
      if (saved.videoUrl) setVideoUrl(saved.videoUrl)
      if (saved.generationMode) setGenerationMode(saved.generationMode)
      if (saved.aspectRatio) setAspectRatio(saved.aspectRatio)
      if (saved.mood) setMood(saved.mood)
      if (saved.occasion) setOccasion(saved.occasion)
      if (saved.ctaGoal) setCtaGoal(saved.ctaGoal)
      if (saved.platform) setPlatform(saved.platform)
            if (saved.customPrompt) setCustomPrompt(saved.customPrompt)
      if (saved.adText) setAdText(saved.adText)
    }
    setHydrated(true)
  }, [])

  /*
   * userId context se — `auth.getUser()` yahan se hat gaya hai. Wo Supabase ke
   * /auth/v1/user par ek NETWORK round-trip tha jo har navigation par chalta
   * tha, sirf wo id lene ke liye jo provider ke paas pehle se hai.
   *
   * `.catch` bhi ahem hai: pehle sirf `.then(setBrands)` tha, to nakami par
   * promise chup-chaap reject hoti aur error kahin nazar na aata — page bahut
   * aage ja kar "brands.find is not a function" par crash karta.
   */
    

  useEffect(() => {
    if (!hydrated) return
    sessionStorage.setItem('ads_session', JSON.stringify({
      selectedProduct, result, videoUrl, generationMode,
      aspectRatio, mood, occasion, ctaGoal, platform, customPrompt, adText,
    }))
  }, [hydrated, selectedBrand, selectedProduct, result, videoUrl, generationMode, aspectRatio, mood, occasion, ctaGoal, platform, customPrompt, adText])

  useEffect(() => {
    if (!canSearch || !selectedBrand) {
      return
    }
    const currentQuery = searchQuery

    const timeout = setTimeout(() => {
      setSearching(true)
      adsApi.searchProducts(selectedBrand.id, currentQuery, userId).then((res) => {
        if (currentQuery === searchQuery) {
          setSearchResults(res)
        }
      }).finally(() => {
        setSearching(false)
      })
    }, 400)
    return () => clearTimeout(timeout)
  }, [canSearch, searchQuery, selectedBrand, userId])

  const handleGenerate = async () => {
    if (!selectedBrand || !selectedProduct || !userId) return
        setGenerating(true)
    setResult(null)
    setVideoUrl(null)
    setGenError('')
    setOutOfCredits('')
    try {
      const res = await adsApi.generateImage({
        brand_id: selectedBrand.id,
        // id se select karo — index rescrape par doosre product par shift ho jata
        // hai, aur selection localStorage mein persist hoti hai.
        product_id: selectedProduct.id ?? null,
        product_index: selectedProduct.id == null ? selectedProduct.index : null,
        generation_mode: generationMode,
        aspect_ratio: aspectRatio,
        platform,
        cta_goal: ctaGoal,
        mood,
        occasion,
                custom_prompt: customPrompt || null,
        ad_text: adText.trim() || null,
        user_id: userId,
      })
      setResult(res)
    } catch (err) {
      // Credits khatam ka apna panel hai — usay generic error banner mein
      // daal dena user ko "dobara koshish karein" ki taraf bhejta hai, jo is
      // soorat mein kabhi kaam nahi karega.
      if (err instanceof OutOfCreditsError) setOutOfCredits(err.message)
      // Backend ka message (length/profanity/provider) waisa ka waisa dikhao.
      else setGenError(err instanceof Error ? err.message : 'Could not generate the ad. Please try again.')
    } finally {
      setGenerating(false)
    }
  }

  const handleGenerateVideo = async () => {
    if (!result?.ad_id) return
    setGeneratingVideo(true)
    try {
      const res = await adsApi.generateVideo(result.ad_id)
      setVideoUrl(res.ad_video_url)
        } catch (err) {
      if (err instanceof OutOfCreditsError) setOutOfCredits(err.message)
      else setGenError(err instanceof Error ? err.message : 'Could not generate the video.')
    } finally {
      setGeneratingVideo(false)
    }
  }

  const startNewAd = () => {
    setSelectedProduct(null)
    setSearchQuery('')
    setSearchResults([])
    setResult(null)
    setVideoUrl(null)
    setCustomPrompt('')
    sessionStorage.removeItem('ads_session')
  }

  return (
    <div className="min-h-full px-6 lg:px-8 py-6">
      {/* Brands load na hon to wajah dikhni chahiye. Pehle ye nakami chup-chaap
          nigal jati thi aur page baad mein crash kar deta tha. */}
            {/* Credits khatam — apna panel, kyunke "dobara try karein" yahan bekaar
          hai. Bria 100 aur Claid 39 free images par hain, is liye demo ke
          doran ye soorat waqai aa sakti hai. */}
      {outOfCredits && (
        <div className="mb-5 rounded-xl border border-[#f2d6a6] bg-[#fdf4e6] px-5 py-4">
          <p className="text-sm font-bold text-[#a8620d]">Image credits finished</p>
          <p className="mt-1 text-xs leading-relaxed text-[#a8620d]">{outOfCredits}</p>
          <p className="mt-2 text-xs leading-relaxed text-[#8b877d]">
            Everything else still works — your saved ads, the gallery and video
            generation are unaffected. Try the other generation mode; it uses a
            different provider.
          </p>
        </div>
      )}

      {genError && (
        <div className="mb-5 flex items-start justify-between gap-4 rounded-xl border border-[#e6c3c8] bg-[#fbeaec] px-4 py-3">
          <p className="text-xs font-semibold leading-relaxed text-[#96203f]">{genError}</p>
          <button
            onClick={() => setGenError('')}
            className="shrink-0 text-xs font-bold text-[#96203f] underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {brandsError && (
        <div className="mb-5 flex items-start gap-2.5 rounded-xl border border-[#e6c3c8] bg-[#fbeaec] px-4 py-3">
          <svg className="mt-0.5 h-4 w-4 shrink-0 text-[#96203f]" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.3 3.9L1.8 18a2 2 0 001.7 3h17a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0zM12 9v4M12 17h.01" />
          </svg>
          <p className="text-xs font-semibold leading-relaxed text-[#96203f]">{brandsError}</p>
        </div>
      )}
      <div className="flex flex-col gap-6 xl:flex-row xl:items-start">
        <div className="w-full xl:max-w-105 space-y-6">
          <div className="rounded-xl border border-[#e7e4dc] bg-[#ffffff] p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.24em] text-[#8b877d]">AI Ad Studio</p>
                <h1 className="mt-2 text-3xl font-black text-[#14140f]">
                  Creative Ad Generator{activeBrand ? ` — ${brandLabel(activeBrand)}` : ''}
                </h1>
                <div className="mt-3"><BrandSwitcher /></div>
                <p className="mt-2 text-sm text-[#56544d] leading-6">
                  Build premium image and video ads from real product data, then save them to your gallery.
                </p>
              </div>
              <Link
                href="/business/ads-generation/gallery"
                className="shrink-0 rounded-full bg-[#f0a63c] px-4 py-2 text-sm font-bold text-black shadow-lg shadow-[#f0a63c]/25 transition hover:bg-[#e59a2c]"
              >
                Gallery
              </Link>
            </div>

            <div className="mt-6 grid grid-cols-2 gap-3 text-xs font-bold text-[#56544d]">
              <div className="rounded-xl border border-[#d5d1c6] bg-[#fbfaf7]/80 p-3">
                <p className="text-[11px] uppercase tracking-[0.2em] text-[#8b877d]">Brand</p>
                <p className="mt-1 truncate text-sm text-[#14140f]">{selectedBrandLabel}</p>
              </div>
              <div className="rounded-xl border border-[#d5d1c6] bg-[#fbfaf7]/80 p-3">
                <p className="text-[11px] uppercase tracking-[0.2em] text-[#8b877d]">Product</p>
                <p className="mt-1 truncate text-sm text-[#14140f]">{selectedProductLabel}</p>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-[#e7e4dc] bg-[#ffffff] p-6 space-y-6">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#0a0a0a] text-sm font-black text-white">1</div>
              <div>
                <h3 className="text-base font-black text-[#14140f]">Select Brand</h3>
                <p className="text-sm text-[#8b877d]">Choose the store or brand profile you want to advertise.</p>
              </div>
            </div>

            <select
              value={selectedBrand?.id || ''}
              onChange={(e) => {
                const id = Number(e.target.value)
                // Global switcher ko update karo — selectedBrand usi se derive hota hai
                if (id) setActiveBrandId(id)
                setSelectedProduct(null)
                setSearchQuery('')
              }}
              className="w-full rounded-xl border border-[#d5d1c6] bg-[#fbfaf7] px-4 py-3 text-sm font-semibold text-[#14140f] outline-none transition focus:border-[#c9c5bb] focus:bg-white"
            >
              <option value="">Choose a brand...</option>
              {brands.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.business_name || b.website_url}
                </option>
              ))}
            </select>
          </div>

          {selectedBrand && (
            <div className="rounded-xl border border-[#e7e4dc] bg-[#ffffff] p-6 space-y-4">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#56544d] text-sm font-black text-white">2</div>
                <div>
                  <h3 className="text-base font-black text-[#14140f]">Select Product</h3>
                  <p className="text-sm text-[#8b877d]">Search products by name, category, or keyword.</p>
                </div>
              </div>

              {selectedProduct ? (
                <div className="rounded-xl border border-[#d5d1c6] bg-[#fbfaf7] p-3">
                  <div className="flex items-center gap-3">
                    {selectedProduct.image_url && (
                      <img src={selectedProduct.image_url} alt={selectedProduct.name} className="h-16 w-16 rounded-xl object-cover" />
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-black text-[#14140f]">{selectedProduct.name}</p>
                      <p className="text-xs font-semibold text-[#8b877d]">{selectedProduct.price}</p>
                    </div>
                    <button
                      onClick={() => setShowSearchModal(true)}
                      className="rounded-full px-3 py-1.5 text-xs font-bold text-[#56544d] transition hover:bg-[#fbfaf7]"
                    >
                      Change
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setShowSearchModal(true)}
                  className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-[#c9c5bb] bg-[#fbfaf7] px-4 py-4 text-sm font-bold text-[#8b877d] transition hover:border-[#0a0a0a] hover:text-[#0a0a0a]"
                >
                  Search and pick a product
                </button>
              )}
            </div>
          )}

          {selectedProduct && (
            <div className="rounded-xl border border-[#e7e4dc] bg-[#ffffff] p-6 space-y-6">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-linear-to-br from-[#f0a63c] to-[#96203f] text-sm font-black text-white">3</div>
                <div>
                  <h3 className="text-base font-black text-[#14140f]">Ad Settings</h3>
                  <p className="text-sm text-[#8b877d]">Shape the output with a format, tone, and CTA.</p>
                </div>
              </div>

              <div>
                <label className="mb-2 block text-xs font-black uppercase tracking-[0.18em] text-[#8b877d]">Generation Method</label>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {GENERATION_MODES.map((m) => (
                    <button
                      key={m.key}
                      onClick={() => setGenerationMode(m.key)}
                      title={m.hint}
                      className={`rounded-xl border p-3 text-left transition-all ${
                        generationMode === m.key
                          ? 'border-[#0a0a0a] bg-[#0a0a0a] text-white ring-2 ring-[#0a0a0a] ring-offset-2'
                          : 'border-[#d5d1c6] bg-[#fbfaf7] text-[#14140f] hover:border-[#c9c5bb]'
                      }`}
                    >
                      <p className="text-[11px] font-black">{m.label}</p>
                      <p className={`text-[10px] font-semibold ${generationMode === m.key ? 'opacity-80' : 'text-[#8b877d]'}`}>
                        {m.blurb}
                      </p>
                    </button>
                  ))}
                </div>
                <p className="mt-2 text-[11px] font-semibold leading-relaxed text-[#8b877d]">
                  {GENERATION_MODES.find((m) => m.key === generationMode)?.hint}
                </p>
              </div>

              <div>
                <label className="mb-2 block text-xs font-black uppercase tracking-[0.18em] text-[#8b877d]">Aspect Ratio</label>
                <div className="grid grid-cols-3 gap-2">
                  {ASPECT_RATIOS.map((ar) => (
                    <button
                      key={ar.key}
                      onClick={() => setAspectRatio(ar.key)}
                      className={`rounded-xl bg-linear-to-br ${ar.gradient} p-3 text-white transition-all ${
                        aspectRatio === ar.key ? 'ring-2 ring-[#0a0a0a] ring-offset-2' : 'opacity-80 hover:opacity-100'
                      }`}
                    >
                      <p className="text-[11px] font-black">{ar.label}</p>
                      <p className="text-[10px] font-semibold opacity-90">{ar.dims}</p>
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs font-black uppercase tracking-[0.18em] text-[#8b877d]">Platform</label>
                  <select
                    value={platform}
                    onChange={(e) => setPlatform(e.target.value)}
                    className="w-full rounded-xl border border-[#d5d1c6] bg-[#fbfaf7] px-3 py-3 text-sm font-semibold text-[#14140f] outline-none transition focus:border-[#c9c5bb] focus:bg-white"
                  >
                    {PLATFORMS.map((p) => <option key={p}>{p}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-black uppercase tracking-[0.18em] text-[#8b877d]">CTA Goal</label>
                  <select
                    value={ctaGoal}
                    onChange={(e) => setCtaGoal(e.target.value)}
                    className="w-full rounded-xl border border-[#d5d1c6] bg-[#fbfaf7] px-3 py-3 text-sm font-semibold text-[#14140f] outline-none transition focus:border-[#c9c5bb] focus:bg-white"
                  >
                    {CTA_GOALS.map((c) => <option key={c}>{c}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-black uppercase tracking-[0.18em] text-[#8b877d]">Mood</label>
                  <select
                    value={mood}
                    onChange={(e) => setMood(e.target.value)}
                    className="w-full rounded-xl border border-[#d5d1c6] bg-[#fbfaf7] px-3 py-3 text-sm font-semibold text-[#14140f] outline-none transition focus:border-[#c9c5bb] focus:bg-white"
                  >
                    {MOODS.map((m) => <option key={m}>{m}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-black uppercase tracking-[0.18em] text-[#8b877d]">Occasion</label>
                  <select
                    value={occasion}
                    onChange={(e) => setOccasion(e.target.value)}
                    className="w-full rounded-xl border border-[#d5d1c6] bg-[#fbfaf7] px-3 py-3 text-sm font-semibold text-[#14140f] outline-none transition focus:border-[#c9c5bb] focus:bg-white"
                  >
                    {OCCASIONS.map((o) => <option key={o}>{o}</option>)}
                  </select>
                </div>
              </div>

                            {/* Text jo IMAGE PAR chhapega — prompt se alag cheez hai.
                  Prompt sirf tasveer ka MAHAUL banata hai; ye woh alfaz hain
                  jo Pillow se image par likhe jate hain. */}
              <div>
                <div className="mb-1 flex items-end justify-between gap-3">
                  <label className="block text-xs font-black uppercase tracking-[0.18em] text-[#8b877d]">
                    Text on the image
                  </label>
                  <span className={`text-[11px] font-bold ${adText.length > 120 ? 'text-[#96203f]' : 'text-[#8b877d]'}`}>
                    {adText.length}/120
                  </span>
                </div>
                <input
                  value={adText}
                  onChange={(e) => setAdText(e.target.value)}
                  maxLength={120}
                  placeholder="Shop the best lawn dresses from Asim Jofa"
                  className="w-full rounded-xl border border-[#d5d1c6] bg-[#fbfaf7] px-4 py-3 text-sm text-[#14140f] outline-none transition placeholder:text-[#c9c5bb] focus:border-[#c9c5bb] focus:bg-white"
                />
                <p className="mt-1.5 text-[11px] leading-relaxed text-[#8b877d]">
                  Leave blank and the AI writes the headline for you. Long text
                  wraps onto up to three lines and shrinks to fit.
                </p>
              </div>

              <div>
                <label className="mb-1 block text-xs font-black uppercase tracking-[0.18em] text-[#8b877d]">
                  Custom Prompt
                </label>
                <textarea
                  value={customPrompt}
                  onChange={(e) => setCustomPrompt(e.target.value)}
                  maxLength={600}
                  placeholder="Example: warm golden lighting, luxury studio background, premium product focus..."
                  rows={4}
                  className="w-full rounded-xl border border-[#d5d1c6] bg-[#fbfaf7] px-4 py-3 text-sm text-[#14140f] outline-none transition placeholder:text-[#c9c5bb] focus:border-[#c9c5bb] focus:bg-white"
                />
                <p className="mt-1.5 text-[11px] text-[#8b877d]">
                  Describes the SCENE, not the words on the image.
                </p>
              </div>

              <button
                onClick={handleGenerate}
                disabled={generating}
                className="group flex w-full items-center justify-center gap-2 rounded-xl bg-linear-to-r from-[#0a0a0a] via-[#16160f] to-[#0a0a0a] px-4 py-3.5 text-sm font-black text-white shadow-lg shadow-[#0a0a0a]/15 transition hover:-translate-y-px disabled:cursor-not-allowed disabled:opacity-60"
              >
                <span className="text-base">✨</span>
                {generating ? 'Generating Ad...' : 'Generate Image Ad'}
              </button>
            </div>
          )}
        </div>

        <div className="flex-1">
          <div className="sticky top-6 rounded-xl border border-[#d5d1c6]/80 bg-[#ffffff] p-4 lg:p-6">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.22em] text-[#8b877d]">Preview Studio</p>
                <h2 className="mt-1 text-xl font-black text-[#14140f]">Generated Ad Output</h2>
              </div>
              <div className="hidden rounded-full border border-[#d5d1c6] bg-[#fbfaf7] px-3 py-1 text-xs font-bold text-[#56544d] md:block">
                Saved to Gallery after generation
              </div>
            </div>

            <div className="rounded-[28px] border border-dashed border-[#c9c5bb] bg-[radial-gradient(circle_at_top,rgba(14,165,233,0.12),transparent_35%),linear-gradient(180deg,#ffffff,#f8fafc)] p-4 lg:p-6 min-h-160">
              {!result && !generating && (
                <div className="flex min-h-140 items-center justify-center">
                  <div className="max-w-md text-center">
                    <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-xl bg-[#f0a63c] text-2xl font-black text-black shadow-lg shadow-[#f0a63c]/25">
                      AI
                    </div>
                    <p className="text-lg font-black text-[#14140f]">Your ad preview will appear here</p>
                    <p className="mt-2 text-sm leading-6 text-[#8b877d]">
                      Choose a brand, select a product, and generate a premium ad image first. Then create a video version if needed.
                    </p>
                  </div>
                </div>
              )}

              {generating && (
                <div className="flex min-h-140 items-center justify-center">
                  <div className="text-center">
                    <div className="mx-auto mb-4 h-12 w-12 animate-spin rounded-full border-4 border-[#0a0a0a] border-t-transparent" />
                    <p className="text-lg font-black text-[#14140f]">Building your ad now...</p>
                    <p className="mt-2 text-sm text-[#8b877d]">Using the selected product image, copy, and styling prompts.</p>
                  </div>
                </div>
              )}

              {result && (
                <div className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
                  <div className="space-y-4">
                    <div className="overflow-hidden rounded-xl border border-[#d5d1c6] bg-white shadow-[0_18px_50px_rgba(15,23,42,0.08)]">
                      <img
                        src={toImageUrl(result.ad_image_url)}
                        alt={result.product_name}
                        className="w-full object-cover"
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-3 text-xs font-bold text-[#56544d] sm:grid-cols-4">
                      <div className="rounded-xl border border-[#d5d1c6] bg-white px-3 py-2">
                        <p className="uppercase tracking-[0.18em] text-[#8b877d]">Product</p>
                        <p className="mt-1 truncate text-[#14140f]">{result.product_name}</p>
                      </div>
                      <div className="rounded-xl border border-[#d5d1c6] bg-white px-3 py-2">
                        <p className="uppercase tracking-[0.18em] text-[#8b877d]">Format</p>
                        <p className="mt-1 text-[#14140f]">{aspectRatio}</p>
                      </div>
                      <div className="rounded-xl border border-[#d5d1c6] bg-white px-3 py-2">
                        <p className="uppercase tracking-[0.18em] text-[#8b877d]">Platform</p>
                        <p className="mt-1 truncate text-[#14140f]">{platform}</p>
                      </div>
                      <div className="rounded-xl border border-[#d5d1c6] bg-white px-3 py-2">
                        <p className="uppercase tracking-[0.18em] text-[#8b877d]">Mood</p>
                        <p className="mt-1 truncate text-[#14140f]">{mood}</p>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div className="rounded-xl border border-[#d5d1c6] bg-white p-5 shadow-[0_18px_50px_rgba(15,23,42,0.06)]">
                      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.22em] text-[#8b877d]">
                        <span className="h-2 w-2 rounded-full bg-[#12876b]" /> AI Copy
                      </div>
                      <p className="mt-3 text-xl font-black leading-tight text-[#14140f]">{result.headline}</p>
                      <p className="mt-3 text-sm leading-6 text-[#56544d]">{result.caption}</p>
                      <div className="mt-4 flex flex-wrap gap-2">
                        {result.hashtags?.map((h: string) => (
                          <span key={h} className="rounded-full border border-[#d5d1c6] bg-[#fbfaf7] px-3 py-1 text-xs font-bold text-[#56544d]">
                            #{h}
                          </span>
                        ))}
                      </div>
                    </div>

                    <div className="grid gap-3 sm:grid-cols-2">
                      <button
                        onClick={() => downloadFile(toImageUrl(result.ad_image_url), `${result.product_name}_ad.jpg`)}
                        className="rounded-xl bg-[#0a0a0a] px-4 py-3 text-center text-sm font-black text-white transition hover:bg-[#16160f]"
                      >
                        Download Image
                      </button>
                      <button
                        onClick={handleGenerateVideo}
                        disabled={generatingVideo}
                        className="rounded-xl bg-linear-to-r from-[#56544d] to-[#f0a63c] px-4 py-3 text-sm font-black text-white transition hover:opacity-95 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {generatingVideo ? 'Generating Video...' : 'Generate Video'}
                      </button>
                    </div>

                    {videoUrl && (
                      <div className="space-y-3 rounded-xl border border-[#d5d1c6] bg-white p-4 shadow-[0_18px_50px_rgba(15,23,42,0.06)]">
                        <div className="overflow-hidden rounded-xl border border-[#d5d1c6] bg-black">
                          <video src={toImageUrl(videoUrl)} controls className="w-full" />
                        </div>
                        <button
                          onClick={() => downloadFile(toImageUrl(videoUrl), `${result.product_name}_ad.mp4`)}
                          className="block w-full rounded-xl border border-[#d5d1c6] bg-[#fbfaf7] px-4 py-3 text-center text-sm font-black text-[#14140f] transition hover:bg-[#e7e4dc]"
                        >
                          Download Video
                        </button>
                      </div>
                    )}

                    <button
                      onClick={() => downloadAdPackage({
                        imageUrl: toImageUrl(result.ad_image_url),
                        videoUrl: videoUrl ? toImageUrl(videoUrl) : null,
                        productName: result.product_name,
                        headline: result.headline,
                        caption: result.caption,
                        hashtags: result.hashtags,
                      })}
                      className="w-full rounded-xl bg-[#12876b] px-4 py-3 text-sm font-black text-white transition hover:bg-[#12876b]"
                    >
                      Download Full Ad Package (.zip)
                    </button>

                    <button
                      onClick={startNewAd}
                      className="w-full rounded-xl border border-[#c9c5bb] bg-white px-4 py-3 text-sm font-black text-[#56544d] transition hover:border-[#0a0a0a] hover:text-[#0a0a0a]"
                    >
                      Create Another Ad
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {showSearchModal && (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-[#0a0a0a]/60 p-6">
          <div className="mb-10 mt-10 w-full max-w-5xl overflow-hidden rounded-[28px] bg-white shadow-[0_30px_120px_rgba(15,23,42,0.35)]">
            <div className="sticky top-0 border-b border-[#d5d1c6] bg-white p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-lg font-black text-[#14140f]">Select a Product</h3>
                <button onClick={() => setShowSearchModal(false)} className="text-xl text-[#8b877d] transition hover:text-[#0a0a0a]">✕</button>
              </div>
              <input
                autoFocus
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Type a product name, category, or keyword..."
                className="w-full rounded-xl border border-[#d5d1c6] bg-[#fbfaf7] px-4 py-3 text-sm font-semibold text-[#14140f] outline-none transition focus:border-[#c9c5bb] focus:bg-white"
              />
              {searching && <p className="mt-2 text-xs font-bold text-[#8b877d]">Searching products...</p>}
            </div>

            <div className="p-5">
              {!canSearch && (
                <p className="py-10 text-center font-bold text-[#8b877d]">
                  Type at least 2 characters to start searching.
                </p>
              )}
              {canSearch && !searching && searchResults.length === 0 && (
                <p className="py-10 text-center font-bold text-[#8b877d]">
                  No products found for &quot;{searchQuery}&quot;
                </p>
              )}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                {(canSearch ? searchResults : []).map((p) => (
                  <button
                    key={p.index}
                    onClick={() => {
                      setSelectedProduct(p)
                      setShowSearchModal(false)
                    }}
                    className="overflow-hidden rounded-xl border border-[#d5d1c6] bg-white text-left transition hover:-translate-y-0.5 hover:border-[#0a0a0a] hover:shadow-xl"
                  >
                    {p.image_url && (
                      <img src={p.image_url} alt={p.name} className="h-40 w-full object-cover" />
                    )}
                    <div className="p-3">
                      <p className="line-clamp-2 text-xs font-black text-[#14140f]">{p.name}</p>
                      <p className="mt-1 text-xs font-semibold text-[#8b877d]">{p.price}</p>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}