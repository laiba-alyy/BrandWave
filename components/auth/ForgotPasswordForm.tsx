'use client'

/*
 * Step 1 of password recovery — reset link bhejta hai.
 *
 * Login par "Forgot password?" pehle sirf ek dead <button> tha; ab ye screen
 * uska asli anjaam hai. `redirectTo` /reset-password par jata hai — wohi route
 * Supabase Dashboard → Authentication → URL Configuration ke Redirect URLs
 * mein bhi allowed hona chahiye, warna link login par wapas phenk dega.
 *
 * Jawab hamesha ek jaisa "sent" screen hai chahe email registered ho ya na ho:
 * warna ye form email-enumeration oracle ban jata. Supabase khud bhi
 * resetPasswordForEmail par non-existent email ke liye error nahi deta.
 */
import { useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { createClient } from '@/lib/supabase'
import { forgotPasswordSchema, type ForgotPasswordInput } from '@/lib/validators/auth'
import {
  Alert,
  AuthBrand,
  IconArrow,
  IconArrowLeft,
  IconEnvelopeBig,
  IconKeyBig,
  IconMail,
  Spinner,
} from '@/components/auth/ui'

export default function ForgotPasswordForm() {
  const supabase = createClient()
  const searchParams = useSearchParams()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sentTo, setSentTo] = useState<string | null>(null)
  const [resent, setResent] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ForgotPasswordInput>({
    resolver: zodResolver(forgotPasswordSchema),
    // Login form typed-in email ko query mein aage bhejta hai.
    defaultValues: { email: searchParams.get('email') ?? '' },
  })

  const sendLink = async (email: string) => {
    const { error: resetError } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/reset-password`,
    })
    if (resetError) throw resetError
  }

  const onSubmit = async (values: ForgotPasswordInput) => {
    const email = values.email.trim().toLowerCase()
    try {
      setLoading(true)
      setError(null)
      await sendLink(email)
      setSentTo(email)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not send the reset link')
    } finally {
      setLoading(false)
    }
  }

  const onResend = async () => {
    if (!sentTo) return
    try {
      setLoading(true)
      setError(null)
      await sendLink(sentTo)
      setResent(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not resend the reset link')
    } finally {
      setLoading(false)
    }
  }

  if (sentTo) {
    return (
      <>
        <AuthBrand />
        <div className="au__confirm">
          <div className="au__mark au__mark--amber">
            <IconEnvelopeBig />
          </div>
          <p className="au__eyebrow">Link sent</p>
          <h1 className="au__title">Check your inbox</h1>
          <p className="au__lede">If an account exists for</p>
          <span className="au__mail">{sentTo}</span>
          <p className="au__lede">
            you will get a reset link within a minute. It expires in one hour — check
            spam if it has not landed.
          </p>

          {error && <Alert kind="error">{error}</Alert>}
          {resent && !error && <Alert kind="ok">Sent again. Give it a moment.</Alert>}

          <button
            type="button"
            className="au__btn au__btn--ghost au__submit"
            onClick={onResend}
            disabled={loading}
          >
            {loading ? <Spinner /> : null}
            {loading ? 'Sending…' : 'Resend link'}
          </button>

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

      <div className="au__confirm">
        <div className="au__mark">
          <IconKeyBig />
        </div>
        <p className="au__eyebrow">Password recovery</p>
        <h1 className="au__title">
          Forgot your <em>password</em>?
        </h1>
        <p className="au__lede">
          Type the email you signed up with and we will send you a link to set a new
          one.
        </p>
      </div>

      {error && <Alert kind="error">{error}</Alert>}

      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <div className="au__fields">
          <div className="au__field">
            <label htmlFor="forgot-email">Email address</label>
            <div className="au__input">
              <IconMail />
              <input
                id="forgot-email"
                type="email"
                autoComplete="email"
                placeholder="you@yourstore.com"
                {...register('email')}
              />
            </div>
            {errors.email && <p className="au__err">{errors.email.message}</p>}
          </div>
        </div>

        <button type="submit" className="au__btn au__btn--primary au__submit" disabled={loading}>
          {loading ? <Spinner /> : null}
          {loading ? 'Sending link…' : 'Send reset link'}
          {loading ? null : <IconArrow />}
        </button>
      </form>

      <p className="au__foot">
        Remembered it? <Link href="/login">Back to sign in</Link>
      </p>
    </>
  )
}
