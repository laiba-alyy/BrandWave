/**
 * Har dashboard route ka instant placeholder.
 *
 * Ye `loading.tsx` files ke zariye Next ke Suspense boundary mein lagta hai.
 * Iske baghair sidebar par click karne ke baad kuch der KUCH nahi hota — purana
 * page khara rehta hai jab tak naye page ka chunk load ho kar mount na ho jaye,
 * aur user ko lagta hai ke click lagi hi nahi. Ab ek top bar + card skeleton
 * foran aa jata hai, to navigation mehsoos hoti hai.
 *
 * Sidebar isme NAHI hai — wo layout mein hai aur navigation ke dauran waise hi
 * khara rehta hai. Sirf content column badalta hai.
 */
export default function RouteSkeleton() {
  return (
    <div className="animate-pulse">
      {/* top bar */}
      <div className="flex h-14 items-center justify-between border-b border-[#e7e4dc] px-8">
        <div className="space-y-2">
          <div className="h-3.5 w-44 rounded bg-[#d5d1c6]" />
          <div className="h-2.5 w-64 rounded bg-[#e7e4dc]" />
        </div>
        <div className="h-8 w-36 rounded-lg bg-[#e7e4dc]" />
      </div>

      <div className="space-y-6 p-8">
        <div className="h-28 rounded-2xl bg-[#e7e4dc]" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-24 rounded-2xl bg-[#e7e4dc]" />
          ))}
        </div>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="h-56 rounded-2xl bg-[#e7e4dc]" />
          <div className="h-56 rounded-2xl bg-[#e7e4dc]" />
        </div>
      </div>
    </div>
  )
}
