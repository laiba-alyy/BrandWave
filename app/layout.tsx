import type { Metadata } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import './globals.css'
import AIAssistantWidget from '@/components/assistant/AIAssistantWidget'   // 👈 ADD KIYA
import { ActiveBrandProvider } from '@/lib/useActiveBrand'

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
})
const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
})

export const metadata: Metadata = {
  title: 'BrandWave — AI Marketing Platform',
  description: 'AI-powered marketing automation for Shopify businesses worldwide.',
  keywords: 'AI marketing, Shopify, ecommerce, SEO, brand intelligence, automation',
  authors: [{ name: 'BrandWave' }],
  openGraph: {
    title: 'BrandWave — AI Marketing Platform',
    description: 'AI-powered marketing automation for Shopify businesses worldwide.',
    type: 'website',
  },
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-white text-gray-900">
        {/*
          ActiveBrandProvider yahan (root par) hai, sirf /business layout mein
          nahi — kyunke AIAssistantWidget bhi root par render hota hai.

          Pehle provider sirf app/business/layout.tsx mein tha, yani widget us
          ke BAHAR tha. useActiveBrand() provider ke bahar safe defaults deta
          hai (activeBrandId: null), to widget har message ke saath
          brand_profile_id: null bhejta tha aur backend ka build_brand_context
          None return karta tha — assistant har jawab mein kehta tha "koi brand
          select nahi hai", halanke switcher mein brand select hota tha.

          ZAROORI: provider ko yahan rakhne ke baad business layout mein DOBARA
          mount na karna — nested provider ka apna alag state hota, aur widget
          outer wala padhta jab ke pages inner wala. Yani bug wapas aa jata.
        */}
        <ActiveBrandProvider>
          {children}
          <AIAssistantWidget />   {/* 👈 ADD KIYA — har page pe render hoga */}
        </ActiveBrandProvider>
      </body>
    </html>
  )
}
