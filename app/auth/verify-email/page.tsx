'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase'

export default function VerifyEmailPage() {
  const router = useRouter()
  const supabase = createClient()
  const [verifying, setVerifying] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    const verifyEmail = async () => {
      try {
        const url = new URL(window.location.href)
        const code = url.searchParams.get('code')
        const tokenHash = url.searchParams.get('token_hash') || url.searchParams.get('token')
        const typeParam = url.searchParams.get('type')
        const callbackError = url.searchParams.get('error_description') || url.searchParams.get('error')

        if (callbackError) {
          throw new Error(callbackError.replace(/\+/g, ' '))
        }

        let verifiedUser: { id?: string; email?: string | null; user_metadata?: Record<string, unknown> } | null = null

        if (code) {
          const { data: exchangeData, error: exchangeError } =
            await supabase.auth.exchangeCodeForSession(code)
          if (exchangeError) {
            const message = exchangeError.message.toLowerCase()
            if (message.includes('pkce code verifier not found')) {
              // Email link may still have confirmed the user on Supabase side.
              // In that case, let user proceed to login.
              setSuccess(true)
              setTimeout(() => {
                router.push('/login?verified=1')
              }, 1200)
              return
            }
            throw exchangeError
          }
          verifiedUser = exchangeData?.user ?? null
        } else if (tokenHash) {
          const otpType = typeParam === 'signup' ? 'signup' : 'email'
          const { data: verifyData, error: verifyError } = await supabase.auth.verifyOtp({
            token_hash: tokenHash,
            type: otpType,
          })
          if (verifyError) throw verifyError
          verifiedUser = verifyData?.user ?? null
        } else {
          throw new Error('Invalid verification link')
        }

        if (!verifiedUser?.id || !verifiedUser?.email) {
          throw new Error('Email verified but user data is unavailable. Please login.')
        }

        const businessName =
          (verifiedUser.user_metadata?.business_name as string | undefined)?.trim() ||
          'My Business'

        // `role` aur `email_verified` yahan se nikal diye gaye hain — dono ab
        // client ke likhne wale columns nahi rahe (dekho db/policies.sql).
        //
        // ignoreDuplicates isliye: upsert `INSERT ... ON CONFLICT DO UPDATE`
        // banta hai, aur DO UPDATE ko har us column par UPDATE ka haq chahiye
        // jo wo naam leta hai. Row pehle se mojood ho to hamein kuch badalna
        // hi nahi — is liye ON CONFLICT DO NOTHING kaafi hai, jo sirf INSERT
        // ka grant maangta hai.
        const { error: upsertError } = await supabase.from('users').upsert({
          id: verifiedUser.id,
          email: verifiedUser.email,
          business_name: businessName,
          auth_provider: 'email',
        }, { onConflict: 'id', ignoreDuplicates: true })
        if (upsertError) throw upsertError

        setSuccess(true)
        setTimeout(() => {
          router.push('/login?verified=1')
        }, 1500)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Verification failed')
      } finally {
        setVerifying(false)
      }
    }

    verifyEmail()
  }, [router, supabase])

  return (
    <main className="min-h-screen bg-gradient-to-br from-blue-600 to-purple-700 flex items-center justify-center px-4">
      <div className="bg-white rounded-2xl shadow-xl p-8 text-center max-w-md w-full">
        {verifying ? (
          <>
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
            <p className="text-gray-700 font-semibold">Verifying your email...</p>
          </>
        ) : success ? (
          <>
            <div className="text-green-600 text-5xl mb-4">✓</div>
            <p className="text-gray-700 font-semibold mb-2">Email verified successfully!</p>
            <p className="text-gray-600 text-sm">Redirecting to login...</p>
          </>
        ) : (
          <>
            <div className="text-red-600 text-5xl mb-4">✗</div>
            <p className="text-red-600 font-semibold mb-4">{error}</p>
            <button
              onClick={() => router.push('/signup')}
              className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700"
            >
              Back to Signup
            </button>
          </>
        )}
      </div>
    </main>
  )
}
