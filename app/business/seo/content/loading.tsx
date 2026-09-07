import DashRouteSkeleton from '@/components/dashboard/DashRouteSkeleton'

// Next is file ko route ke Suspense fallback ki tarah istemal karta hai —
// sidebar par click karte hi ye render ho jati hai, page ke tayyar hone ka
// intezaar kiye baghair. SEO pages dash.css par hain, is liye skeleton bhi
// usi palette ka (warna safed flash dikhta tha).
export default function Loading() {
  return <DashRouteSkeleton />
}
