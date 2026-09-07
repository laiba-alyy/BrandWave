'use client'

import AiRetryBanner from '@/components/shared/AiRetryBanner'
import DashboardShell from '@/components/dashboard/DashboardShell'

/**
 * Saare /business modules ka layout.
 *
 * Ek account ke multiple stores ho sakte hain. Pehle har module apna brand
 * khud "most recent profile" utha kar decide karta tha, jis se doosre brand
 * ka SEO/ads data chup-chaap dikh jata tha. Ab brand ek hi jagah tay hota
 * hai aur har module usi par scope karta hai.
 *
 * <ActiveBrandProvider> pehle YAHAN tha, lekin ab app/layout.tsx (root) mein
 * hai — kyunke AI Assistant widget bhi root par render hota hai aur usay bhi
 * active brand chahiye. Yahan dobara mount karna provider ko nest kar dega:
 * do alag brand states ban jayengi, widget outer wali padhega aur ye pages
 * inner wali — yani assistant phir se "koi brand select nahi hai" kehne lag
 * jayega. Is liye ye provider ko wapas yahan mat laana.
 *
 * <DashboardShell> (sidebar + auth guard) bhi yahan hai, page ke andar nahi.
 * Layout navigations ke darmiyan zinda rehta hai, page nahi — is liye sidebar
 * ab har click par remount nahi hota. Tafseel DashboardShell ke doc-comment
 * mein hai; kisi page mein `<Sidebar />` dobara mat lagana.
 */
export default function BusinessLayout({ children }: { children: React.ReactNode }) {
  return (
    <DashboardShell>
      {/* Groq rate limit par backend chup chaap wait karta hai - banner batata
          hai ke spinner atka nahi, retry chal rahi hai. */}
      <AiRetryBanner />
      {children}
    </DashboardShell>
  )
}
