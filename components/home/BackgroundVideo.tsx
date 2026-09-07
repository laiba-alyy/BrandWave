/*
 * Landing ka background layer. `background-image` video nahi chala sakta, is
 * liye ek fixed <video> layer content ke peeche baithti hai aur uske upar ek
 * scrim div text ko readable rakhta hai.
 *
 * - poster = wahi still jo pehle background tha, taake video load hone se
 *   pehle koi khali frame na dikhe.
 * - prefers-reduced-motion par video CSS se hide ho jati hai aur `.bw-landing`
 *   ki apni background image fallback ban jati hai.
 */
export default function BackgroundVideo() {
  return (
    <div className="bw-bg" aria-hidden="true">
      <video
        className="bw-bg__video"
        autoPlay
        muted
        loop
        playsInline
        preload="auto"
        poster="/images/backgroud_image.webp"
      >
        <source src="/images/animation.mp4" type="video/mp4" />
      </video>
      <div className="bw-bg__scrim" />
    </div>
  )
}
