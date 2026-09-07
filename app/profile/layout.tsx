'use client'

import DashboardShell from '@/components/dashboard/DashboardShell'

/**
 * Settings sidebar ka hissa hai (/profile), lekin /business ke bahar — is liye
 * shell yahan alag se mount hoti hai.
 *
 * Ahem: ye WAHI <Sidebar /> instance nahi hai jo /business par chal raha hota
 * hai. /business/seo se Settings par jane par sidebar ek dafa remount hoga,
 * kyunke dono alag layout subtrees hain. /business ke andar ki tamaam
 * navigations (dashboard, SEO, sentiment, chatbot, ads, video) ek hi shell
 * share karti hain aur bilkul remount nahi hoti.
 */
export default function ProfileLayout({ children }: { children: React.ReactNode }) {
  return <DashboardShell>{children}</DashboardShell>
}
