/*
 * BrandWave ka type stack — ek hi jagah.
 *
 * Landing (app/page.tsx), auth pages aur ab redesigned dashboard pages sab
 * yehi teen fonts use karte hain. next/font sirf module scope par chal sakta
 * hai, is liye pehle ye har jagah alag alag define ho raha tha; ek jagah rakhne
 * se same instance share hota hai aur variable names kabhi diverge nahi karte.
 *
 * NOTE: ye file sirf woh routes import karte hain jo naye design par hain.
 * Baqi dashboard abhi bhi Geist par hai (app/layout.tsx), aur un pages par ye
 * fonts download nahi hote.
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

export const brandFontVars = `${fraunces.variable} ${instrumentSans.variable} ${jetbrainsMono.variable}`
