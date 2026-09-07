import { Suspense } from 'react'

import AuthShell from '@/components/auth/AuthShell'
import ForgotPasswordForm from '@/components/auth/ForgotPasswordForm'
import { AuthBrand, Spinner } from '@/components/auth/ui'

export const metadata = {
  title: 'Forgot password — BrandWave',
  description: 'Request a link to reset your BrandWave password.',
}

export default function ForgotPasswordPage() {
  return (
    <AuthShell solo>
      <div className="au__card">
        {/* Form login se aayi hui ?email= padhta hai — useSearchParams ko
            Suspense chahiye warna prerender fail hota hai. */}
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
          <ForgotPasswordForm />
        </Suspense>
      </div>
    </AuthShell>
  )
}
