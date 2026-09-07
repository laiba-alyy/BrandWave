import { brandFontVars } from '@/components/shared/brandFonts'
import '@/components/dashboard/dash.css'

/**
 * RouteSkeleton ka dash.css wala bhai.
 *
 * RouteSkeleton safed Tailwind par hai (bg-white + gray-100). Migrated pages ka
 * ground warm paper hai (#f7f6f2), is liye un par purana skeleton ek nazar aane
 * wala FLASH deta tha: safed placeholder, phir warm page. Chhoti si baat hai,
 * magar har navigation par dikhti hai aur sasti lagti hai.
 *
 * Ye wohi shakl hai, wohi tokens par. Jo pages abhi purane Tailwind par hain wo
 * RouteSkeleton hi use karte rahenge — un ke liye safed hi theek hai.
 */
export default function DashRouteSkeleton() {
  return (
    <div className={`bw-dash ${brandFontVars}`}>
      <div className="dsh">
        <div className="dsh__top">
          <div style={{ display: 'grid', gap: 9 }}>
            <div className="dsh__skel" style={{ height: 19, width: 210 }} />
            <div className="dsh__skel" style={{ height: 12, width: 290 }} />
          </div>
          <div className="dsh__topactions">
            <div className="dsh__skel" style={{ height: 34, width: 132, borderRadius: 8 }} />
            <div className="dsh__skel" style={{ height: 34, width: 108, borderRadius: 8 }} />
          </div>
        </div>

        <div className="dsh__body">
          <div className="dsh__skel" style={{ height: 168, borderRadius: 14 }} />
          <div className="dsh__grid dsh__grid--3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="dsh__skel" style={{ height: 104, borderRadius: 12 }} />
            ))}
          </div>
          <div className="dsh__grid dsh__grid--2">
            <div className="dsh__skel" style={{ height: 232, borderRadius: 12 }} />
            <div className="dsh__skel" style={{ height: 232, borderRadius: 12 }} />
          </div>
        </div>
      </div>
    </div>
  )
}
