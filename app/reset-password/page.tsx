import AuthShell from '@/components/auth/AuthShell'
import ResetPasswordForm from '@/components/auth/ResetPasswordForm'

export const metadata = {
  title: 'Set a new password — BrandWave',
  description: 'Choose a new password for your BrandWave account.',
}

export default function ResetPasswordPage() {
  return (
    <AuthShell solo>
      <div className="au__card">
        <ResetPasswordForm />
      </div>
    </AuthShell>
  )
}
