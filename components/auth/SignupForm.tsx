'use client'

/*
 * Brand owner signup.
 *
 * Role selection screen hata di gayi hai — BrandWave par sirf ek tarah ka
 * account banta hai, is liye role hamesha 'user' jata hai (auth metadata aur
 * users row dono mein). Admin accounts UI se nahi bante.
 */
import { useState } from 'react'
import Link from 'next/link'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { createClient } from '@/lib/supabase'
import { passwordChecks, signupSchema, type SignupInput } from '@/lib/validators/auth'
import {
  Alert,
  AuthBrand,
  IconArrow,
  IconCheck,
  IconEnvelopeBig,
  IconEye,
  IconGoogle,
  IconLock,
  IconMail,
  IconStore,
  Spinner,
} from '@/components/auth/ui'

export default function SignupForm() {
  const supabase = createClient()
  const [loading, setLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showPassword, setShowPassword] = useState(false)
  const [sentTo, setSentTo] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    watch,
    getValues,
    formState: { errors },
  } = useForm<SignupInput>({
    resolver: zodResolver(signupSchema),
    defaultValues: { businessName: '', email: '', password: '', confirmPassword: '' },
  })

  const password = watch('password') ?? ''
  const checks = passwordChecks(password)

  const onSubmit = async (values: SignupInput) => {
    try {
      setLoading(true)
      setError(null)
      const normalizedEmail = values.email.trim().toLowerCase()

      // Pehle yahan ek "duplicate email" pre-flight check tha jo public.users
      // ko query karta tha. Wo do wajah se hataya gaya:
      //
      // 1. Us waqt visitor abhi `anon` hota hai, aur saari RLS policies
      //    `to authenticated` hain — to query hamesha 0 rows deti thi. Check
      //    khamoshi se HAMESHA pass hone laga tha, yani kaam hi nahi kar raha tha.
      // 2. Isay `anon` ke liye khol dena email-enumeration endpoint bana deta:
      //    koi bhi ek ek email daal kar pata kar leta ke kis ka account hai.
      //
      // Duplicate ka kya hota hai: Supabase JAAN BOOJH KAR error nahi deta.
      // Confirm-email on ho to mojooda email par wo ek user object wapas karta
      // hai jiska `identities` khali hota hai, aur visitor ko wahi "inbox check
      // karein" screen milti hai. Yehi uska anti-enumeration design hai — hum
      // usay bypass karne ki koshish NAHI kar rahe.
      //
      // `role` user_metadata se hata diya gaya. Wo kabhi authoritative tha hi
      // nahi (client jo chahe bhej sakta hai), aur ab koi use bhi nahi karta —
      // chhorne se sirf yeh ghalat-fehmi paida hoti ke role yahan se aata hai.
      const { data, error: signUpError } = await supabase.auth.signUp({
        email: normalizedEmail,
        password: values.password,
        options: {
          emailRedirectTo: `${window.location.origin}/auth/verify-email`,
          data: { business_name: values.businessName.trim() },
        },
      })
      if (signUpError) throw signUpError
      if (!data.user?.id) throw new Error('Unable to create account')

      setSentTo(normalizedEmail)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Signup failed')
    } finally {
      setLoading(false)
    }
  }

  const handleGoogle = async () => {
    try {
      setGoogleLoading(true)
      setError(null)
      sessionStorage.setItem('businessName', getValues('businessName')?.trim() || 'My Business')
      sessionStorage.setItem('selectedRole', 'user')
      const { error: oauthError } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: `${window.location.origin}/auth/callback`,
          queryParams: { prompt: 'select_account' },
        },
      })
      if (oauthError) throw oauthError
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Google signup failed')
      setGoogleLoading(false)
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
          <p className="au__eyebrow">One step left</p>
          <h1 className="au__title">Check your inbox</h1>
          <p className="au__lede">We sent a verification link to</p>
          <span className="au__mail">{sentTo}</span>
          <p className="au__lede">
            Open it to confirm your address, then sign in and connect your first store.
          </p>
          <Link className="au__btn au__btn--ink au__submit" href="/login">
            Go to sign in
            <IconArrow />
          </Link>
        </div>
      </>
    )
  }

  const busy = loading || googleLoading

  return (
    <>
      <AuthBrand />

      <div className="au__head">
        <p className="au__eyebrow">Create your account</p>
        <h1 className="au__title">
          Start reading your <em>store</em>
        </h1>
        <p className="au__lede">
          One account for scraping, SEO, sentiment and your chatbot. No card needed to
          start.
        </p>
      </div>

      {error && <Alert kind="error">{error}</Alert>}

      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <div className="au__fields">
          <div className="au__field">
            <label htmlFor="signup-business">Business name</label>
            <div className="au__input">
              <IconStore />
              <input
                id="signup-business"
                type="text"
                autoComplete="organization"
                placeholder="Your store name"
                {...register('businessName')}
              />
            </div>
            {errors.businessName && <p className="au__err">{errors.businessName.message}</p>}
          </div>

          <div className="au__field">
            <label htmlFor="signup-email">Email address</label>
            <div className="au__input">
              <IconMail />
              <input
                id="signup-email"
                type="email"
                autoComplete="email"
                placeholder="you@yourstore.com"
                {...register('email')}
              />
            </div>
            {errors.email && <p className="au__err">{errors.email.message}</p>}
          </div>

          <div className="au__field">
            <label htmlFor="signup-password">Password</label>
            <div className="au__input au__input--pw">
              <IconLock />
              <input
                id="signup-password"
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
            <label htmlFor="signup-confirm">Confirm password</label>
            <div className="au__input au__input--pw">
              <IconLock />
              <input
                id="signup-confirm"
                type={showPassword ? 'text' : 'password'}
                autoComplete="new-password"
                placeholder="••••••••"
                {...register('confirmPassword')}
              />
            </div>
            {errors.confirmPassword && <p className="au__err">{errors.confirmPassword.message}</p>}
          </div>
        </div>

        <button type="submit" className="au__btn au__btn--primary au__submit" disabled={busy}>
          {loading ? <Spinner /> : null}
          {loading ? 'Creating account…' : 'Create account'}
          {loading ? null : <IconArrow />}
        </button>
      </form>

      <div className="au__or">or</div>

      <button
        type="button"
        className="au__btn au__btn--ghost"
        onClick={handleGoogle}
        disabled={busy}
      >
        {googleLoading ? <Spinner /> : <IconGoogle />}
        {googleLoading ? 'Redirecting…' : 'Continue with Google'}
      </button>

      <p className="au__foot">
        Already have an account? <Link href="/login">Sign in</Link>
      </p>

      <p className="au__legal">
        By creating an account you agree to our terms of service and privacy policy.
      </p>
    </>
  )
}
