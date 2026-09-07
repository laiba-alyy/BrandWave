/*
 * Auth pages ka type stack — landing (app/page.tsx) se bilkul same, taake
 * landing se login par aate hi type badla hua na lage.
 *
 * next/font module scope par hi chal sakta hai, aur ye file sirf auth routes
 * import karti hain — dashboard abhi bhi Geist par hai (app/layout.tsx), is
 * liye baqi app ye teen fonts download nahi karti.
 */
import { Fraunces, Instrument_Sans, JetBrains_Mono } from 'next/font/google'

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

export const authFontVars = `${fraunces.variable} ${instrumentSans.variable} ${jetbrainsMono.variable}`
