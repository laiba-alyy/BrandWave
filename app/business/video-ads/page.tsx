'use client'

import { useState, useEffect, useMemo } from 'react'
import Link from 'next/link'

import { useActiveBrand, brandLabel } from '@/lib/useActiveBrand'
import BrandSwitcher from '@/components/dashboard/BrandSwitcher'
// Product search/pick aur brand list image ad module se REUSE hoti hai —
// catalogue aur ownership check dono features ke liye ek hi hain.
import { adsApi, downloadFile, type Brand, type Product, type GalleryItem } from '@/lib/adsApi'
import {
    OutOfCreditsError, videoAdsApi, toMediaUrl, MAX_IDEA_CHARS,
  type VideoAdOptions, type VideoAdOption, type VideoSource, type GeneratedVideoAd,
  type PromptSource,
} from '@/lib/videoAdsApi'

type VideoSession = {
  selectedProduct: Product | null
  source: VideoSource
  sourceAdId: number | null
  result: GeneratedVideoAd | null
  adStyle: string
  scene: string
  mood: string
  cameraMotion: string
  lighting: string
  pacing: string
  customPrompt: string
  /** "Your idea, in your own words" — prompt likhwane wali ek line. */
  idea: string
  /** customPrompt kahan se aaya — 'form' | 'ai' | 'manual'. */
  promptSource: PromptSource
  duration: number
  userPlan: string
}

function readVideoSession(): VideoSession | null {
  if (typeof window === 'undefined') return null
  const saved = sessionStorage.getItem('video_ads_session')
  if (!saved) return null
  try {
    return JSON.parse(saved) as VideoSession
  } catch {
    return null
  }
}

/** Option grid — form ke har sawal ke liye. */
function OptionGrid({
  label, options, value, onChange, columns = 2,
}: {
  label: string
  options: VideoAdOption[]
  value: string
  onChange: (key: string) => void
  columns?: number
}) {
  return (
    <div>
      <label className="mb-2 block text-xs font-black uppercase tracking-[0.18em] text-[#8b877d]">
        {label}
      </label>
      <div className={`grid gap-2 ${columns === 3 ? 'grid-cols-2 sm:grid-cols-3' : 'grid-cols-2'}`}>
        {options.map((o) => (
          <button
            key={o.key}
            type="button"
            onClick={() => onChange(o.key)}
            className={`rounded-xl border px-3 py-2.5 text-left text-[11px] font-black transition-all ${
              value === o.key
                ? 'border-[#f0a63c] bg-[#f0a63c] text-white ring-2 ring-[#f0a63c] ring-offset-2'
                : 'border-[#d5d1c6] bg-[#fbfaf7] text-[#14140f] hover:border-[#c9c5bb]'
            }`}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  )
}

export default function VideoAdsPage() {
  
  const {
    activeBrandId, activeBrand, setActiveBrandId,
    brands: ctxBrands, userId,
  } = useActiveBrand()

  /*
   * Brands ab CONTEXT se — is page ki apni fetch se nahi.
   *
   * Pehle yahan DO sequential round-trips thay: `auth.getUser()` (Supabase ka
   * /auth/v1/user) aur phir `adsApi.getMyBrands(uid)`. Dono ke poora hone tak
   * dropdown khali rehta tha aur "Choose a brand..." dikhata tha — halanke
   * ActiveBrandProvider ye dono cheezein app load par EK dafa le chuka hota
   * hai. Ab jo brand aakhri baar istemal (ya scrape) hua tha wo FORAN chuna
   * hua aata hai, aur badalna bhi instant hai.
   */
  const brands = ctxBrands as unknown as Brand[]
  const selectedBrand = useMemo<Brand | null>(
    () => brands.find((b) => b.id === activeBrandId) ?? null,
    [brands, activeBrandId]
  )

  // Form ke options backend se aate hain — labels aur prompt fragments ek hi
  // registry mein bandhe hain (modules/video_ads/schemas.py).
  const [options, setOptions] = useState<VideoAdOptions | null>(null)
  const [optionsError, setOptionsError] = useState<string | null>(null)

  // ---- Input image ka source ----
  const [source, setSource] = useState<VideoSource>('product')
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<Product[]>([])
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)
  const [searching, setSearching] = useState(false)
  const [showSearchModal, setShowSearchModal] = useState(false)

  // Optional secondary source: pehle se bana hua image ad.
  const [imageAds, setImageAds] = useState<GalleryItem[]>([])
  const [sourceAdId, setSourceAdId] = useState<number | null>(null)

  // ---- Form ke jawabat ----
  const [adStyle, setAdStyle] = useState('')
  const [scene, setScene] = useState('')
  const [mood, setMood] = useState('')
  const [cameraMotion, setCameraMotion] = useState('')
  const [lighting, setLighting] = useState('')
  const [pacing, setPacing] = useState('')
    const [customPrompt, setCustomPrompt] = useState('')

  // ---- "Write the prompt for me" ----
  //
  // Khali textarea ka masla: jo user technical nahi wo ya to usay chhor deta
  // hai ya kuch aisa likhta hai jo backend ka prompt_guard rad kar deta hai.
  // Ab wo apne alfaz mein EK line likhta hai (Roman Urdu bhi chalti hai) aur
  // form ke chune hue options ke saath mila kar LLM teen prompt likh deta hai.
  // Ye call sasti hai — koi video credit kharch NAHI hota.
  const [idea, setIdea] = useState('')
  const [drafting, setDrafting] = useState(false)
  const [draftError, setDraftError] = useState<string | null>(null)
  const [draftOptions, setDraftOptions] = useState<string[]>([])
  // Woh farmaishein jo fixed rules rok dengi (frame mein text / product ki
  // tabdeeli). Prompt phir bhi banta hai — ye sirf batati hain ke kya nahi hoga.
  const [draftWarnings, setDraftWarnings] = useState<string[]>([])
  const [promptSource, setPromptSource] = useState<PromptSource>('form')
  // Video ke AAKHIR mein chhapne wala text. Provider ko nahi jata — moviepy
  // se locally lagta hai, is liye iska koi generation credit nahi lagta aur
  // video ~3s lambi bhi ho jati hai.
    const [endCardText, setEndCardText] = useState('')
  // 402 — fal credits khatam, ya chuni hui length paid-only hai.
  const [outOfCredits, setOutOfCredits] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [duration, setDuration] = useState(10)
  // Provider ka intikhab. Abhi koi asal billing nahi — yeh flag seedha backend
  // ko jata hai (free -> Kling, premium -> Veo 3.1).
  const [userPlan, setUserPlan] = useState('free')

  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<GeneratedVideoAd | null>(null)

  const [hydrated, setHydrated] = useState(false)

  // Plans backend se aate hain; har plan ki durations alag ho sakti hain
  // kyunki segment count provider par munhasir hai.
  const planList = useMemo(() => Object.values(options?.plans ?? {}), [options])
  const activePlan = options?.plans?.[userPlan] ?? null
  const selectedDuration = activePlan?.durations.find((d) => d.seconds === duration)
  const selectedAd = imageAds.find((a) => a.ad_id === sourceAdId) ?? null
  const canSearch = Boolean(selectedBrand && searchQuery.trim().length >= 2)
  const hasSource = source === 'product' ? Boolean(selectedProduct) : Boolean(sourceAdId)
  const canGenerate = Boolean(selectedBrand && userId && hasSource && !generating)

  // ---- Session restore (wahi pattern jo image ad page ka hai) ----
  useEffect(() => {
    const saved = readVideoSession()
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
      if (saved.source) setSource(saved.source)
      if (saved.sourceAdId) setSourceAdId(saved.sourceAdId)
      if (saved.result) setResult(saved.result)
      if (saved.adStyle) setAdStyle(saved.adStyle)
      if (saved.scene) setScene(saved.scene)
      if (saved.mood) setMood(saved.mood)
      if (saved.cameraMotion) setCameraMotion(saved.cameraMotion)
      if (saved.lighting) setLighting(saved.lighting)
      if (saved.pacing) setPacing(saved.pacing)
      if (saved.customPrompt) {
        setCustomPrompt(saved.customPrompt)
        setShowAdvanced(true)
      }
      if (saved.idea) {
        setIdea(saved.idea)
        setShowAdvanced(true)
      }
      // Draft ke OPTIONS jaan boojh kar save nahi hote (sirf chuna hua prompt
      // aur ye flag) — wo dobara bananay mein 3 second lagte hain aur unhein
      // sessionStorage mein rakhna sirf jagah kharab karta.
      if (saved.promptSource) setPromptSource(saved.promptSource)
      if (saved.duration) setDuration(saved.duration)
      if (saved.userPlan) setUserPlan(saved.userPlan)
    }
    setHydrated(true)
  }, [])

  useEffect(() => {
    if (!hydrated) return
    sessionStorage.setItem('video_ads_session', JSON.stringify({
      selectedProduct, source, sourceAdId, result,
      adStyle, scene, mood, cameraMotion, lighting, pacing, customPrompt,
      idea, promptSource, duration, userPlan,
    }))
  }, [hydrated, selectedProduct, source, sourceAdId, result,
      adStyle, scene, mood, cameraMotion, lighting, pacing, customPrompt,
      idea, promptSource, duration, userPlan])

  // ---- Options + user + brands ----
  useEffect(() => {
    videoAdsApi.getOptions()
      .then((res) => {
        setOptions(res)
        // Pehla option default — form kabhi bilkul khali submit na ho.
        setAdStyle((v) => v || res.ad_styles[0]?.key || '')
        setScene((v) => v || res.scenes[0]?.key || '')
        setMood((v) => v || res.moods[0]?.key || '')
        setCameraMotion((v) => v || res.camera_motions[0]?.key || '')
        setLighting((v) => v || res.lighting[0]?.key || '')
        setPacing((v) => v || res.pacing[0]?.key || '')
        setUserPlan((v) => (res.plans[v] ? v : res.default_plan))
      })
      .catch((e) => setOptionsError(e instanceof Error ? e.message : 'Could not load options'))
  }, [])

    useEffect(() => {
    if (!userId) return
    // Sirf image-ad gallery — brands aur userId dono context se aate hain.
    // Ye source optional hai, na mile to chup-chaap khali reh jaye.
    adsApi.getGallery(userId).then(setImageAds).catch(() => setImageAds([]))
  }, [userId])

  // ---- Product search: wahi debounce + endpoint jo image ad page ka hai ----
  useEffect(() => {
    if (!canSearch || !selectedBrand) return
    const currentQuery = searchQuery

    const timeout = setTimeout(() => {
      setSearching(true)
      adsApi.searchProducts(selectedBrand.id, currentQuery, userId).then((res) => {
        if (currentQuery === searchQuery) setSearchResults(res)
      }).finally(() => setSearching(false))
    }, 400)
    return () => clearTimeout(timeout)
  }, [canSearch, searchQuery, selectedBrand, userId])

  /**
   * Ek draft ko textarea mein daal do.
   *
   * promptSource 'ai' ho jata hai aur user ke edit karne par bhi 'ai' hi
   * rehta hai (dekho handlePromptChange) — sawal ye hai ke prompt SHURU
   * kahan se hua, na ke us mein baad mein kitna haath laga.
   */
  const applyDraft = (text: string) => {
    setCustomPrompt(text)
    setPromptSource('ai')
  }

  const handlePromptChange = (value: string) => {
    setCustomPrompt(value)
    if (!value.trim()) {
      // Box khali kar diya — ab video form ke options se banega.
      setPromptSource('form')
    } else if (promptSource !== 'ai') {
      setPromptSource('manual')
    }
  }

  const handleDraftPrompt = async () => {
    if (!selectedBrand || drafting) return
    setDrafting(true)
    setDraftError(null)
    try {
      const res = await videoAdsApi.draftPrompt({
        brand_id: selectedBrand.id,
        /*
         * Product sirf CONTEXT hai (naam/category/description). Na mile to
         * backend bina us ke draft bana leta hai, error nahi deta.
         *
         * `source` bhejna zaroori hai: image_ad wale raste par catalogue ka
         * product_id yahan hota hi nahi, wo us bane hue ad ke record mein
         * hota hai — backend wahan se dhoondta hai.
         */
        source,
        product_id: source === 'product' ? (selectedProduct?.id ?? null) : null,
        product_index:
          source === 'product' && selectedProduct?.id == null
            ? selectedProduct?.index ?? null
            : null,
        source_ad_id: source === 'image_ad' ? sourceAdId : null,
        ad_style: adStyle || null,
        scene: scene || null,
        mood: mood || null,
        camera_motion: cameraMotion || null,
        lighting: lighting || null,
        pacing: pacing || null,
        idea: idea.trim() || null,
      })
      /*
       * Pehla option foran textarea mein — warna user ko teen options dikhte
       * hain aur box phir bhi khali rehta hai, yani wahi khali page wapas.
       *
       * Lekin user ki APNI tehreer par kabhi nahi likhte. "Try another three"
       * dobara chalne par agar box mein us ka likha (ya edit kiya hua) matn
       * hai to sirf naye options dikhte hain — chunna us par chhora jata hai.
       * Ye check purane options par hai, is liye chuna hua bina-chhera draft
       * "us ka apna" nahi ginta aur normal tor par badal jata hai.
       */
      const untouched =
        !customPrompt.trim() || draftOptions.includes(customPrompt)

      setDraftOptions(res.prompts)
      setDraftWarnings(res.warnings)
      if (untouched && res.prompts[0]) applyDraft(res.prompts[0])
    } catch (err) {
      setDraftError(
        err instanceof Error
          ? err.message
          : 'Could not write a prompt. Please try again, or write your own below.'
      )
    } finally {
      setDrafting(false)
    }
  }

  const handleGenerate = async () => {
    if (!selectedBrand || !userId || !hasSource) return
        setGenerating(true)
    setError(null)
    setOutOfCredits('')
    setResult(null)
    try {
      const res = await videoAdsApi.generate({
        brand_id: selectedBrand.id,
        user_id: userId,
        source,
        product_id: source === 'product' ? (selectedProduct?.id ?? null) : null,
        product_index:
          source === 'product' && selectedProduct?.id == null
            ? selectedProduct?.index ?? null
            : null,
        source_ad_id: source === 'image_ad' ? sourceAdId : null,
        ad_style: adStyle || null,
        scene: scene || null,
        mood: mood || null,
        camera_motion: cameraMotion || null,
        lighting: lighting || null,
        pacing: pacing || null,
                custom_prompt: customPrompt.trim() || null,
        // Box khali ho to source hamesha 'form' — chahe pehle koi draft
        // liya hi kyun na gaya ho.
        prompt_source: customPrompt.trim() ? promptSource : 'form',
        end_card_text: endCardText.trim() || null,
        duration_seconds: duration,
        user_plan: userPlan,
      })
      setResult(res)
        } catch (err) {
      // Credits/paid-length ka apna panel hai — usay laal error banner mein
      // daal dena user ko "dobara koshish karein" ki taraf bhejta hai, jo is
      // soorat mein kabhi kaam nahi karega.
      if (err instanceof OutOfCreditsError) setOutOfCredits(err.message)
      else setError(err instanceof Error ? err.message : 'Could not generate the video. Please try again.')
    } finally {
      setGenerating(false)
    }
  }

  const startNew = () => {
    setSelectedProduct(null)
    setSourceAdId(null)
    setSearchQuery('')
    setSearchResults([])
    setResult(null)
    setError(null)
    setCustomPrompt('')
    setIdea('')
    setDraftOptions([])
    setDraftWarnings([])
    setDraftError(null)
    setPromptSource('form')
    sessionStorage.removeItem('video_ads_session')
  }

  const previewImage =
    source === 'product' ? selectedProduct?.image_url : selectedAd?.image_path ? toMediaUrl(selectedAd.image_path) : null

  return (
    <div className="min-h-full px-6 lg:px-8 py-6">
      <div className="flex flex-col gap-6 xl:flex-row xl:items-start">
        {/* ─────────── Left: form ─────────── */}
        <div className="w-full xl:max-w-105 space-y-6">
          <div className="rounded-xl border border-[#e7e4dc] bg-[#ffffff] p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.24em] text-[#8b877d]">AI Video Studio</p>
                <h1 className="mt-2 text-3xl font-black text-[#14140f]">
                  Product Video Ads{activeBrand ? ` — ${brandLabel(activeBrand)}` : ''}
                </h1>
                <div className="mt-3"><BrandSwitcher /></div>
                <p className="mt-2 text-sm text-[#56544d] leading-6">
                  Turn a real product photo into a moving ad. Answer a few questions — no prompt writing needed.
                </p>
              </div>
              <Link
                href="/business/video-ads/gallery"
                className="shrink-0 rounded-full bg-[#f0a63c] px-4 py-2 text-sm font-bold text-black shadow-lg shadow-[#f0a63c]/25 transition hover:bg-[#e59a2c]"
              >
                Videos
              </Link>
            </div>
          </div>

          {optionsError && (
            <div className="rounded-xl border border-[#f2d6a6] bg-[#fdf4e6] p-4 text-sm font-semibold text-[#a8620d]">
              Could not load the form options: {optionsError}
              <span className="mt-1 block font-medium">Is the backend running?</span>
            </div>
          )}

          {/* 1. Brand */}
          <div className="rounded-xl border border-[#e7e4dc] bg-[#ffffff] p-6 space-y-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#0a0a0a] text-sm font-black text-white">1</div>
              <div>
                <h3 className="text-base font-black text-[#14140f]">Select Brand</h3>
                <p className="text-sm text-[#8b877d]">Choose the store whose product you want to advertise.</p>
              </div>
            </div>
            <select
              value={selectedBrand?.id || ''}
              onChange={(e) => {
                const id = Number(e.target.value)
                if (id) setActiveBrandId(id)
                setSelectedProduct(null)
                setSearchQuery('')
              }}
              className="w-full rounded-xl border border-[#d5d1c6] bg-[#fbfaf7] px-4 py-3 text-sm font-semibold text-[#14140f] outline-none transition focus:border-[#f2d6a6] focus:bg-white"
            >
                            {brands.length === 0 && <option value="">Loading your brands...</option>}
              {brands.map((b) => (
                <option key={b.id} value={b.id}>{b.business_name || b.website_url}</option>
              ))}
            </select>
          </div>

          {/* 2. Source image */}
          {selectedBrand && (
            <div className="rounded-xl border border-[#e7e4dc] bg-[#ffffff] p-6 space-y-4">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#f0a63c] text-sm font-black text-white">2</div>
                <div>
                  <h3 className="text-base font-black text-[#14140f]">Pick the Product</h3>
                  <p className="text-sm text-[#8b877d]">The video is built from this image.</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setSource('product')}
                  className={`rounded-xl border p-3 text-left transition-all ${
                    source === 'product'
                      ? 'border-[#0a0a0a] bg-[#0a0a0a] text-white ring-2 ring-[#0a0a0a] ring-offset-2'
                      : 'border-[#d5d1c6] bg-[#fbfaf7] text-[#14140f] hover:border-[#c9c5bb]'
                  }`}
                >
                  <p className="text-[11px] font-black">From my products</p>
                  <p className={`text-[10px] font-semibold ${source === 'product' ? 'opacity-80' : 'text-[#8b877d]'}`}>
                    Your scraped catalogue
                  </p>
                </button>
                <button
                  type="button"
                  onClick={() => setSource('image_ad')}
                  className={`rounded-xl border p-3 text-left transition-all ${
                    source === 'image_ad'
                      ? 'border-[#0a0a0a] bg-[#0a0a0a] text-white ring-2 ring-[#0a0a0a] ring-offset-2'
                      : 'border-[#d5d1c6] bg-[#fbfaf7] text-[#14140f] hover:border-[#c9c5bb]'
                  }`}
                >
                  <p className="text-[11px] font-black">From an image ad</p>
                  <p className={`text-[10px] font-semibold ${source === 'image_ad' ? 'opacity-80' : 'text-[#8b877d]'}`}>
                    Optional — uses a past ad
                  </p>
                </button>
              </div>

              {source === 'product' ? (
                selectedProduct ? (
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
                        className="rounded-full px-3 py-1.5 text-xs font-bold text-[#a8620d] transition hover:bg-[#fdf4e6]"
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
                )
              ) : (
                <div>
                  {imageAds.length === 0 ? (
                    <p className="rounded-xl border border-dashed border-[#c9c5bb] bg-[#fbfaf7] px-4 py-4 text-center text-xs font-bold text-[#8b877d]">
                      You have no image ads yet. Generate one first, or use a product instead.
                    </p>
                  ) : (
                    <select
                      value={sourceAdId ?? ''}
                      onChange={(e) => setSourceAdId(e.target.value ? Number(e.target.value) : null)}
                      className="w-full rounded-xl border border-[#d5d1c6] bg-[#fbfaf7] px-4 py-3 text-sm font-semibold text-[#14140f] outline-none transition focus:border-[#f2d6a6] focus:bg-white"
                    >
                      <option value="">Choose an image ad...</option>
                      {imageAds.map((a) => (
                        <option key={a.ad_id} value={a.ad_id}>
                          {a.product_name || `Ad #${a.ad_id}`}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              )}
            </div>
          )}

          {/* 3. The form */}
          {hasSource && options && (
            <div className="rounded-xl border border-[#e7e4dc] bg-[#ffffff] p-6 space-y-6">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-linear-to-br from-[#f0a63c] to-[#96203f] text-sm font-black text-white">3</div>
                <div>
                  <h3 className="text-base font-black text-[#14140f]">Describe the Ad</h3>
                  <p className="text-sm text-[#8b877d]">Just pick what fits — we write the prompt for you.</p>
                </div>
              </div>

              <OptionGrid label="What kind of ad?" options={options.ad_styles} value={adStyle} onChange={setAdStyle} />
              <OptionGrid label="Scene / background" options={options.scenes} value={scene} onChange={setScene} columns={3} />
              <OptionGrid label="Mood / vibe" options={options.moods} value={mood} onChange={setMood} />
              <OptionGrid label="Lighting" options={options.lighting} value={lighting} onChange={setLighting} />
              <OptionGrid label="Camera motion" options={options.camera_motions} value={cameraMotion} onChange={setCameraMotion} />
              <OptionGrid label="Pacing" options={options.pacing} value={pacing} onChange={setPacing} columns={3} />

              {/* Plan -> provider. Abhi koi asal billing nahi, is liye yeh
                  khula selector hai; asal subscriptions aane par ise user ke
                  plan se replace kar dena hai. */}
              {planList.length > 1 && (
                <div>
                  <label className="mb-2 block text-xs font-black uppercase tracking-[0.18em] text-[#8b877d]">
                    Plan
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    {planList.map((pl) => (
                      <button
                        key={pl.plan}
                        type="button"
                        onClick={() => setUserPlan(pl.plan)}
                        className={`rounded-xl border p-3 text-left transition-all ${
                          userPlan === pl.plan
                            ? 'border-[#0a0a0a] bg-[#0a0a0a] text-white ring-2 ring-[#0a0a0a] ring-offset-2'
                            : 'border-[#d5d1c6] bg-[#fbfaf7] text-[#14140f] hover:border-[#c9c5bb]'
                        }`}
                      >
                        <p className="text-[11px] font-black">{pl.label}</p>
                        <p className={`text-[10px] font-semibold ${userPlan === pl.plan ? 'opacity-80' : 'text-[#8b877d]'}`}>
                          {pl.provider} video model
                        </p>
                      </button>
                    ))}
                  </div>
                  <p className="mt-2 text-[11px] font-semibold leading-relaxed text-[#8b877d]">
                    No billing is connected yet — this flag just picks which
                    model generates the video.
                  </p>
                </div>
              )}

              {/* Video length — cost yahin saaf dikhta hai, generate se PEHLE. */}
              <div>
                <label className="mb-2 block text-xs font-black uppercase tracking-[0.18em] text-[#8b877d]">
                  Video length
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {(activePlan?.durations ?? []).map((d) => (
                                        <button
                      key={d.seconds}
                      type="button"
                      disabled={d.locked}
                      title={d.locked ? 'Needs paid credits' : undefined}
                      onClick={() => !d.locked && setDuration(d.seconds)}
                      className={`rounded-xl border p-3 text-left transition-all ${
                        d.locked
                          ? 'cursor-not-allowed border-[#e7e4dc] bg-[#fbfaf7] text-[#c9c5bb]'
                          : duration === d.seconds
                            ? 'border-[#f0a63c] bg-[#f0a63c] text-white ring-2 ring-[#f0a63c] ring-offset-2'
                            : 'border-[#d5d1c6] bg-[#fbfaf7] text-[#14140f] hover:border-[#c9c5bb]'
                      }`}
                    >
                      <p className="text-sm font-black">
                        {d.seconds}s{d.locked ? ' \u00b7 Paid' : ''}
                      </p>
                      <p className={`mt-0.5 text-[10px] font-semibold leading-tight ${
                        d.locked ? 'text-[#c9c5bb]'
                          : duration === d.seconds ? 'opacity-80' : 'text-[#8b877d]'
                      }`}>
                        {d.locked ? 'Needs paid credits' : d.detail}
                      </p>
                    </button>
                  ))}
                </div>
                                {(activePlan?.durations ?? []).some((d) => d.locked) && (
                  <p className="mt-2 rounded-xl border border-[#e7e4dc] bg-[#fbfaf7] px-3 py-2 text-[11px] font-semibold leading-relaxed text-[#8b877d]">
                    Longer lengths run several billable generations each, so they
                    stay locked until paid credits are added. Add an end card below
                    to make a 10s or 15s ad longer for free.
                  </p>
                )}
                {selectedDuration && selectedDuration.segments > 1 && (
                  <p className="mt-2 rounded-xl bg-[#fdf4e6] px-3 py-2 text-[11px] font-bold leading-relaxed text-[#a8620d]">
                    Heads up: {selectedDuration.seconds}s runs {selectedDuration.segments} billable
                    {activePlan ? ` ${activePlan.provider}` : ''} generations on fal.ai
                    ({selectedDuration.detail}), so it costs more and takes longer than the
                    shortest option.
                  </p>
                )}
              </div>

              <div className="mb-5">
                <div className="mb-2 flex items-end justify-between gap-3">
                  <label className="block text-xs font-black uppercase tracking-[0.18em] text-[#8b877d]">
                    End card text
                  </label>
                  <span className="text-[11px] font-bold text-[#8b877d]">
                    {endCardText.length}/90
                  </span>
                </div>
                <input
                  value={endCardText}
                  onChange={(e) => setEndCardText(e.target.value)}
                  maxLength={90}
                  placeholder="Shop the new lawn collection - asimjofa.com"
                  className="w-full rounded-xl border border-[#d5d1c6] bg-[#fbfaf7] px-4 py-3 text-sm text-[#14140f] outline-none transition placeholder:text-[#c9c5bb] focus:border-[#f2d6a6] focus:bg-white"
                />
                <p className="mt-1.5 text-[11px] leading-relaxed text-[#8b877d]">
                  Fades in on a closing card and adds about 3 seconds to the video.
                  Rendered here, not by the AI model, so it costs no credits and the
                  text always comes out clean.
                </p>
              </div>

              {/*
                Prompt — AI likhe ya user khud.

                Pehle is ka unwan "Advanced: write your own prompt" tha. Wahi
                lafz "Advanced" un logon ko rok deta tha jinke liye ye feature
                sab se zyada faidemand hai, is liye ab unwan daawat deta hai.
              */}
              <div className="rounded-xl border border-[#d5d1c6] bg-[#fbfaf7]/60 p-4">
                <button
                  type="button"
                  onClick={() => setShowAdvanced((v) => !v)}
                  className="flex w-full items-center justify-between text-left"
                >
                  <span className="text-xs font-black uppercase tracking-[0.18em] text-[#56544d]">
                    Prompt: let AI write it, or write your own
                  </span>
                  <span className="text-sm font-black text-[#8b877d]">{showAdvanced ? '−' : '+'}</span>
                </button>

                {showAdvanced && (
                  <div className="mt-4 space-y-4">
                    {/* ---- 1. User ki apni line + "likh do" button ---- */}
                    <div>
                      <div className="mb-2 flex items-end justify-between gap-3">
                        <label className="block text-xs font-black uppercase tracking-[0.18em] text-[#8b877d]">
                          Your idea <span className="normal-case tracking-normal text-[#c9c5bb]">— optional</span>
                        </label>
                        <span className="text-[11px] font-bold text-[#8b877d]">
                          {idea.length}/{MAX_IDEA_CHARS}
                        </span>
                      </div>
                      <input
                        value={idea}
                        onChange={(e) => setIdea(e.target.value)}
                        maxLength={MAX_IDEA_CHARS}
                        placeholder="chai ka cup barish wali khirki ke paas"
                        className="w-full rounded-xl border border-[#d5d1c6] bg-white px-4 py-3 text-sm text-[#14140f] outline-none transition placeholder:text-[#c9c5bb] focus:border-[#f2d6a6]"
                      />
                      <p className="mt-1.5 text-[11px] leading-relaxed text-[#8b877d]">
                        Tell us the scene you have in mind — Urdu or English, both work.
                        Leave it empty and we will write three from your choices above.
                      </p>

                      {/*
                        Wahi shakl jo neeche wale "Generate Video Ad" button ki
                        hai — sirf padding thori kam, taake asal CTA phir bhi
                        sab se numaya rahe.
                      */}
                      <button
                        type="button"
                        onClick={handleDraftPrompt}
                        disabled={!selectedBrand || drafting}
                        className="group mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-[#f0a63c] px-4 py-3 text-sm font-black text-black shadow-lg shadow-[#f0a63c]/25 transition hover:-translate-y-px hover:bg-[#e59a2c] disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        <span className="text-base">✨</span>
                        {drafting ? 'Writing your prompt…' : 'Write the prompt for me'}
                      </button>
                      <p className="mt-1.5 text-[11px] leading-relaxed text-[#8b877d]">
                        Free — this only writes text, so it uses no video credits.
                      </p>
                    </div>

                    {draftError && (
                      <div className="rounded-xl border border-[#e6c3c8] bg-[#fbeaec] px-3 py-2 text-[11px] font-semibold leading-relaxed text-[#96203f]">
                        {draftError}
                      </div>
                    )}

                    {/*
                      Woh farmaishein jo fixed rules rok dengi. Ye BLOCK nahi
                      karti — prompt ban chuka hota hai. Sirf batati hain ke
                      kya nahi hoga, aur us ka theek rasta kya hai (End card).
                    */}
                    {draftWarnings.map((w, i) => (
                      <div
                        key={i}
                        className="rounded-xl border border-[#f2d6a6] bg-[#fdf4e6] px-3 py-2 text-[11px] font-semibold leading-relaxed text-[#a8620d]"
                      >
                        {w}
                      </div>
                    ))}

                    {/* ---- 2. Teen options — chunna likhne se aasan hai ---- */}
                    {draftOptions.length > 0 && (
                      <div>
                        <label className="mb-2 block text-xs font-black uppercase tracking-[0.18em] text-[#8b877d]">
                          Pick one
                        </label>
                        <div className="space-y-2">
                          {draftOptions.map((p, i) => (
                            <button
                              key={i}
                              type="button"
                              onClick={() => applyDraft(p)}
                              className={`w-full rounded-xl border p-3 text-left transition-all ${
                                customPrompt === p
                                  ? 'border-[#f0a63c] bg-[#fdf4e6] ring-2 ring-[#f0a63c] ring-offset-2'
                                  : 'border-[#d5d1c6] bg-white hover:border-[#c9c5bb]'
                              }`}
                            >
                              <p className="text-[10px] font-black uppercase tracking-[0.18em] text-[#8b877d]">
                                Option {i + 1}
                                {customPrompt === p ? ' · using this' : ''}
                              </p>
                              <p className="mt-1 text-[12px] leading-relaxed text-[#14140f]">
                                {p}
                              </p>
                            </button>
                          ))}
                        </div>
                        <button
                          type="button"
                          onClick={handleDraftPrompt}
                          disabled={drafting}
                          className="mt-2 w-full rounded-xl border border-[#d5d1c6] bg-[#fbfaf7] px-4 py-2.5 text-xs font-black text-[#14140f] transition hover:border-[#c9c5bb] disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          ↻ Try another three
                        </button>
                      </div>
                    )}

                    {/* ---- 3. Asal prompt — hamesha qabil-e-tarmeem ---- */}
                    <div>
                      <div className="mb-2 flex items-end justify-between gap-3">
                        <label className="block text-xs font-black uppercase tracking-[0.18em] text-[#8b877d]">
                          Prompt
                        </label>
                        {promptSource === 'ai' && customPrompt.trim() && (
                          <span className="rounded-full bg-[#fdf4e6] px-2 py-0.5 text-[10px] font-black uppercase tracking-[0.14em] text-[#a8620d]">
                            AI draft
                          </span>
                        )}
                      </div>
                      <textarea
                        value={customPrompt}
                        onChange={(e) => handlePromptChange(e.target.value)}
                        placeholder="Example: the product rests on wet black stone as mist drifts past, camera slowly pushes in, cool cinematic light..."
                        rows={5}
                        className="w-full rounded-xl border border-[#d5d1c6] bg-white px-4 py-3 text-sm text-[#14140f] outline-none transition placeholder:text-[#c9c5bb] focus:border-[#f2d6a6]"
                      />
                      <p className="mt-2 text-[11px] font-semibold leading-relaxed text-[#8b877d]">
                        Edit this freely, or leave it as it is. Whatever is in this box
                        takes over from the Style, Scene, Mood, Lighting, Camera and
                        Pacing choices above. Leave it empty to use those choices
                        instead. The product-protection rules always stay on.
                      </p>
                    </div>
                  </div>
                )}
              </div>

                            {outOfCredits && (
                <div className="rounded-xl border border-[#f2d6a6] bg-[#fdf4e6] p-4">
                  <p className="text-sm font-black text-[#a8620d]">Video credits needed</p>
                  <p className="mt-1 text-xs font-semibold leading-relaxed text-[#a8620d]">{outOfCredits}</p>
                  <p className="mt-2 text-xs leading-relaxed text-[#8b877d]">
                    Everything else still works — your saved videos and the gallery
                    are unaffected. A 10s or 15s ad with an end card gives you a
                    longer result without extra generations.
                  </p>
                </div>
              )}

              {error && (
                <div className="rounded-xl border border-[#e6c3c8] bg-[#fbeaec] p-4 text-sm font-semibold text-[#96203f]">
                  {error}
                </div>
              )}

              <button
                onClick={handleGenerate}
                disabled={!canGenerate}
                className="group flex w-full items-center justify-center gap-2 rounded-xl bg-[#f0a63c] px-4 py-3.5 text-sm font-black text-black shadow-lg shadow-[#f0a63c]/25 transition hover:-translate-y-px hover:bg-[#e59a2c] disabled:cursor-not-allowed disabled:opacity-60"
              >
                <span className="text-base">🎬</span>
                {generating ? `Generating ${duration}s video...` : `Generate ${duration}s Video Ad`}
              </button>
            </div>
          )}
        </div>

        {/* ─────────── Right: preview ─────────── */}
        <div className="flex-1">
          <div className="sticky top-6 rounded-xl border border-[#d5d1c6]/80 bg-[#ffffff] p-4 lg:p-6">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.22em] text-[#8b877d]">Preview Studio</p>
                <h2 className="mt-1 text-xl font-black text-[#14140f]">Generated Video Ad</h2>
              </div>
              <div className="hidden rounded-full border border-[#d5d1c6] bg-[#fbfaf7] px-3 py-1 text-xs font-bold text-[#56544d] md:block">
                Saved to your video gallery
              </div>
            </div>

            <div className="rounded-[28px] border border-dashed border-[#c9c5bb] bg-[radial-gradient(circle_at_top,rgba(168,85,247,0.12),transparent_35%),linear-gradient(180deg,#ffffff,#f8fafc)] p-4 lg:p-6 min-h-160">
              {!result && !generating && (
                <div className="flex min-h-140 flex-col items-center justify-center gap-6">
                  {previewImage && (
                    <img src={previewImage} alt="Source" className="max-h-64 rounded-xl border border-[#d5d1c6] object-contain shadow-lg" />
                  )}
                  <div className="max-w-md text-center">
                    <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-xl bg-[#f0a63c] text-2xl font-black text-black shadow-lg shadow-[#f0a63c]/25">
                      🎬
                    </div>
                    <p className="text-lg font-black text-[#14140f]">Your video ad will appear here</p>
                    <p className="mt-2 text-sm leading-6 text-[#8b877d]">
                      Pick a product, answer the questions, and choose a length. The product itself
                      stays exactly as it is — only the scene, lighting and camera move.
                    </p>
                  </div>
                </div>
              )}

              {generating && (
                <div className="flex min-h-140 items-center justify-center">
                  <div className="max-w-md text-center">
                    <div className="mx-auto mb-4 h-12 w-12 animate-spin rounded-full border-4 border-[#a8620d] border-t-transparent" />
                    <p className="text-lg font-black text-[#14140f]">
                      Generating your {duration}s video{activePlan ? ` with ${activePlan.provider}` : ''}...
                    </p>
                    <p className="mt-2 text-sm leading-6 text-[#8b877d]">
                      {selectedDuration && selectedDuration.segments > 1
                        ? `This runs ${selectedDuration.segments} generations back to back (each one continues from the last frame of the previous), so it can take several minutes.`
                        : 'Video generation usually takes a few minutes.'}
                    </p>
                    <p className="mt-3 text-xs font-bold text-[#a8620d]">
                      Please keep this tab open — closing it will not stop the charge.
                    </p>
                  </div>
                </div>
              )}

              {result && (
                <div className="space-y-5">
                  {/* Prompt parha nahi ja saka — user ko batana zaroori hai,
                      warna wo samajhta hai ke uska prompt chala tha. */}
                  {result.prompt_notice && (
                    <div className="rounded-xl border border-[#f2d6a6] bg-[#fdf4e6] px-4 py-3">
                      <p className="text-[11px] font-black uppercase tracking-[0.18em] text-[#a8620d]">
                        Prompt not used
                      </p>
                      <p className="mt-1 text-xs font-semibold leading-relaxed text-[#a8620d]">
                        {result.prompt_notice}
                      </p>
                    </div>
                  )}
                  <div className="overflow-hidden rounded-xl border border-[#d5d1c6] bg-black shadow-[0_18px_50px_rgba(15,23,42,0.12)]">
                    <video src={toMediaUrl(result.video_url)} controls loop className="w-full" />
                  </div>

                  <div className="grid grid-cols-2 gap-3 text-xs font-bold text-[#56544d] sm:grid-cols-4">
                    <div className="rounded-xl border border-[#d5d1c6] bg-white px-3 py-2">
                      <p className="uppercase tracking-[0.18em] text-[#8b877d]">Product</p>
                      <p className="mt-1 truncate text-[#14140f]">{result.product_name || '—'}</p>
                    </div>
                    <div className="rounded-xl border border-[#d5d1c6] bg-white px-3 py-2">
                      <p className="uppercase tracking-[0.18em] text-[#8b877d]">Length</p>
                      <p className="mt-1 text-[#14140f]">{result.duration_seconds}s</p>
                    </div>
                    <div className="rounded-xl border border-[#d5d1c6] bg-white px-3 py-2">
                      <p className="uppercase tracking-[0.18em] text-[#8b877d]">Segments</p>
                      <p className="mt-1 text-[#14140f]">{result.segments}</p>
                    </div>
                    <div className="rounded-xl border border-[#d5d1c6] bg-white px-3 py-2">
                      <p className="uppercase tracking-[0.18em] text-[#8b877d]">Model</p>
                      <p className="mt-1 truncate text-[#14140f]" title={result.model_id}>
                        {result.provider} · audio off
                      </p>
                    </div>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2">
                    <button
                      onClick={() => downloadFile(
                        toMediaUrl(result.video_url),
                        `${(result.product_name || 'product').replace(/[^a-z0-9]/gi, '_')}_video_ad.mp4`
                      )}
                      className="rounded-xl bg-[#0a0a0a] px-4 py-3 text-center text-sm font-black text-white transition hover:bg-[#16160f]"
                    >
                      Download Video
                    </button>
                    <button
                      onClick={startNew}
                      className="rounded-xl border border-[#c9c5bb] bg-white px-4 py-3 text-sm font-black text-[#56544d] transition hover:border-[#0a0a0a] hover:text-[#0a0a0a]"
                    >
                      Create Another Video
                    </button>
                  </div>

                  <p className="text-center text-[11px] font-semibold text-[#8b877d]">
                    Music and on-screen text are added separately, later.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Product search modal — image ad page ke jaisa hi flow */}
      {showSearchModal && (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-[#0a0a0a]/60 p-6">
          <div className="mb-10 mt-10 w-full max-w-5xl overflow-hidden rounded-[28px] bg-white shadow-[0_30px_120px_rgba(15,23,42,0.35)]">
            <div className="sticky top-0 border-b border-[#d5d1c6] bg-white p-5">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-lg font-black text-[#14140f]">Select a Product</h3>
                <button onClick={() => setShowSearchModal(false)} className="text-xl text-[#8b877d] transition hover:text-[#0a0a0a]">✕</button>
              </div>
              <input
                autoFocus
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Type a product name, category, or keyword..."
                className="w-full rounded-xl border border-[#d5d1c6] bg-[#fbfaf7] px-4 py-3 text-sm font-semibold text-[#14140f] outline-none transition focus:border-[#f2d6a6] focus:bg-white"
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
                    className="overflow-hidden rounded-xl border border-[#d5d1c6] bg-white text-left transition hover:-translate-y-0.5 hover:border-[#f0a63c] hover:shadow-xl"
                  >
                    {p.image_url && <img src={p.image_url} alt={p.name} className="h-40 w-full object-cover" />}
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
