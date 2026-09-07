import type { ReactNode } from 'react'
import Link from 'next/link'
import { Fraunces, Instrument_Sans, JetBrains_Mono } from 'next/font/google'

import '@/components/home/landing.css'
import './legal.css'

/*
 * Privacy aur Terms dono is shell me render hote hain.
 *
 * `bw-landing` class ZAROORI hai — saare design tokens (--amber, --f-display,
 * --text-dim waghera) usi par define hain (landing.css). Uske baghair page
 * bina rang ke render hoga.
 *
 * Fonts yahin load hote hain, app/layout.tsx me nahi — bilkul usi tarah jaise
 * app/page.tsx karta hai, taake dashboard ke pages ye fonts download na karen.
 */
const fraunces = Fraunces({
  variable: '--font-fraunces',
  subsets: ['latin'],
  style: ['normal', 'italic'],
  axes: ['opsz'],
  display: 'swap',
})
const instrumentSans = Instrument_Sans({
  variable: '--font-instrument-sans',
  subsets: ['latin'],
  display: 'swap',
})
const jetbrainsMono = JetBrains_Mono({
  variable: '--font-jetbrains-mono',
  subsets: ['latin'],
  display: 'swap',
})

export default function LegalPage({
  title,
  updated,
  lede,
  children,
}: {
  title: string
  updated: string
  lede: string
  children: ReactNode
}) {
  return (
    <main
      className={`bw-landing ${fraunces.variable} ${instrumentSans.variable} ${jetbrainsMono.variable}`}
    >
      <div className="legal">
        <div className="legal__in">
          <header className="legal__head">
            <Link className="legal__back" href="/">
              ← Back to BrandWave
            </Link>
            <h1 className="legal__title">{title}</h1>
            <p className="legal__meta">Last updated: {updated}</p>
            <p className="legal__lede">{lede}</p>
          </header>

          {children}

          <div className="legal__foot">
            <Link href="/">Home</Link>
            <Link href="/privacy">Privacy Policy</Link>
            <Link href="/terms">Terms of Service</Link>
          </div>
        </div>
      </div>
    </main>
  )
}
