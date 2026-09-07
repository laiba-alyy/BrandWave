/**
 * Video ad module ka API client — image ad wale `adsApi` se ALAG.
 *
 * Yahan product search/list DOBARA nahi likhi gayi. Video ka product picker
 * seedha `adsApi.searchProducts` / `adsApi.getMyBrands` istemal karta hai,
 * kyunki catalogue aur ownership check dono modules ke liye ek hi hain.
 */
import { authHeaders } from '@/lib/authHeaders'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

/*
 * ROUTE PREFIX MEIN "ads" JAAN BOOJH KAR NAHI HAI.
 *
 * uBlock/AdBlock/Brave Shields ki generic filter lists URL mein "ads-" jaisa
 * tukra dekh kar request giradeti hain (net::ERR_BLOCKED_BY_CLIENT). JS mein
 * wo `TypeError: Failed to fetch` banta hai — bina status code ke, aur server
 * par koi log bhi nahi aata kyunke request browser se nikalti hi nahi. Backend
 * theek hota hai magar user ko sirf "failed to fetch" dikhta hai.
 *
 * Backend dono prefixes serve karta hai; ye naya neutral wala hai.
 * Badalna ho to SIRF yahan — har call site isi constant se banti hai.
 */
const VIDEO_ADS_API = `${API_BASE}/api/video-studio`

/** Backend ne 402 diya — credits khatam, ya ye length paid credits maangti hai. */
export class OutOfCreditsError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'OutOfCreditsError'
  }
}

async function readJsonOrThrow<T>(res: Response): Promise<T> {
  let body: unknown = null
  try {
    body = await res.json()
  } catch {
    body = null
  }

  if (!res.ok) {
    const envelope = body as { detail?: unknown; message?: string } | null
    const detail =
      (typeof envelope?.detail === 'string' && envelope.detail) ||
      envelope?.message ||
      `Request failed (${res.status})`
        // 402 = credits khatam (fal.ai) YA paid-only length. Dono soorton mein
    // "dobara koshish karein" bekaar hai, is liye UI ko farq pata hona chahiye.
    if (res.status === 402) throw new OutOfCreditsError(detail)
    throw new Error(detail)
  }

  return body as T
}

/**
 * Backend `generated_ads/videos/xxx.mp4` deta hai; /static us folder par mount
 * hai. Wahi mapping jo adsApi.toImageUrl karta hai — videos usi mount se aati
 * hain, is liye behaviour ek jaisa rakha gaya hai.
 */
export function toMediaUrl(path: string): string {
  const cleaned = path.replace(/\\/g, '/').replace(/^generated_ads\//, '')
  return `${API_BASE}/static/${cleaned}`
}

/** Ek form option. Labels backend ki registry se aate hain. */
export interface VideoAdOption {
  key: string
  label: string
}

export interface VideoDurationOption {
  seconds: number
  /** Kitni billable generations lagengi (1 base + extensions). */
  segments: number
  label: string
    /** Misal: "1 generation + 2 extensions" — cost ka andaza dene ke liye. */
  detail: string
  /**
   * Ye length paid credits maangti hai (backend: VIDEO_PAID_DURATIONS).
   * 20s teen billable generations chalata hai, is liye default par band hai.
   * UI ise disabled dikhati hai — warna user 2-3 minute intezaar ke baad 402
   * khata.
   */
  locked: boolean
}

/**
 * Ek plan aur us ka provider.
 *
 * `durations` PLAN ke saath badalti hain: segment count provider par munhasir
 * hai (Kling 10s ek generation mein deta hai, Veo ko do lagti hain), is liye
 * cost warning bhi plan ke saath badalta hai.
 */
export interface VideoPlanCapability {
  plan: string
  label: string
  /** "Kling" | "Veo" */
  provider: string
  model_id: string
  durations: VideoDurationOption[]
}

/** Backend: GET /api/video-studio/options */
export interface VideoAdOptions {
  ad_styles: VideoAdOption[]
  scenes: VideoAdOption[]
  moods: VideoAdOption[]
  camera_motions: VideoAdOption[]
  lighting: VideoAdOption[]
  pacing: VideoAdOption[]
  /** plan key -> capability. "free" -> Kling, "premium" -> Veo 3.1 */
  plans: Record<string, VideoPlanCapability>
  default_plan: string
}

/** Input image kahan se aa rahi hai. 'product' hi asal/default rasta hai. */
export type VideoSource = 'product' | 'image_ad'

/**
 * Prompt kahan se aaya — sirf record ke liye, generation ka rasta is se nahi
 * badalta.
 *   'form'   -> user ne prompt likha hi nahi
 *   'ai'     -> "Write the prompt for me" ka draft (edit kiya ho ya na)
 *   'manual' -> user ne khud likha
 *
 * Backend is par bharosa nahi karta: prompt na-qabil-e-istemal nikle to wahan
 * chup-chaap 'form' ban jata hai (dekho api/routes/video_ads.py).
 */
export type PromptSource = 'form' | 'ai' | 'manual'

/**
 * "Your idea, in your own words" ki hadd — backend ke MAX_IDEA_CHARS ke barabar
 * (modules/video_ads/schemas.py). Yahan sirf counter aur maxLength ke liye hai;
 * asal enforcement backend par hoti hai.
 */
export const MAX_IDEA_CHARS = 300

/** Backend: POST /api/video-studio/draft-prompt */
export interface DraftPromptPayload {
  brand_id: number
  /**
   * Wahi do raste jo generate par hain. image_ad par catalogue ka product
   * backend us bane hue ad ke record se dhoondta hai (generated_ads.product_id).
   */
  source?: VideoSource
  /**
   * Sirf context ke liye (naam/category/description) — video ka input nahi.
   * Na mile to draft phir bhi banta hai, bas thora aam.
   */
  product_id?: number | null
  product_index?: number | null
  /** source='image_ad' ke liye — generated_ads.id */
  source_ad_id?: number | null
  ad_style?: string | null
  scene?: string | null
  mood?: string | null
  camera_motion?: string | null
  lighting?: string | null
  pacing?: string | null
  /** Woh EK line jo user ne apne alfaz mein likhi — Roman Urdu bhi chalti hai. */
  idea?: string | null
}

export interface DraftedPrompts {
  /** Teen options — user chunta hai, phir chahe to edit karta hai. */
  prompts: string[]
  /**
   * Woh farmaishein jo fixed rules rok dengi (frame mein text, ya product ki
   * tabdeeli). Prompt phir bhi banta hai; ye sirf batati hain ke kya nahi hoga.
   */
  warnings: string[]
}

export interface GenerateVideoAdPayload {
  brand_id: number
  user_id: string
  source: VideoSource
  /** source='product' ke liye — authoritative selector. */
  product_id?: number | null
  /** Sirf un purane profiles ke liye jo product ids se pehle scrape hue the. */
  product_index?: number | null
  /** source='image_ad' ke liye — generated_ads.id */
  source_ad_id?: number | null
  ad_style?: string | null
  scene?: string | null
  mood?: string | null
  camera_motion?: string | null
  lighting?: string | null
  pacing?: string | null
  /** Bhara ho to yehi creative direction banta hai aur presets chhor diye jate hain. */
    custom_prompt?: string | null
  /** custom_prompt kahan se aaya — dekho PromptSource. */
  prompt_source?: PromptSource | null
  /**
   * Video ke aakhir mein chhapne wala text. Provider ko NAHI jata — server par
   * moviepy se lagta hai, is liye koi generation credit nahi lagta aur video
   * ~3s lambi ho jati hai.
   */
  end_card_text?: string | null
  duration_seconds: number
  /**
   * Kaun sa provider chalega — "free" -> Kling, "premium" -> Veo 3.1.
   * Abhi koi asal billing nahi; yeh sirf ek flag hai. Anjaan value backend par
   * chup-chaap "free" ban jati hai.
   */
  user_plan: string
}

/** Backend: GenerateVideoAdResponse */
export interface GeneratedVideoAd {
  success: boolean
  video_id: number
  video_url: string
  product_name: string | null
  duration_seconds: number
  segments: number
    model_id: string
  provider: string
  user_plan: string
  /**
   * Prompt parha nahi ja saka aur form ke options se video bana — UI ye line
   * dikhati hai. Warna user samajhta hai ke uska prompt chala tha.
   */
  prompt_notice?: string | null
  /** Aakhir mein end card laga ya nahi. */
  end_card?: boolean
}

export interface VideoGalleryItem {
  video_id: number
  product_name: string | null
  video_path: string
  duration_seconds: number | null
  segments: number | null
  source: string | null
  provider: string | null
  user_plan: string | null
  created_at: string
}

export interface VideoGalleryDetail extends VideoGalleryItem {
  source_image_url: string | null
  ad_style: string | null
  scene: string | null
  mood: string | null
  camera_motion: string | null
  lighting: string | null
  pacing: string | null
  custom_prompt: string | null
  prompt_source: string | null
  model_id: string | null
  final_prompt: string | null
}

export const videoAdsApi = {
  getOptions: () =>
    fetch(`${VIDEO_ADS_API}/options`).then((r) =>
      readJsonOrThrow<VideoAdOptions>(r)
    ),

  /**
   * "Write the prompt for me" — form ke jawabat + user ki ek line se teen
   * prompt options.
   *
   * Ye call SASTI aur TEZ hai (ek chhoti text LLM call, ~3s) aur is mein koi
   * video credit KHARCH NAHI hota — generate se bilkul alag rasta hai. Isi liye
   * user ise baar baar chala sakta hai aur prompt dekh kar hi generate dabata
   * hai.
   */
  draftPrompt: async (payload: DraftPromptPayload) => {
    const res = await fetch(`${VIDEO_ADS_API}/draft-prompt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
      body: JSON.stringify(payload),
    })
    return readJsonOrThrow<DraftedPrompts>(res)
  },

  /**
   * Yeh call MINUTES leti hai: har length 1-3 billable generations chalati hai
   * (kitni — provider par munhasir, /options batata hai) aur har generation
   * khud kai minute leti hai. Is liye yahan koi client-side
   * timeout NAHI lagaya gaya — abort karne se generation phir bhi chalti rehti
   * aur bill lag jata, magar result kabhi save na hota.
   */
  generate: async (payload: GenerateVideoAdPayload) => {
    const res = await fetch(`${VIDEO_ADS_API}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
      body: JSON.stringify(payload),
    })
    return readJsonOrThrow<GeneratedVideoAd>(res)
  },

  getGallery: async (userId: string) => {
    const res = await fetch(`${VIDEO_ADS_API}/gallery/${userId}`, {
      headers: await authHeaders(),
    })
    return readJsonOrThrow<VideoGalleryItem[]>(res)
  },

  getGalleryDetail: async (videoId: number) => {
    const res = await fetch(`${VIDEO_ADS_API}/gallery/detail/${videoId}`, {
      headers: await authHeaders(),
    })
    return readJsonOrThrow<VideoGalleryDetail>(res)
  },
}
