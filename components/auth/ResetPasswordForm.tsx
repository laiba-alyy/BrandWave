'use client'

/*
 * Step 2 of password recovery — naya password set karta hai.
 *
 * Recovery link teen shakalon mein aa sakta hai:
 *   1. pkce      → ?code=…                        (auth-js `resetPasswordForEmail`
 *                  par hamesha code_challenge bhejta hai, chahe client ka
 *                  flowType 'implicit' hi kyun na ho — is liye amooman yehi)
 *   2. implicit  → #access_token=…&type=recovery
 *   3. otp       → ?token_hash=…&type=recovery     (naye email templates)
 *
 * ZAROORI — pehle `getSession()`, phir koi manual exchange:
 * supabase-js apne `_initialize()` mein pehle (1) aur (2) dono khud consume kar
 * leta hai jab `detectSessionInUrl` on ho, aur `getSession()` usi initialize
 * promise ke peeche khara hai. Agar hum pehle `exchangeCodeForSession(code)`
 * chalayen to code pehle hi istemal ho chuka hota aur verifier storage se hat
 * chuka hota — call fail hoti aur hum ek KAAMYAB session ke bawajood "link
 * expired" dikha dete. Manual raste sirf tab chahiye jab getSession() khali ho:
 * `token_hash` ko auth-js khud handle nahi karta.
 *
 * Password update hone ke baad session ko sign out kiya jata hai taake user
 * naye password se dobara login kare — warna recovery session chupke se ek
 * poori logged-in session ban jati hai.
 */
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { createClient } from '@/lib/supabase'
import {
  passwordChecks,
  resetPasswordSchema,
  type ResetPasswordInput,
} from '@/lib/validators/auth'
import {
  Alert,
  AuthBrand,
  IconArrow,
  IconArrowLeft,
  IconCheck,
  IconEye,
  IconKeyBig,
  IconLock,
  Spinner,
} from '@/components/auth/ui'

type LinkState = 'checking' | 'valid' | 'invalid'

const INVALID_MESSAGE =
  'This reset link is invalid or has expired. Request a fresh one and try again.'

export default function ResetPasswordForm() {
  const router = useRouter()
  const [supabase] = useState(() => createClient())
  const [linkState, setLinkState] = useState<LinkState>('checking')
  const [linkError, setLinkError] = useState(INVALID_MESSAGE)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showPassword, setShowPassword] = useState(false)

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<ResetPasswordInput>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: { password: '', confirmPassword: '' },
  })

  const password = watch('password') ?? ''
  const checks = passwordChecks(password)

  useEffect(() => {
    let cancelled = false

    const verifyLink = async () => {
      try {
        const url = new URL(window.location.href)
        const hash = new URLSearchParams(url.hash.replace(/^#/, ''))

        const linkFailure =
          hash.get('error_description') ||
          hash.get('error') ||
          url.searchParams.get('error_description') ||
          url.searchParams.get('error')
        if (linkFailure) {
          if (!cancelled) {
            setLinkError(linkFailure.replace(/\+/g, ' '))
            setLinkState('invalid')
          }
          return
        }

        // Ye await supabase-js ke initialize ko bhi await karta hai, yani URL
        // walay code/hash ka faisla ho chuka hota hai.
        const { data, error: sessionError } = await supabase.auth.getSession()
        if (sessionError) throw sessionError
        let session = data.session

        if (!session) {
          const tokenHash = url.searchParams.get('token_hash') || url.searchParams.get('token')
          const code = url.searchParams.get('code')

          if (tokenHash) {
            const { data: otpData, error: otpError } = await supabase.auth.verifyOtp({
              token_hash: tokenHash,
              type: 'recovery',
            })
            if (otpError) throw otpError
            session = otpData.session
          } else if (code) {
            // Yahan aana ka matlab: verifier is browser mein nahi mila (link
            // kisi aur browser/device par khola gaya). Ek koshish phir bhi,
            // taake error message Supabase ka asal message ho.
            const { data: codeData, error: exchangeError } =
              await supabase.auth.exchangeCodeForSession(code)
            if (exchangeError) throw exchangeError
            session = codeData.session
          }
        }

        if (cancelled) return

        if (session) {
          setLinkState('valid')
          // Token URL se hata dein — reload/share par leak na ho.
          window.history.replaceState({}, '', window.location.pathname)
        } else {
          setLinkError(INVALID_MESSAGE)
          setLinkState('invalid')
        }
      } catch (err) {
        if (cancelled) return
        setLinkError(err instanceof Error ? err.message : INVALID_MESSAGE)
        setLinkState('invalid')
      }
    }

    verifyLink()
    return () => {
      cancelled = true
    }
  }, [supabase])

  const onSubmit = async (values: ResetPasswordInput) => {
    try {
      setLoading(true)
      setError(null)
      const { error: updateError } = await supabase.auth.updateUser({
        password: values.password,
      })
      if (updateError) throw updateError

      await supabase.auth.signOut()
      router.replace('/login?reset=1')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update your password')
      setLoading(false)
    }
  }

  if (linkState === 'checking') {
    return (
      <>
        <AuthBrand />
        <div className="au__confirm">
          <div className="au__mark">
            <Spinner />
          </div>
          <p className="au__eyebrow">One moment</p>
          <h1 className="au__title">Checking your link…</h1>
        </div>
      </>
    )
  }

  if (linkState === 'invalid') {
    return (
      <>
        <AuthBrand />
        <div className="au__confirm">
          <div className="au__mark au__mark--rose">
            <IconKeyBig />
          </div>
          <p className="au__eyebrow">Link problem</p>
          <h1 className="au__title">This link no longer works</h1>
          <p className="au__lede">{linkError}</p>
          <Link className="au__btn au__btn--primary au__submit" href="/forgot-password">
            Request a new link
            <IconArrow />
          </Link>
          <Link className="au__back" href="/login">
            <IconArrowLeft />
            Back to sign in
          </Link>
        </div>
      </>
    )
  }

  return (
    <>
      <AuthBrand />

      <div className="au__head">
        <p className="au__eyebrow">Almost done</p>
        <h1 className="au__title">
          Set a new <em>password</em>
        </h1>
        <p className="au__lede">
          Choose something you have not used here before. You will sign in again with it.
        </p>
      </div>

      {error && <Alert kind="error">{error}</Alert>}

      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <div className="au__fields">
          <div className="au__field">
            <label htmlFor="reset-password">New password</label>
            <div className="au__input au__input--pw">
              <IconLock />
              <input
                id="reset-password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="new-password"
                placeholder="••••••••"
                {...register('password')}
              />
              <button
                type="button"
                className="au__eye"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                <IconEye off={showPassword} />
              </button>
            </div>

            {password.length > 0 && (
              <div className="au__rules">
                {[
                  { label: 'At least 8 characters', on: checks.minLength },
                  { label: 'One uppercase letter', on: checks.hasUppercase },
                  { label: 'One special character', on: checks.hasSpecial },
                ].map((rule) => (
                  <div key={rule.label} className={`au__rule${rule.on ? ' au__rule--on' : ''}`}>
                    <span className="au__rule-dot">
                      <IconCheck />
                    </span>
                    {rule.label}
                  </div>
                ))}
              </div>
            )}
            {errors.password && <p className="au__err">{errors.password.message}</p>}
          </div>

          <div className="au__field">
            <label htmlFor="reset-confirm">Confirm new password</label>
            <div className="au__input au__input--pw">
              <IconLock />
              <input
                id="reset-confirm"
                type={showPassword ? 'text' : 'password'}
                autoComplete="new-password"
                placeholder="••••••••"
                {...register('confirmPassword')}
              />
            </div>
            {errors.confirmPassword && <p className="au__err">{errors.confirmPassword.message}</p>}
          </div>
        </div>

        <button type="submit" className="au__btn au__btn--primary au__submit" disabled={loading}>
          {loading ? <Spinner /> : null}
          {loading ? 'Updating…' : 'Update password'}
          {loading ? null : <IconArrow />}
        </button>
      </form>

      <p className="au__foot">
        Changed your mind? <Link href="/login">Back to sign in</Link>
      </p>
    </>
  )
}
