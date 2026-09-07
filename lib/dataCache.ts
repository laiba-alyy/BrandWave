'use client'

import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react'

/**
 * Client-side stale-while-revalidate cache.
 *
 * MASLA jo ye hal karta hai:
 * Har page apna data mount par fetch karta tha aur `loading = true` se shuru
 * hota tha. SEO page -> Keywords -> wapas SEO par aane ka matlab tha ke audit
 * score DOBARA network se aata, aur user 2-3 second skeleton dekhta — halanke
 * wahi audit ek second pehle screen par tha aur badla kuch bhi nahi tha.
 * Dashboard ke graphs ke saath bhi bilkul yehi hota tha.
 *
 * HAL:
 * Fetch ka natija module-level Map mein rehta hai. Ye Map client-side
 * navigation ke aar-paar zinda rehta hai (SPA mein module state reload par hi
 * marti hai), is liye dobara us page par aate hi data FORAN mil jata hai —
 * spinner bilkul nahi. Uske baad chup-chaap background revalidate chalta hai,
 * to purana data kabhi screen par atka nahi rehta.
 *
 * Yani: pehli dafa spinner, uske baad instant.
 *
 * Ye jaan boojh kar SWR/react-query ke baghair likha gaya hai — poore app ko
 * ek nayi data-fetching dependency dene ki zaroorat sirf itni si baat ke liye
 * nahi thi.
 *
 * IMPLEMENTATION NOTE — useSyncExternalStore kyun:
 * Ye cache React ke bahar ka store hai, aur React ke paas isi ke liye ek
 * official hook maujood hai. Pehli koshish mein yahan `useState` + `useEffect`
 * tha, jismein effect ke andar setState karna parta tha (cascading renders)
 * aur fetcher ko render ke doran ref mein likhna parta tha — dono cheezein
 * react-hooks lint ne theek hi pakri thin. useSyncExternalStore ke saath
 * component sirf store ko SUNTA hai: koi setState-in-effect nahi.
 */

interface Entry<T> {
  data?: T
  /** Kab cache hui — background revalidate isi se tay hota hai. */
  at: number
  error: string
  fetching: boolean
}

/**
 * Snapshot object har update par NAYA banta hai (kabhi jagah par mutate nahi
 * hota) — useSyncExternalStore reference se change detect karta hai.
 */
const store = new Map<string, Entry<unknown>>()
const listeners = new Map<string, Set<() => void>>()

/** Ek hi key par ek waqt mein sirf EK request (Strict Mode double-effect bhi). */
const inflight = new Map<string, Promise<unknown>>()

/** Itni der ke andar dobara us page par aaye to background refetch bhi nahi. */
const REVALIDATE_AFTER_MS = 15_000

/** key === null wali soorat ke liye ek hi stable object. */
const EMPTY: Entry<never> = { at: 0, error: '', fetching: false }

function emit(key: string): void {
  listeners.get(key)?.forEach((fn) => fn())
}

function write<T>(key: string, patch: Partial<Entry<T>>): void {
  const prev = (store.get(key) as Entry<T> | undefined) ?? { at: 0, error: '', fetching: false }
  store.set(key, { ...prev, ...patch })
  emit(key)
}

export function cacheGet<T>(key: string): T | undefined {
  return store.get(key)?.data as T | undefined
}

export function cacheSet<T>(key: string, data: T): void {
  write<T>(key, { data, at: Date.now(), error: '' })
}

/**
 * Us prefix se shuru hone wali har entry bhula do.
 *
 * Mutations ke baad zaroori hai: audit dobara chalane par keywords ki cached
 * value purani ho jati hai, aur dashboard summary bhi (usmein SEO score hota
 * hai). Prefix isliye ke keys mein brand id bhi shamil hoti hai.
 */
export function cacheInvalidate(prefix: string): void {
  for (const key of Array.from(store.keys())) {
    if (key.startsWith(prefix)) {
      store.delete(key)
      emit(key)
    }
  }
}

export interface CachedData<T> {
  /** Cached ya taza data. Kabhi fetch na hua ho to null. */
  data: T | null
  /** SIRF cold load par true — cache hit par kabhi nahi. Skeleton isi par. */
  loading: boolean
  /** Background refresh chal raha hai. UI chahe to halka sa hint dikhaye. */
  revalidating: boolean
  error: string
  /** Zabardasti network se dobara lao (user ka "Refresh" button). */
  refresh: () => Promise<void>
  /** Cache aur screen dono par nayi value likho (mutation ke baad). */
  mutate: (data: T | null) => void
}

async function load<T>(key: string, fetcher: () => Promise<T>): Promise<void> {
  write<T>(key, { fetching: true })
  try {
    // Wahi key pehle se ja rahi hai to usi promise par sawar ho jao.
    let promise = inflight.get(key) as Promise<T> | undefined
    if (!promise) {
      promise = fetcher()
      inflight.set(key, promise)
      void promise.catch(() => {}).finally(() => {
        if (inflight.get(key) === promise) inflight.delete(key)
      })
    }
    const data = await promise
    write<T>(key, { data, at: Date.now(), error: '', fetching: false })
  } catch (e) {
    // Background refresh nakam ho to purana `data` cache mein rehne do —
    // kaam karti hui screen ko error se badalna behtar nahi.
    write<T>(key, {
      error: e instanceof Error ? e.message : 'Could not load this data',
      fetching: false,
    })
  }
}

/**
 * @param key      cache key — `null` do to hook idle rehta hai (misal: brand
 *                 abhi resolve nahi hui). Key mein brand id zaroor shamil karo.
 * @param fetcher  data laane wala function. `useCallback` mein wrap karo jiski
 *                 deps wohi hon jo key banati hain.
 */
export function useCachedData<T>(
  key: string | null,
  fetcher: () => Promise<T>,
): CachedData<T> {
  // Fetcher ko ref mein rakha jata hai taake fetch-effect sirf `key` par chale.
  // Ye effect JAAN BOOJH KAR fetch-effect se PEHLE declare hai, to mount par
  // ref pehle set hota hai. (useRef ki initial value waise bhi sahi hoti hai.)
  const fetcherRef = useRef(fetcher)
  useEffect(() => { fetcherRef.current = fetcher }, [fetcher])

  const subscribe = useCallback((onChange: () => void) => {
    if (!key) return () => {}
    let set = listeners.get(key)
    if (!set) { set = new Set(); listeners.set(key, set) }
    set.add(onChange)
    return () => {
      set.delete(onChange)
      if (set.size === 0) listeners.delete(key)
    }
  }, [key])

  const getSnapshot = useCallback(
    () => (key ? (store.get(key) as Entry<T> | undefined) ?? EMPTY : EMPTY) as Entry<T>,
    [key],
  )

  // Server par store hamesha khali hai — SSR aur pehla client render match
  // karte hain, hydration mismatch nahi hota.
  const entry = useSyncExternalStore(
    subscribe,
    getSnapshot,
    useCallback(() => EMPTY as Entry<T>, []),
  )

  useEffect(() => {
    if (!key) return
    const current = store.get(key) as Entry<T> | undefined

    // Cache hit aur abhi abhi laya gaya tha — network ko chhero mat.
    if (current?.data !== undefined && Date.now() - current.at < REVALIDATE_AFTER_MS) return
    if (current?.fetching) return

    void load(key, () => fetcherRef.current())
  }, [key])

  const refresh = useCallback(async () => {
    if (key) await load(key, () => fetcherRef.current())
  }, [key])

  const mutate = useCallback((next: T | null) => {
    if (!key) return
    if (next === null) cacheInvalidate(key)
    else cacheSet(key, next)
  }, [key])

  return {
    data: (entry.data ?? null) as T | null,
    // Cold load: abhi tak koi data nahi aaya. Cache hit par ye kabhi true nahi.
    loading: key != null && entry.data === undefined && !entry.error,
    revalidating: entry.fetching && entry.data !== undefined,
    error: entry.error,
    refresh,
    mutate,
  }
}
