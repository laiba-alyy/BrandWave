import { faqs } from './landingContent'

export default function Faq() {
  return (
    <section className="sec" id="faq">
      <div className="shell">
        <div className="sec__head">
          <div className="eyebrow">Before you connect</div>
          <h2>The questions we actually get.</h2>
        </div>

        <div className="faq">
          {faqs.map((item, i) => (
            <details key={item.q} open={i === 0}>
              <summary>{item.q}</summary>
              <p>{item.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  )
}
