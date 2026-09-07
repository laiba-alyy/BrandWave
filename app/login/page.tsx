import { Suspense } from 'react'

import AuthShell, { AuthForm } from '@/components/auth/AuthShell'
import AuthPanel from '@/components/auth/AuthPanel'
import LoginForm from '@/components/auth/LoginForm'
import { AuthBrand, Spinner } from '@/components/auth/ui'

export const metadata = {
  title: 'Sign in — BrandWave',
  description: 'Sign in to your BrandWave dashboard.',
}

export default function LoginPage() {
  return (
    <AuthShell>
      <AuthForm>
        {/* LoginForm useSearchParams() call karta hai — Suspense boundary ke
            baghair `next build` /login prerender par fail ho jata hai. */}
        <Suspense
          fallback={
            <>
              <AuthBrand />
              <div className="au__confirm">
                <div className="au__mark">
                  <Spinner />
                </div>
              </div>
            </>
          }
        >
          <LoginForm />
        </Suspense>
      </AuthForm>

      <AuthPanel
        eyebrow="BrandWave"
        title="Everything your store said,"
        accent="in one place"
        quote="BrandWave took our SEO score from 28 to 74 in a single week."
        by="Shopify store owner"
        stats={[
          { value: '500+', label: 'Active stores' },
          { value: '98%', label: 'Satisfaction' },
          { value: '30s', label: 'Setup time' },
        ]}
      />
    </AuthShell>
  )
}
