import { Fraunces, Instrument_Sans, JetBrains_Mono } from 'next/font/google'

import '@/components/home/landing.css'

import Navbar from '@/components/home/Navbar'
import Hero from '@/components/home/Hero'
import Stats from '@/components/home/Stats'
import Band from '@/components/home/Band'
import HowItWorks from '@/components/home/HowItWorks'
import Pricing from '@/components/home/Pricing'
import Faq from '@/components/home/Faq'
import CTA from '@/components/home/CTA'
import Footer from '@/components/home/Footer'

/*
 * Landing page ka type stack sirf yahan load hota hai — dashboard abhi bhi
 * Geist par hai (app/layout.tsx). Fonts route-level par rakhne se app ke baqi
 * pages inhe download nahi karte.
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

export const metadata = {
  title: 'BrandWave — AI Marketing Automation Platform',
  description:
    'Scrape, analyze, and automate your marketing with AI-powered tools built for Shopify businesses worldwide.',
}

export default function Home() {
  return (
    <main
      className={`bw-landing ${fraunces.variable} ${instrumentSans.variable} ${jetbrainsMono.variable}`}
    >
      <Navbar />
      <Hero />
      <Stats />
      <Band />
      <HowItWorks />
      <Pricing />
      <Faq />
      <CTA />
      <Footer />
    </main>
  )
}
