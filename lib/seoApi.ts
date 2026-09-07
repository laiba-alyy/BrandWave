import { authHeaders } from '@/lib/authHeaders'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

/**
 * SEO generate/read calls ke liye ek hi jagah.
 *
 * Do masle theek karta hai jo pehle har page mein alag alag the:
 *
 * 1. `brand_profile_id: null` bhejna backend ke liye "omitted" ke barabar hai.
 *    Multi-brand account par backend ab guess karne se inkar karta hai aur 400
 *    deta hai. Isliye request bhejne se PEHLE hi rok dete hain aur user ko
 *    saaf batate hain ke brand select karna hai.
 *
 * 2. Pages `if (res.ok)` + `catch {}` karte the — yani 400/500 CHUP-CHAAP
 *    nigal jate the aur button bas spin karna band kar deta tha. Ab backend ka
 *    `detail` message Error mein aata hai taake UI use dikha sake.
 */
export class BrandNotSelectedError extends Error {
  constructor() {
    super('No brand selected yet. Pick a brand from the switcher, then try again.')
    this.name = 'BrandNotSelectedError'
  }
}

async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json()
    // FastAPI HTTPException -> {detail: "..."}; validation errors -> {detail: [...]}
    if (typeof body?.detail === 'string') return body.detail
    if (Array.isArray(body?.detail)) {
      return body.detail.map((d: { msg?: string }) => d?.msg).filter(Boolean).join('; ')
        || `Request failed (${res.status})`
    }
    if (typeof body?.message === 'string') return body.message
  } catch {
    // non-JSON body
  }
  return `Request failed (${res.status})`
}

export async function seoPost<T = unknown>(
  path: string,
  userId: string,
  activeBrandId: number | null,
  extra: Record<string, unknown> = {}
): Promise<T> {
  if (activeBrandId == null) throw new BrandNotSelectedError()
  if (!userId) throw new Error('Not signed in.')

  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
    body: JSON.stringify({ user_id: userId, brand_profile_id: activeBrandId, ...extra }),
  })

  if (!res.ok) throw new Error(await readError(res))
  return res.json() as Promise<T>
}

export async function seoGet<T = unknown>(
  path: string,
  activeBrandId: number | null,
  params: Record<string, string> = {}
): Promise<T | null> {
  const qs = new URLSearchParams(params)
  if (activeBrandId != null) qs.set('brand_profile_id', String(activeBrandId))
  const res = await fetch(`${API_URL}${path}?${qs.toString()}`, {
    headers: await authHeaders(),
  })
  // 404 = "kuch generate nahi hua abhi" — ye error nahi, empty state hai
  if (res.status === 404) return null
  if (!res.ok) throw new Error(await readError(res))
  return res.json() as Promise<T>
}
