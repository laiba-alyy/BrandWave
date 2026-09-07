'use client'

import Link from 'next/link'
import { useState } from 'react'
import { plans, pricingNote } from './landingContent'

type Currency = 'pkr' | 'usd'

function Tick({ hero }: { hero?: boolean }) {
  return (
    <svg width="13" height="13" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path
        d="M2.5 7.4 5.4 10.3 11.5 4"
        stroke={hero ? '#F0A63C' : '#C8622B'}
        strokeWidth="1.9"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export default function Pricing() {
  const [currency, setCurrency] = useState<Currency>('pkr')

  return (
    <section className="sec bw-invert" id="pricing">
      <div className="shell">
        <div className="sec__head prices__head">
          <div style={{ maxWidth: '52ch' }}>
            <div className="eyebrow">Pricing</div>
            <h2>Priced for a brand, not an agency.</h2>
            <p>
              Monthly, cancel whenever. Every plan includes the full scrape and the
              sentiment model — the tiers change how many stores and how much generation
              you get.
            </p>
          </div>

          <div className="cur" role="group" aria-label="Currency">
            <button
              type="button"
              aria-pressed={currency === 'pkr'}
              onClick={() => setCurrency('pkr')}
            >
              PKR
            </button>
            <button
              type="button"
              aria-pressed={currency === 'usd'}
              onClick={() => setCurrency('usd')}
            >
              USD
            </button>
          </div>
        </div>

        <div className="prices">
          {plans.map((plan) => (
            <div className={`plan${plan.hero ? ' plan--hero' : ''}`} key={plan.name}>
              <div className="plan__name">
                {plan.name}
                {plan.badge && <span className="chip chip--amber">{plan.badge}</span>}
              </div>

              <div className="plan__price">
                {plan.price[currency]}
                <small> / month</small>
              </div>

              <div className="plan__for">{plan.for}</div>

              <ul>
                {plan.features.map((f) => (
                  <li key={f}>
                    <Tick hero={plan.hero} />
                    {f}
                  </li>
                ))}
              </ul>

              <div className="plan__cta">
                <Link
                  className={`btn btn--${plan.cta.variant}`}
                  href={plan.cta.href}
                >
                  {plan.cta.label}
                </Link>
              </div>
            </div>
          ))}
        </div>

        <p className="prices__note">{pricingNote}</p>
      </div>
    </section>
  )
}
