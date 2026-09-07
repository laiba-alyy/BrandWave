import { brandFontVars } from '@/components/shared/brandFonts'
import '@/components/dashboard/dash.css'

/**
 * Is module ke saare safhe dash.css ke scope mein.
 *
 * Ye pages `<>...</>` (fragment) return karte hain — un mein apna `<main>`
 * hai hi nahi — is liye har page mein wrapper daalne ke bajaye segment layout
 * mein ek dafa lagana zyada saaf hai. Layout navigations ke darmiyan zinda
 * rehta hai, to font/CSS dobara apply bhi nahi hoti.
 */
export default function ModuleLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className={`bw-dash ${brandFontVars}`}>
      <div className="dsh">{children}</div>
    </main>
  )
}
