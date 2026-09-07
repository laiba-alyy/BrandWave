/*
 * Auth pages ka bahri dhancha.
 *
 * `.bw-auth` woh scope hai jis ke andar components/auth/auth.css apna cream +
 * ink + amber world set karti hai. Root layout body par `bg-white text-gray-900`
 * (Tailwind) lagata hai — is liye wrapper khud background aur color deta hai,
 * warna cream ground white par kat jata.
 *
 * Do shakals:
 *   <AuthShell>            → do-column: form (cream) + AuthPanel (ink)
 *   <AuthShell solo>       → ek centered card (verify / sent / done screens)
 */
import '@/components/auth/auth.css'
import { authFontVars } from '@/components/auth/fonts'

export default function AuthShell({
  children,
  solo = false,
  wide = false,
}: {
  children: React.ReactNode
  solo?: boolean
  wide?: boolean
}) {
  return (
    <main className={`bw-auth ${authFontVars}`}>
      <div className={solo ? 'au au--solo' : `au${wide ? ' au--wide' : ''}`}>{children}</div>
    </main>
  )
}

/** Left column — form side. */
export function AuthForm({ children }: { children: React.ReactNode }) {
  return (
    <section className="au__form">
      <div className="au__form-in">{children}</div>
    </section>
  )
}
