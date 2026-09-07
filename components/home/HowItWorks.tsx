import { steps } from './landingContent'

export default function HowItWorks() {
  return (
    <section className="sec sec--flush" id="how">
      <div className="shell">
        <div className="sec__head how__head">
          <h2>Three steps, and only the first one needs you.</h2>
        </div>

        <div className="steps">
          {steps.map((step) => (
            <div className="step" key={step.n}>
              <div className="step__n">{step.n}</div>
              <h3>{step.title}</h3>
              <p>{step.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
