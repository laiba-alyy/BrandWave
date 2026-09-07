'use server'

import { createClient } from '@/lib/supabase/server'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

/**
 * Account deletion — ab backend ke cascade endpoint se hoti hai.
 *
 * ── Pehle yahan kya galat tha ──────────────────────────────────────────────
 * Ye action khud do kaam karta tha:
 *   1. Supabase ki `users` row delete
 *   2. `supabase.auth.admin.deleteUser()`
 *
 * Magar client `lib/supabase/server.ts` se aata hai jo ANON key use karta hai,
 * aur admin API sirf service_role se chalti hai — to step 2 hamesha fail hota
 * tha. Us error ko sirf console warning samajh kar action phir bhi
 * `{ success: true }` return kar deta tha.
 *
 * Nateeja: `users` row chali jati thi, auth record ZINDA reh jata tha, aur
 * Neon (brands, SEO, ads) + Pinecone (chatbot vectors) ka poora data orphan
 * ho jata tha — kyunke unhe koi chhoota hi nahi tha.
 *
 * Ab saara cascade backend karta hai (Neon -> Pinecone -> Supabase, isi
 * tarteeb mein), service_role key ke saath, aur fail hone par ASLI error
 * uthati hai — jhooti success nahi.
 */
export async function deleteUserAccount(userId: string) {
  const supabase = await createClient()

  // Backend har delete par token verify karta hai aur confirm karta hai ke
  // token ka user wahi hai jiska account delete ho raha hai. Is ke baghair
  // endpoint se koi bhi kisi ka bhi account uda sakta tha.
  const { data: { session } } = await supabase.auth.getSession()
  if (!session) throw new Error('You must be signed in to delete your account.')
  if (session.user.id !== userId) throw new Error('You can only delete your own account.')

  const res = await fetch(`${API_URL}/api/auth/delete-account/${userId}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${session.access_token}`,
    },
    body: JSON.stringify({ dry_run: false }),
  })

  const payload = await res.json().catch(() => ({}))

  if (!res.ok) {
    // Ye error UI tak jati hai. Purana flow yahan chup ho jata tha, is liye
    // user ko lagta tha account delete ho gaya jabke data waise ka waisa tha.
    throw new Error(payload?.detail || `Account deletion failed (${res.status})`)
  }

  return { success: true, deleted: payload.deleted }
}
