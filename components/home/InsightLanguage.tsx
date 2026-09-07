'use client'

import { useState } from 'react'
import { sampleInsight } from './landingContent'

/**
 * Wohi finding, do zubaanon mein. Toggle sirf language badalta hai — numbers
 * aur evidence chips waise ke waise rehte hain, jo is section ka poora point hai.
 */
export default function InsightLanguage() {
  const [isEn, setIsEn] = useState(true)
  const copy = isEn ? sampleInsight.en : sampleInsight.ur

  return (
    <section className="sec sec--flush" id="insights">
      <div className="shell lang">
        <div className="lang__head">
          <div className="eyebrow">Written how you think</div>
          <h2>One clear finding. In your language.</h2>
          <p>
            BrandWave turns your store data into a clear next step, written in English or
            Roman Urdu.
          </p>
        </div>

        <div className="insight">
          <div className="insight__top">
            <div className="toggle" role="group" aria-label="Insight language">
              <button type="button" aria-pressed={isEn} onClick={() => setIsEn(true)}>
                EN
              </button>
              <button type="button" aria-pressed={!isEn} onClick={() => setIsEn(false)}>
                ROMAN URDU
              </button>
            </div>
          </div>

          <div className="insight__body">
            <h3>{copy.title}</h3>
            <p>{copy.body}</p>

            {sampleInsight.evidence.length > 0 && (
              <div className="evidence">
                {sampleInsight.evidence.map((e) => (
                  <span className="tag" key={e}>
                    {e}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
