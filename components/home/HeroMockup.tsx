/*
 * Hero ka product mockup — BrandWave ka apna dashboard, CSS/SVG se bana.
 *
 * Pehle yahan ek stock tasveer thi jis par Shopify ka bara logo aur kuch aam
 * store screenshots thay. Do masle:
 *   1. Wo BrandWave ko nahi bechti thi — pehli nazar mein page Shopify ka
 *      lagta tha, hamara nahi.
 *   2. Kisi doosre brand ka trademark hero mein sab se bara element tha.
 *
 * Ab yahan asal product ki shakl hai: wahi modules, wahi amber accent,
 * wahi ink surface jo dashboard mein hai. Tasveer nahi — markup hai, is liye
 * ye har screen par tez (koi 1.15 MB PNG nahi), theme ke saath khud badalta
 * hai, aur zoom par dhundla nahi hota.
 */
/* Paanch module JAAN BOOJH KAR, nau nahi: sidebar ki lambai main column se
   mail khani chahiye, warna window ka neeche wala hissa khali ya kata hua
   lagta hai. Ye asal fehrist ka hissa hai, poori fehrist nahi. */
const MODULES = [
  { label: 'Scraping', done: true },
  { label: 'SEO', done: true },
  { label: 'Sentiment', done: true },
  { label: 'Image ads', done: true },
  { label: 'Video ads', done: false },
]

// Sentiment sparkline — sirf shakl ke liye, koi asal data nahi.
const SPARK = [8, 14, 11, 19, 16, 26, 22, 31, 28, 38, 35, 44]

function sparkPath(values: number[], w: number, h: number): string {
  const max = Math.max(...values)
  const step = w / (values.length - 1)
  return values
    .map((v, i) => `${i === 0 ? 'M' : 'L'} ${(i * step).toFixed(1)} ${(h - (v / max) * h).toFixed(1)}`)
    .join(' ')
}

export default function HeroMockup() {
  const path = sparkPath(SPARK, 190, 46)

  return (
    <div className="heromock" aria-hidden="true">
      <div className="heromock__win">
        {/* app chrome */}
        <div className="heromock__bar">
          <span className="heromock__dot" />
          <span className="heromock__dot" />
          <span className="heromock__dot" />
          <span className="heromock__url">brandwave · asimjofa.com</span>
        </div>

        <div className="heromock__body">
          {/* sidebar */}
          <aside className="heromock__side">
            {MODULES.map((m) => (
              <span key={m.label} className={`heromock__nav${m.done ? ' is-done' : ''}`}>
                <i />
                {m.label}
              </span>
            ))}
          </aside>

          {/* main */}
          <div className="heromock__main">
            <div className="heromock__tiles">
              <div className="heromock__tile">
                <span className="heromock__tlabel">Products read</span>
                <strong className="heromock__tval">7,173</strong>
              </div>
              <div className="heromock__tile">
                <span className="heromock__tlabel">SEO score</span>
                <strong className="heromock__tval">
                  82<em>↗</em>
                </strong>
              </div>
              <div className="heromock__tile">
                <span className="heromock__tlabel">Ads made</span>
                <strong className="heromock__tval">14</strong>
              </div>
            </div>

            <div className="heromock__chart">
              <div className="heromock__chead">
                <span>Positive sentiment</span>
                <span className="heromock__cpct">+38%</span>
              </div>
              <svg viewBox="0 0 190 46" preserveAspectRatio="none" className="heromock__svg">
                <defs>
                  <linearGradient id="bwSpark" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="rgba(240,166,60,0.34)" />
                    <stop offset="100%" stopColor="rgba(240,166,60,0)" />
                  </linearGradient>
                </defs>
                <path d={`${path} L 190 46 L 0 46 Z`} fill="url(#bwSpark)" />
                <path d={path} fill="none" stroke="#f0a63c" strokeWidth="2"
                  strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>

            <div className="heromock__row">
              <span className="heromock__spin" />
              Generating video ad · segment 2 of 2
            </div>
          </div>
        </div>
      </div>

      {/* Floating card — gehrai ke liye, aur ye batane ke liye ke natija
          asal mein nikalta kya hai. */}
      <div className="heromock__float">
        <span className="heromock__fcheck">✓</span>
        <span>
          <strong>Video ad ready</strong>
          <em>10s · no watermark</em>
        </span>
      </div>
    </div>
  )
}
