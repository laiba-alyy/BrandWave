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
const ADS_API = `${API_BASE}/api/image-studio`

/**
 * Generate calls pehle seedha `.then(r => r.json())` karti thin — yani 429/500
 * ka error body bhi "success" ki tarah page ko chala jata tha aur user ko
 * `undefined` dikhta tha. Ab backend ka `detail` message Error mein aata hai,
 * jis se rate limit par "Rate limit reached, please wait a minute" nazar aata hai.
 */
/**
 * Credits khatam hone wali nakami — baqi errors se ALAG.
 *
 * Backend is soorat mein 402 deta hai (dekho services/common.py). UI ko farq
 * pata hona chahiye kyunke ilaaj alag hai: "try again" yahan bekaar hai.
 */
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
        if (res.status === 402) throw new OutOfCreditsError(detail)
    throw new Error(detail)
  }

  return body as T
}

/**
 * List endpoints ke liye — jawab ko ARRAY hone par majboor karta hai.
 *
 * `res.json() as Promise<Brand[]>` ek jhoot tha: TypeScript ko yaqeen dila
 * deta tha ke array aayi hai, jab ke 401/403/500 par backend `{"detail": ...}`
 * bhejta hai. Wo object seedha state mein chala jata aur page bahut door ja kar
 * "brands.find is not a function" par crash karta — asli wajah (auth/500) kahin
 * nazar nahi aati thi. Ab error yahin, apne asli message ke saath, phenka jata
 * hai; aur jawab agar kisi wajah se array na ho to khali list milti hai bajaye
 * crash ke.
 */
async function readArrayOrThrow<T>(res: Response): Promise<T[]> {
  const body = await readJsonOrThrow<unknown>(res)
  if (Array.isArray(body)) return body as T[]
  // Kuch endpoints {data: [...]} lifafe mein bhejte hain
  const wrapped = (body as { data?: unknown } | null)?.data
  if (Array.isArray(wrapped)) return wrapped as T[]
  return []
}

export function toImageUrl(path: string): string {
  const cleaned = path.replace(/\\/g, '/').replace(/^generated_ads\//, '')
  return `${API_BASE}/static/${cleaned}`
}

/**
 * How the base ad image is produced. Backend registry:
 * modules/ads_generation/services/dispatch.py
 */
export type GenerationMode = 'scene' | 'on_model'

export const GENERATION_MODES: {
  key: GenerationMode
  label: string
  blurb: string
  hint: string
}[] = [
  {
    key: 'scene',
    label: 'Change scene',
    blurb: 'Product or model already in the photo',
    hint: 'Keeps the photo exactly as-is and builds a new background around it. Best for bags, bottles, jewellery, and clothing already shot on a model.',
  },
  {
    key: 'on_model',
    label: 'Put on a model',
    blurb: 'Flat-lay or mannequin garment',
    hint: 'Places the garment on a generated fashion model. Only for clothing photos with no person in them.',
  },
]

export interface Brand {
  id: number
  business_name: string | null
  website_url: string
}

export interface Product {
  /** Shopify product id — authoritative selector when generating an ad. */
  id: number | null
  /** Position in the catalogue. Display/legacy only: rescrape shifts it. */
  index: number
  name: string
  price: string | null
  description: string | null
  image_url: string | null
  category: string | null
}

export interface ProductListResponse {
  products: Product[]
  total_products: number
  offset: number
  limit: number
}

/** Backend: GenerateImageAdResponse */
export interface GeneratedAd {
  success: boolean
  ad_id: number
  ad_image_url: string
  product_name: string
  headline: string
  caption: string
  hashtags: string[]
}

/** Backend: GenerateVideoAdResponse */
export interface GeneratedVideo {
  success: boolean
  ad_video_url: string
}

export interface GalleryItem {
  ad_id: number
  product_name: string
  image_path: string
  video_path: string | null
  created_at: string
}

export interface GalleryDetail extends GalleryItem {
  headline: string | null
  caption: string | null
  hashtags: string | null
  aspect_ratio: string | null
  platform: string | null
  mood: string | null
}

export const adsApi = {
  getMyBrands: async (userId: string) => {
    const res = await fetch(`${ADS_API}/my-brands/${userId}`, {
      headers: await authHeaders(),
    })
    return readArrayOrThrow<Brand>(res)
  },

  // user_id ownership check ke liye jata hai — backend confirm karta hai ke
  // brand isi account ka hai.
  searchProducts: async (brandId: number, query: string, userId?: string) => {
    const res = await fetch(
      `${ADS_API}/products/search?brand_id=${brandId}&query=${encodeURIComponent(query)}` +
        (userId ? `&user_id=${encodeURIComponent(userId)}` : ''),
      { headers: await authHeaders() }
    )
    return readArrayOrThrow<Product>(res)
  },

  listProducts: async (brandId: number, offset = 0, limit = 20, userId?: string) => {
    const res = await fetch(
      `${ADS_API}/products/${brandId}?offset=${offset}&limit=${limit}` +
        (userId ? `&user_id=${encodeURIComponent(userId)}` : ''),
      { headers: await authHeaders() }
    )
    return readJsonOrThrow<ProductListResponse>(res)
  },

  generateImage: async (payload: {
    brand_id: number
    /** Authoritative. Backend 404s if this id is gone rather than picking the wrong product. */
    product_id: number | null
    /** Only for legacy profiles scraped before product ids existed. */
    product_index?: number | null
    /**
     * Which service builds the base image. Both keep the real product pixels —
     * neither repaints it.
     *   'scene'    Bria  — product (or model) is already in the photo, swap the background
     *   'on_model' Claid — flat/mannequin garment photo, put it on a generated model
     * Omitted = 'scene' on the backend.
     */
    generation_mode?: GenerationMode
    aspect_ratio: string
    platform: string
    cta_goal: string
    mood: string
    occasion: string
        custom_prompt: string | null
    /** Jo user IMAGE PAR likhwana chahta hai. Khali = AI ka headline lagega. */
    ad_text?: string | null
    /** Button ka apna text. Khali = cta_goal ya AI ka CTA. */
    ad_cta?: string | null
    user_id: string
  }) => {
    const res = await fetch(`${ADS_API}/generate-image`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
      body: JSON.stringify(payload),
    })
    return readJsonOrThrow<GeneratedAd>(res)
  },

  generateVideo: async (adId: number) => {
    const res = await fetch(`${ADS_API}/generate-video`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
      body: JSON.stringify({ ad_id: adId }),
    })
    return readJsonOrThrow<GeneratedVideo>(res)
  },

  getGallery: async (userId: string) => {
    const res = await fetch(`${ADS_API}/gallery/${userId}`, {
      headers: await authHeaders(),
    })
    return readArrayOrThrow<GalleryItem>(res)
  },

  getGalleryDetail: async (adId: number) => {
    const res = await fetch(`${ADS_API}/gallery/detail/${adId}`, {
      headers: await authHeaders(),
    })
    return readJsonOrThrow<GalleryDetail>(res)
  },
}
export async function downloadFile(url: string, filename: string) {
  try {
    const response = await fetch(url)
    if (!response.ok) throw new Error('File fetch failed')
    const blob = await response.blob()
    const blobUrl = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = blobUrl
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(blobUrl)
  } catch (err) {
    console.error('Download failed, opening in new tab instead:', err)
    // Fallback: naya tab mein khol do, user manually "Save As" kar sakta hai
    window.open(url, '_blank')
  }
}

export async function downloadAdPackage(params: {
  imageUrl: string
  videoUrl?: string | null
  productName: string
  headline: string
  caption: string
  hashtags: string[]
}) {
    // NOTE: pehle yahan @ts-ignore tha "CDN se load hoga" ke comment ke saath.
  // jszip ab package.json mein hai aur apni index.d.ts ke saath aata hai, is
  // liye suppression ki koi zaroorat nahi rahi.
  const JSZip = (await import('jszip')).default
  const zip = new JSZip()

  const imageBlob = await (await fetch(params.imageUrl)).blob()
  zip.file('ad-image.jpg', imageBlob)

  if (params.videoUrl) {
    const videoBlob = await (await fetch(params.videoUrl)).blob()
    zip.file('ad-video.mp4', videoBlob)
  }

  const detailsText = `Product: ${params.productName}

Headline: ${params.headline}

Caption: ${params.caption}

Hashtags: ${params.hashtags.map((h) => '#' + h).join(' ')}
`
  zip.file('ad-details.txt', detailsText)

  const zipBlob = await zip.generateAsync({ type: 'blob' })
  const blobUrl = window.URL.createObjectURL(zipBlob)
  const link = document.createElement('a')
  link.href = blobUrl
  link.download = `${params.productName.replace(/[^a-z0-9]/gi, '_')}_ad_package.zip`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(blobUrl)
}