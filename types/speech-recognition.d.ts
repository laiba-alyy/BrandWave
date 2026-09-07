/**
 * Web Speech API ke woh types jo TypeScript ki DOM lib mein nahi hain.
 *
 * `lib.dom.d.ts` mein SpeechRecognitionAlternative / SpeechRecognitionResult /
 * SpeechRecognitionResultList to maujood hain, magar khud recognition object,
 * uske events, aur `window.SpeechRecognition` nahi. Isi kami ki wajah se
 * AIAssistantWidget mein chaar jagah `any` parta tha.
 *
 * Sirf utna declare kiya gaya hai jitna wo component waqai use karta hai —
 * maqsad `any` hatana hai, poora spec dobara likhna nahi. Jo cheezein lib.dom
 * pehle se deti hai unhein yahan dobara declare NAHI kiya, warna
 * duplicate-identifier errors aate.
 */

declare global {
  interface SpeechRecognitionEvent extends Event {
    readonly resultIndex: number
    readonly results: SpeechRecognitionResultList
  }

  interface SpeechRecognitionErrorEvent extends Event {
    readonly error: string
    readonly message: string
  }

  interface SpeechRecognitionInstance extends EventTarget {
    lang: string
    continuous: boolean
    interimResults: boolean
    maxAlternatives: number
    start(): void
    stop(): void
    abort(): void
    onstart: ((this: SpeechRecognitionInstance, ev: Event) => void) | null
    onend: ((this: SpeechRecognitionInstance, ev: Event) => void) | null
    onerror:
      | ((this: SpeechRecognitionInstance, ev: SpeechRecognitionErrorEvent) => void)
      | null
    onresult:
      | ((this: SpeechRecognitionInstance, ev: SpeechRecognitionEvent) => void)
      | null
  }

  type SpeechRecognitionConstructor = new () => SpeechRecognitionInstance

  interface Window {
    /** Standard naam — abhi sirf kuch browsers par. */
    SpeechRecognition?: SpeechRecognitionConstructor
    /** Chrome/Edge ka prefixed naam — amalan yehi chalta hai. */
    webkitSpeechRecognition?: SpeechRecognitionConstructor
  }
}

export {}
