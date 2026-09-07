import AuthShell, { AuthForm } from '@/components/auth/AuthShell'
import AuthPanel from '@/components/auth/AuthPanel'
import SignupForm from '@/components/auth/SignupForm'

export const metadata = {
  title: 'Create your account — BrandWave',
  description: 'Create your BrandWave account and connect your first store.',
}

/*
 * Pehle ye route /role-selection par redirect karta tha (Business owner vs
 * Administrator). Wo screen hata di gayi — har naya account brand owner hai —
 * is liye ab signup form seedha yahan render hota hai.
 */
export default function SignupPage() {
  return (
    <AuthShell wide>
      <AuthForm>
        <SignupForm />
      </AuthForm>

      <AuthPanel
        eyebrow="Free to start"
        title="Connect the store."
        accent="Read what it says."
        quote="We stopped guessing what customers wanted. It was in our own reviews all along."
        by="Founder, DTC skincare"
        stats={[
          { value: '500+', label: 'Active stores' },
          { value: '98%', label: 'Satisfaction' },
          { value: '30s', label: 'Setup time' },
        ]}
      />
    </AuthShell>
  )
}
