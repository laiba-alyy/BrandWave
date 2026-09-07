'use client'

import { useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { createClient } from '@/lib/supabase'
import { loginSchema, type LoginInput } from '@/lib/validators/auth'
import {
  Alert,
  AuthBrand,
  IconArrow,
  IconEye,
  IconGoogle,
  IconLock,
  IconMail,
  Spinner,
} from '@/components/auth/ui'

export default function LoginForm() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const supabase = createClient()
  const [loading, setLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [generalError, setGeneralError] = useState<string | null>(null)
  const [showPassword, setShowPassword] = useState(false)

  const emailVerified = searchParams.get('verified') === '1'
  const passwordReset = searchParams.get('reset') === '1'

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  })

  const onEmailSubmit = async (data: LoginInput) => {
    try {
      setLoading(true)
      setGeneralError(null)
      const { data: authData, error: authError } = await supabase.auth.signInWithPassword({
        email: data.email.trim().toLowerCase(),
        password: data.password,
      })
      if (authError) throw new Error(authError.message)

      const { data: userData, error: userError } = await supabase
        .from('users').select('id, business_name, email_verified, role')
        .eq('id', authData.user.id).maybeSingle()
      if (userError) throw new Error(userError.message)

      let appUser = userData
      if (!appUser) {
        const businessName = (authData.user.user_metadata?.business_name as string)?.trim() || 'My Business'
        const inferredRole = authData.user.user_metadata?.role === 'admin' ? 'admin' : 'user'
        const { data: insertedUser, error: insertError } = await supabase
          .from('users').insert({
            id: authData.user.id, email: authData.user.email,
            business_name: businessName, role: inferredRole,
            email_verified: true, auth_provider: 'email',
          }).select('id, business_name, email_verified, role').single()
        if (insertError) throw new Error(insertError.message)
        appUser = insertedUser
      }

      if (!appUser.email_verified) {
        await supabase.from('users').update({ email_verified: true }).eq('id', authData.user.id)
      }

      router.push(appUser.role === 'admin' ? '/admin' : '/business')
    } catch (err) {
      setGeneralError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleSignIn = async () => {
    try {
      setGoogleLoading(true)
      setGeneralError(null)
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: `${window.location.origin}/auth/callback`,
          queryParams: { prompt: 'select_account' },
        },
      })
      if (error) throw error
    } catch (err) {
      setGeneralError(err instanceof Error ? err.message : 'Google sign in failed')
      setGoogleLoading(false)
    }
  }

  /*
   * "Forgot password?" pehle ek dead <button> tha — koi handler hi nahi tha.
   * Ab /forgot-password par le jata hai aur jo email pehle se type ho chuki hai
   * wohi query mein saath chali jati hai, taake dobara likhni na pare.
   *
   * `watch` chahiye, `getValues` nahi: RHF ke fields uncontrolled hain, to
   * getValues typing par re-render trigger nahi karta aur href hamesha pehle
   * render wali (khali) value par atka reh jata hai.
   */
  const typedEmail = watch('email')?.trim()
  const forgotHref = typedEmail
    ? `/forgot-password?email=${encodeURIComponent(typedEmail)}`
    : '/forgot-password'

  const busy = loading || googleLoading

  return (
    <>
      <AuthBrand />

      <div className="au__head">
        <h1 className="au__title">
          Sign in to your <em>account</em>
        </h1>
      </div>

      {emailVerified && <Alert kind="ok">Email verified. You can sign in now.</Alert>}
      {passwordReset && <Alert kind="ok">Password updated. Sign in with your new password.</Alert>}
      {generalError && <Alert kind="error">{generalError}</Alert>}

      <form onSubmit={handleSubmit(onEmailSubmit)} noValidate>
        <div className="au__fields">
          <div className="au__field">
            <label htmlFor="login-email">Email address</label>
            <div className="au__input">
              <IconMail />
              <input
                id="login-email"
                type="email"
                autoComplete="email"
                placeholder="you@yourstore.com"
                {...register('email')}
              />
            </div>
            {errors.email && <p className="au__err">{errors.email.message}</p>}
          </div>

          <div className="au__field">
            <div className="au__labelrow">
              <label htmlFor="login-password">Password</label>
              <Link className="au__link" href={forgotHref}>
                Forgot password?
              </Link>
            </div>
            <div className="au__input au__input--pw">
              <IconLock />
              <input
                id="login-password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
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
            {errors.password && <p className="au__err">{errors.password.message}</p>}
          </div>
        </div>

        <div className="au__row">
          <label className="au__check">
            <input type="checkbox" name="remember" defaultChecked />
            Keep me signed in
          </label>
        </div>

        <button type="submit" className="au__btn au__btn--primary au__submit" disabled={busy}>
          {loading ? <Spinner /> : null}
          {loading ? 'Signing in…' : 'Sign in'}
          {loading ? null : <IconArrow />}
        </button>
      </form>

      <div className="au__or">or</div>

      <button
        type="button"
        className="au__btn au__btn--ghost"
        onClick={handleGoogleSignIn}
        disabled={busy}
      >
        {googleLoading ? <Spinner /> : <IconGoogle />}
        {googleLoading ? 'Redirecting…' : 'Continue with Google'}
      </button>

      <p className="au__foot">
        New to BrandWave? <Link href="/signup">Create an account</Link>
      </p>
    </>
  )
}
