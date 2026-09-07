/**
 * Shared helper that returns `{ Authorization: "Bearer <token>" }` for
 * every backend fetch call.
 *
 * Before this existed, every page sent `user_id` in the request body or
 * URL and the backend blindly trusted it.  Now the backend verifies a
 * Supabase access token instead, and every caller needs to attach it.
 *
 * Usage:
 *   const res = await fetch(url, {
 *     headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
 *     ...
 *   })
 *
 * If the user is not logged in (no session), the function throws so the
 * caller can redirect to /login rather than silently sending an
 * unauthenticated request that will 401.
 */
import { createClient } from '@/lib/supabase'

let _supabase: ReturnType<typeof createClient> | null = null

function getSupabase() {
  if (!_supabase) _supabase = createClient()
  return _supabase
}

export async function authHeaders(): Promise<Record<string, string>> {
  const supabase = getSupabase()
  const { data, error } = await supabase.auth.getSession()
  if (error || !data.session?.access_token) {
    throw new Error('Not signed in — please log in again.')
  }
  return { Authorization: `Bearer ${data.session.access_token}` }
}

/**
 * Convenience: returns the current user's id from the active session,
 * or null if not logged in.  Faster than `getUser()` because it reads
 * the local session rather than calling Supabase's /user endpoint.
 */
export async function currentUserId(): Promise<string | null> {
  const supabase = getSupabase()
  const { data } = await supabase.auth.getSession()
  return data.session?.user?.id ?? null
}
