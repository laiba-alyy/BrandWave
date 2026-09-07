'use client'

import { useRef, useState } from 'react'
import {
  modules,
  sampleAssistant,
  sampleChatbot,
  sampleDashboard,
  sampleImageAds,
  sampleInsights,
  sampleSentiment,
  sampleSeo,
  sampleSetup,
  sampleVideoAds,
} from './landingContent'

/**
 * "Nine modules, one picture of your brand" — rail + screen.
 *
 * Tabs ARIA tab pattern follow karte hain: arrow keys se move, aur panel
 * `hidden` se toggle hota hai (display:none) taake hidden panels ka content
 * screen readers aur tab order dono se bahar rahe.
 */
export default function ModuleExplorer() {
  const [active, setActive] = useState(0)
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([])

  const onKeyDown = (e: React.KeyboardEvent, i: number) => {
    const d =
      e.key === 'ArrowDown' || e.key === 'ArrowRight'
        ? 1
        : e.key === 'ArrowUp' || e.key === 'ArrowLeft'
          ? -1
          : 0
    if (!d) return
    e.preventDefault()
    const n = (i + d + modules.length) % modules.length
    setActive(n)
    tabRefs.current[n]?.focus()
  }

  return (
    <section className="sec" id="modules">
      <div className="shell">
        <div className="sec__head">
          <div className="eyebrow">The workspace</div>
          <h2>Nine modules. One picture of your brand.</h2>
          <p>
            Pick a module to see the actual screen. Everything below runs on your own
            catalogue and your own reviews — nothing generic, nothing borrowed from a
            competitor&rsquo;s data.
          </p>
        </div>

        <div className="explorer">
          <div className="rail" role="tablist" aria-label="BrandWave modules">
            {modules.map((m, i) => (
              <button
                key={m.crumb}
                ref={(el) => {
                  tabRefs.current[i] = el
                }}
                className="rail__item"
                role="tab"
                id={`tab-${m.crumb}`}
                aria-controls={`p-${m.crumb}`}
                aria-selected={active === i}
                tabIndex={active === i ? 0 : -1}
                onClick={() => setActive(i)}
                onKeyDown={(e) => onKeyDown(e, i)}
              >
                <span className="rail__n">{m.n}</span>
                <span>
                  <span className="rail__t">{m.title}</span>
                  <span className="rail__d">{m.desc}</span>
                </span>
              </button>
            ))}
          </div>

          <div className="screen">
            <div className="screen__bar">
              <div className="screen__dots">
                <i />
                <i />
                <i />
              </div>
              <div className="screen__path">
                app.brandwave.io / your-store / <b>{modules[active].crumb}</b>
              </div>
            </div>

            <div className="screen__body">
              {modules.map((m, i) => (
                <section
                  key={m.crumb}
                  className="panel"
                  role="tabpanel"
                  id={`p-${m.crumb}`}
                  aria-labelledby={`tab-${m.crumb}`}
                  hidden={active !== i}
                >
                  <PanelBody index={i} />
                </section>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

/** Jab tak asli data wire nahi hota, panel ka data area ye dikhata hai. */
function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="empty">
      <b>Awaiting your data</b>
      {children}
    </div>
  )
}

function PanelBody({ index }: { index: number }) {
  switch (index) {
    case 0:
      return <SetupPanel />
    case 1:
      return <SentimentPanel />
    case 2:
      return <SeoPanel />
    case 3:
      return <InsightsPanel />
    case 4:
      return <ImageAdsPanel />
    case 5:
      return <VideoAdsPanel />
    case 6:
      return <ChatbotPanel />
    case 7:
      return <AssistantPanel />
    default:
      return <DashboardPanel />
  }
}

/* ── 01 ─────────────────────────────────────────────────────────────────── */
function SetupPanel() {
  return (
    <>
      <div className="panel__h">
        <h3>Brand Setup</h3>
        <span className="chip chip--mute">{sampleSetup.chip}</span>
      </div>
      <p className="panel__lead">
        Paste your store URL. BrandWave paginates until the catalogue runs out — no page
        cap — then reads your currency and domain to work out which market you sell into.
      </p>
      <div className="panel__grid g3">
        <div className="card">
          <div className="card__k">Catalogue</div>
          <div className="card__v">{sampleSetup.catalogue}</div>
        </div>
        <div className="card">
          <div className="card__k">Market</div>
          <div className="card__v">{sampleSetup.market}</div>
        </div>
        <div className="card">
          <div className="card__k">Brand voice</div>
          <div className="card__v">{sampleSetup.voice}</div>
        </div>
      </div>
      <div className="panel__grid">
        <div className="card">
          <div className="card__k">Price bands detected</div>
          {sampleSetup.priceBands.length ? (
            <div className="tags">
              {sampleSetup.priceBands.map((b) => (
                <span className="tag" key={b.label}>
                  {b.label} <b>{b.value}</b>
                </span>
              ))}
            </div>
          ) : (
            <div className="card__v muted">
              Price bands appear here once your catalogue is scraped.
            </div>
          )}
        </div>
      </div>
    </>
  )
}

/* ── 02 ─────────────────────────────────────────────────────────────────── */
function SentimentPanel() {
  const s = sampleSentiment
  return (
    <>
      <div className="panel__h">
        <h3>Sentiment Analysis</h3>
        <span className="chip chip--mute">{s.chip}</span>
      </div>
      <p className="panel__lead">
        A fine-tuned multilingual model scores every review; a second pass pulls out the
        pain points and the things customers keep asking for.
      </p>
      <div className="panel__grid g2">
        <div className="card">
          <div className="card__k">Overall sentiment</div>
          <div className="senti__head" style={{ marginTop: 10 }}>
            <span className="senti__pct">{s.headlinePct}</span>
            <span className="senti__lbl">{s.headlineNote}</span>
          </div>
          <div className="bar">
            <i className="bar__pos" style={{ width: `${s.positivePct}%` }} />
            <i className="bar__neu" style={{ width: `${s.neutralPct}%` }} />
            <i className="bar__neg" style={{ width: `${s.negativePct}%` }} />
          </div>
          <div className="senti__legend">
            {s.legend.map((l) => (
              <span key={l.l}>
                <b>{l.n}</b> {l.l}
              </span>
            ))}
          </div>
          {s.emotions.length > 0 && (
            <div className="tags">
              {s.emotions.map((e) => (
                <span className="tag" key={e.label}>
                  {e.label} <b>{e.value}</b>
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="card">
          <div className="card__k">What hurts</div>
          {s.painPoints.length ? (
            <ul className="list" style={{ marginTop: 8 }}>
              {s.painPoints.map((p) => (
                <li key={p.text}>
                  <span className="num">{p.num}</span>
                  <span>{p.text}</span>
                  <span className="who">{p.who}</span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="card__v muted">
              Ranked pain points appear here once your reviews are read.
            </div>
          )}
        </div>
      </div>

      <div className="panel__grid">
        <div className="card">
          <div className="card__k">What they love</div>
          {s.loved.length ? (
            <div className="tags">
              {s.loved.map((l) => (
                <span className="tag" key={l.label}>
                  {l.label} <b>{l.value}</b>
                </span>
              ))}
            </div>
          ) : (
            <div className="card__v muted">
              The phrases customers repeat in positive reviews land here.
            </div>
          )}
        </div>
      </div>
    </>
  )
}

/* ── 03 ─────────────────────────────────────────────────────────────────── */
function SeoPanel() {
  const s = sampleSeo
  return (
    <>
      <div className="panel__h">
        <h3>SEO Intelligence</h3>
        <span className="chip chip--amber">{s.chip}</span>
      </div>
      <p className="panel__lead">
        Keywords are generated against your catalogue, then validated against live
        autocomplete — so you only optimise for things people actually type.
      </p>

      {s.keywords.length ? (
        <div className="scroll-x" style={{ marginTop: 18 }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>Keyword</th>
                <th>Intent</th>
                <th>Difficulty</th>
                <th className="n">Monthly</th>
              </tr>
            </thead>
            <tbody>
              {s.keywords.map((k) => (
                <tr key={k.kw}>
                  <td>{k.kw}</td>
                  <td>{k.intent}</td>
                  <td>
                    <span className="meter">
                      <i style={{ width: `${k.difficulty}%` }} />
                    </span>
                  </td>
                  <td className="n">{k.volume}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ marginTop: 18 }}>
          <Empty>
            Your keyword table — intent, difficulty and monthly volume — builds itself from
            your catalogue on the first audit.
          </Empty>
        </div>
      )}

      {s.rewrite ? (
        <div className="diff" style={{ marginTop: 20 }}>
          <div className="diff__row is-old">
            <span className="diff__lbl">{s.rewrite.oldLabel}</span>
            {s.rewrite.oldTitle}
          </div>
          <div className="diff__row is-new">
            <span className="diff__lbl">{s.rewrite.newLabel}</span>
            {s.rewrite.newTitle}
          </div>
        </div>
      ) : (
        <div className="diff" style={{ marginTop: 20 }}>
          <div className="diff__row">
            <span className="diff__lbl">Before / after</span>
            Every rewritten title is shown against the original, with the character count
            and the keyword it now covers.
          </div>
        </div>
      )}
    </>
  )
}

/* ── 04 ─────────────────────────────────────────────────────────────────── */
function InsightsPanel() {
  const s = sampleInsights
  return (
    <>
      <div className="panel__h">
        <h3>Brand Insights</h3>
        <span className="chip chip--mute">{s.chip}</span>
      </div>
      <p className="panel__lead">
        No vague advice. Each finding names the evidence behind it, so you can check the
        claim before you act on it.
      </p>

      <div className="panel__grid g2">
        <div className="card" style={{ borderColor: 'rgba(240,114,138,.26)' }}>
          <div className="card__k" style={{ color: 'var(--rose)' }}>
            Fix first
          </div>
          {s.fixFirst ? (
            <>
              <div className="card__v">{s.fixFirst.body}</div>
              <div className="tags">
                {s.fixFirst.tags.map((t) => (
                  <span className="tag" key={t}>
                    {t}
                  </span>
                ))}
              </div>
            </>
          ) : (
            <div className="card__v muted">
              The problem costing you the most money, with the reviews that prove it.
            </div>
          )}
        </div>

        <div className="card" style={{ borderColor: 'rgba(62,217,164,.26)' }}>
          <div className="card__k" style={{ color: 'var(--jade)' }}>
            Opening
          </div>
          {s.opening ? (
            <>
              <div className="card__v">{s.opening.body}</div>
              <div className="tags">
                {s.opening.tags.map((t) => (
                  <span className="tag" key={t}>
                    {t}
                  </span>
                ))}
              </div>
            </>
          ) : (
            <div className="card__v muted">
              The demand you are already earning but not capturing on your product pages.
            </div>
          )}
        </div>
      </div>

      <div className="panel__grid">
        <div className="card">
          <div className="card__k">Also flagged</div>
          {s.alsoFlagged.length ? (
            <ul className="list" style={{ marginTop: 6 }}>
              {s.alsoFlagged.map((f) => (
                <li key={f.text}>
                  <span className="num">{f.num}</span>
                  <span>{f.text}</span>
                  <span className="who">{f.who}</span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="card__v muted">
              Lower-priority findings queue up here, each with its own evidence.
            </div>
          )}
        </div>
      </div>
    </>
  )
}

/* ── 05 ─────────────────────────────────────────────────────────────────── */
function ImageAdsPanel() {
  const s = sampleImageAds
  return (
    <>
      <div className="panel__h">
        <h3>Image Ads</h3>
        <span className="chip chip--amber">Product preserved, scene generated</span>
      </div>
      <p className="panel__lead">
        Your actual product stays pixel-true. BrandWave builds the set around it and sets
        the copy in your brand&rsquo;s type.
      </p>
      <div className="panel__grid g3">
        <div>
          <div className="adshot adshot--src">
            <div className="adshot__prod" />
            <div className="adshot__sub" style={{ color: 'var(--text-mute)' }}>
              Source · catalogue photo
            </div>
          </div>
        </div>
        <div>
          <div className="adshot">
            <div className="adshot__prod" />
            <div className="adshot__txt">
              {s.headline[0]}
              <br />
              {s.headline[1]}
            </div>
            <div className="adshot__sub">{s.sub}</div>
          </div>
        </div>
        <div className="card">
          <div className="card__k">Generation brief</div>
          <div className="card__v">{s.brief}</div>
          <div className="tags">
            {s.formats.map((f) => (
              <span className="tag" key={f}>
                {f}
              </span>
            ))}
            <span className="tag">
              Headline from <b>review language</b>
            </span>
          </div>
        </div>
      </div>
    </>
  )
}

/* ── 06 ─────────────────────────────────────────────────────────────────── */
function VideoAdsPanel() {
  const s = sampleVideoAds
  return (
    <>
      <div className="panel__h">
        <h3>Video Ads</h3>
        <span className="chip chip--mute">{s.chip}</span>
      </div>
      <p className="panel__lead">
        One product photo in, a short ad out — camera move, scene and pacing decided per
        product, not stamped from a preset.
      </p>
      <div className="frames" style={{ marginTop: 18 }}>
        {s.frames.map((f) => (
          <div className="frame" key={f.t}>
            <i style={{ inset: f.inset }} />
            <span>{f.t}</span>
          </div>
        ))}
      </div>
      <div className="timeline">
        <span className="timeline__t">00:03</span>
        <span className="timeline__track">
          <i />
        </span>
        <span className="timeline__t">00:08</span>
      </div>
      <div className="panel__grid g3">
        {s.notes.map((n) => (
          <div className="card" key={n.k}>
            <div className="card__k">{n.k}</div>
            <div className="card__v">{n.v}</div>
          </div>
        ))}
      </div>
    </>
  )
}

/* ── 07 ─────────────────────────────────────────────────────────────────── */
function ChatbotPanel() {
  const s = sampleChatbot
  return (
    <>
      <div className="panel__h">
        <h3>Support Chatbot</h3>
        <span className="chip chip--mute">{s.chip}</span>
      </div>
      <p className="panel__lead">
        Grounded in your own catalogue, policies and order rules — so it answers from your
        store, and hands over the moment it shouldn&rsquo;t guess.
      </p>
      <div className="panel__grid g2">
        <div className="card">
          {s.thread.length ? (
            <div className="chat">
              {s.thread.map((m, i) => (
                <div className={`msg msg--${m.from}`} key={i}>
                  {m.text}
                </div>
              ))}
            </div>
          ) : (
            <Empty>
              A real transcript from your own store appears here once the bot is live.
            </Empty>
          )}
        </div>
        <div className="card">
          <div className="card__k">Why it doesn&rsquo;t invent answers</div>
          <div className="card__v">{s.why}</div>
          <div className="tags">
            {s.tags.map((t) => (
              <span className="tag" key={t}>
                {t}
              </span>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}

/* ── 08 ─────────────────────────────────────────────────────────────────── */
function AssistantPanel() {
  const s = sampleAssistant
  return (
    <>
      <div className="panel__h">
        <h3>AI Assistant</h3>
        <span className="chip chip--amber">Floating · knows this brand</span>
      </div>
      <p className="panel__lead">
        The in-app helper reads the same data you&rsquo;re looking at, so you can ask about
        your own numbers instead of hunting for the right screen.
      </p>
      <div className="panel__grid g2">
        <div className="card">
          {s.thread.length ? (
            <div className="chat">
              {s.thread.map((m, i) => (
                <div className={`msg msg--${m.from}`} key={i}>
                  {m.text}
                </div>
              ))}
            </div>
          ) : (
            <Empty>
              Ask about your own catalogue and the assistant answers from your live
              numbers.
            </Empty>
          )}
        </div>
        <div className="card">
          <div className="card__k">It can also do</div>
          <ul className="list" style={{ marginTop: 6 }}>
            {s.canAlsoDo.map((item) => (
              <li key={item}>
                <span className="num">→</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </>
  )
}

/* ── 09 ─────────────────────────────────────────────────────────────────── */
function DashboardPanel() {
  const tiles = sampleDashboard.tiles
  return (
    <>
      <div className="panel__h">
        <h3>Dashboard</h3>
        <span className="chip chip--mute">Every module, one screen</span>
      </div>
      <p className="panel__lead">
        The first screen after login: every module reduced to the one number that changed,
        plus what needs you today.
      </p>

      {tiles.length ? (
        <div className="tiles" style={{ marginTop: 18 }}>
          {tiles.map((t) => (
            <div className="tile" key={t.k}>
              <div className="tile__k">{t.k}</div>
              <div className="tile__v">{t.v}</div>
              <div className={`tile__d ${t.tone}`}>{t.d}</div>
              {t.spark && (
                <svg
                  className="spark"
                  viewBox="0 0 120 26"
                  preserveAspectRatio="none"
                  aria-hidden="true"
                >
                  <path d={t.spark.d} fill="none" stroke={t.spark.color} strokeWidth="1.8" />
                  <path d={`${t.spark.d} L120 26 L0 26 Z`} fill={t.spark.fill} />
                  <circle cx="120" cy={t.spark.cy} r="2.4" fill={t.spark.color} />
                </svg>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div style={{ marginTop: 18 }}>
          <Empty>
            Sentiment, SEO score, complaint rate, products indexed, ads generated and chats
            handled — each with its own trend line.
          </Empty>
        </div>
      )}
    </>
  )
}
