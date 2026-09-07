import { bandFeatures, type BandFeature } from './landingContent'

const featureIcons = {
  link: <path d="M9.5 6.5 11 5a2.8 2.8 0 0 1 4 4l-2.2 2.2a2.8 2.8 0 0 1-4 0M6.5 9.5 5 11a2.8 2.8 0 0 1-4-4l2.2-2.2a2.8 2.8 0 0 1 4 0" />,
  search: <path d="m10.8 10.8 3.7 3.7M6.8 11.5a4.7 4.7 0 1 0 0-9.4 4.7 4.7 0 0 0 0 9.4Z" />,
  pulse: <path d="M1.5 8h3l1.7-4 3.2 8 1.8-4h3.3M14.5 8H16" />,
  chat: <path d="M14.5 10.5a2 2 0 0 1-2 2H7l-3.5 2v-2.1a2 2 0 0 1-1.5-1.9v-5a2 2 0 0 1 2-2h8.5a2 2 0 0 1 2 2v5Z" />,
  spark: <path d="m8 1.5.9 4.6L13.5 8l-4.6.9L8 13.5l-.9-4.6L2.5 8l4.6-.9L8 1.5ZM14 1.5v3M15.5 3h-3" />,
  play: <path d="M2.5 3.5h11v9h-11zM6.6 6.4l3.4 1.9-3.4 1.9V6.4Z" />,
}

/**
 * Ek feature card: icon + index, phir title, description aur accent rule.
 *
 * Pehle har card me hover-to-play video clip thi. Chhe clips mil kar ~24 MB
 * thin, aur us size par un me kuch samajh nahi aata tha -- hover par 1.3x zoom
 * ho kar card se bahar nikalti thin, jis se grid hilti hui lagti thi. Ab card
 * khud maloomat deta hai aur landing page par koi video download hoti hi nahi.
 *
 * Poora component ab STATIC hai -- na ref, na event handler -- is liye ye
 * server component hai aur client bundle me ek byte bhi nahi jata. Hover ka
 * poora asar CSS se aata hai (dekho landing.css ka FEATURES block).
 */
function FeatureCard({ feature, index }: { feature: BandFeature; index: number }) {
  return (
    <article className="band__cell">
      <div className="band__head">
        <span className="band__icon" aria-hidden="true">
          <svg
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            {featureIcons[feature.icon as keyof typeof featureIcons]}
          </svg>
        </span>
        {/* Sirf basri tarteeb -- screen reader ke liye is ka koi matlab nahi. */}
        <span className="band__n" aria-hidden="true">
          {String(index + 1).padStart(2, '0')}
        </span>
      </div>

      <h3 className="band__k">{feature.title}</h3>
      <p className="band__v">{feature.description}</p>
      <span className="band__rule" aria-hidden="true" />
    </article>
  )
}

export default function Band() {
  return (
    <section className="band" id="features" aria-label="BrandWave features">
      <div className="band__in">
        {/* Clips ke hote hue section khud apni wazahat kar deta tha. Ab jab
            cards sirf text hain, ek header chahiye — warna grid bina kisi
            tamheed ke shuru ho jati hai. */}
        <div className="sec__head band__intro">
          <div className="eyebrow eyebrow--amber">Features</div>
          <h2>Every part of your marketing, in one place.</h2>
          <p>
            Nine modules that share one brand profile — so what the scraper learns
            about your store shows up everywhere else, without you entering it twice.
          </p>
        </div>

        <div className="band__grid">
          {bandFeatures.map((feature, i) => (
            <FeatureCard feature={feature} index={i} key={feature.title} />
          ))}
        </div>
      </div>
    </section>
  )
}
