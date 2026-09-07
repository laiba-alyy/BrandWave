import RouteSkeleton from '@/components/dashboard/RouteSkeleton'

// Next is file ko route ke Suspense fallback ki tarah istemal karta hai —
// sidebar par click karte hi ye render ho jati hai, page ke tayyar hone ka
// intezaar kiye baghair.
export default function Loading() {
  return <RouteSkeleton />
}
