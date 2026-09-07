'use client'

/*
 * Auth pages ka daayan ink panel — cream form ke saamne wala counterweight.
 *
 * Landing ka WaveCanvas yahan dobara use hota hai (ab class prop leta hai)
 * taake login/signup par wohi lehrein chalein jo hero par chalti hain. Panel
 * `<= 1020px` par auth.css se hide ho jata hai, is liye mobile par canvas ka
 * rAF loop bhi mount nahi hota.
 */
import WaveCanvas from '@/components/home/WaveCanvas'

export default function AuthPanel({
  eyebrow,
  title,
  accent,
  quote,
  by,
  stats,
}: {
  eyebrow: string
  title: string
  accent: string
  quote: string
  by: string
  stats: { value: string; label: string }[]
}) {
  return (
    <aside className="au__side">
      <div className="pnl">
        <WaveCanvas className="pnl__waves" />
        <div className="pnl__doodles" aria-hidden="true">
          <span className="pnl__doodle pnl__doodle--ring" />
          <span className="pnl__doodle pnl__doodle--spark" />
          <span className="pnl__doodle pnl__doodle--curve" />
          <span className="pnl__doodle pnl__doodle--dot pnl__doodle--dot-one" />
          <span className="pnl__doodle pnl__doodle--dot pnl__doodle--dot-two" />
          <span className="pnl__doodle pnl__doodle--cross pnl__doodle--cross-one" />
          <span className="pnl__doodle pnl__doodle--cross pnl__doodle--cross-two" />
          <span className="pnl__doodle pnl__doodle--arc" />
          <span className="pnl__doodle pnl__doodle--dash" />
          <span className="pnl__doodle pnl__doodle--cluster" />
          <span className="pnl__doodle pnl__doodle--diamond" />
          <span className="pnl__doodle pnl__doodle--hatch" />
          <span className="pnl__doodle pnl__doodle--lower-arc" />
        </div>

        <div>
          <p className="pnl__eyebrow">{eyebrow}</p>
          <h2>
            {title} <em>{accent}</em>
          </h2>
        </div>

        <div className="pnl__card">
          <p className="pnl__quote">&ldquo;{quote}&rdquo;</p>
          <p className="pnl__by">{by}</p>
          <div className="pnl__stats">
            {stats.map((stat) => (
              <div className="pnl__stat" key={stat.label}>
                <b>{stat.value}</b>
                <span>{stat.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </aside>
  )
}
