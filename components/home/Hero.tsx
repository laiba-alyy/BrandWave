import Link from 'next/link'
import WaveCanvas from './WaveCanvas'
import HeroMockup from './HeroMockup'

export default function Hero() {
  return (
    <header className="hero" id="top">
      <WaveCanvas />

      <div className="shell hero__in">
        <div className="hero__copy">
          <div className="eyebrow eyebrow--amber rise rise--1">For Shopify brand owners</div>

          <h1 className="rise rise--1">
            <span className="hero__headline-dark">Turn your brand into</span>{' '}
            <span className="hero__headline-amber">smarter growth</span>{' '}
            <span className="hero__headline-dark">with AI-powered marketing</span>
          </h1>

          <div className="hero__actions rise rise--2">
            <Link className="btn btn--primary btn--lg" href="/signup">
              Connect your store
              <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path
                  d="M3 8h10M9 4l4 4-4 4"
                  stroke="currentColor"
                  strokeWidth="1.7"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </Link>
            <a className="btn btn--ghost btn--lg" href="#features">
              Explore features
            </a>
          </div>
        </div>

        <HeroMockup />

      </div>

    </header>
  )
}
