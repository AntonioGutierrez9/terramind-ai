/* Language switch (English default, Spanish optional).
 *
 * The interface text lives in English in the components; when Spanish is selected, a small DOM translator swaps every
 * visible UI string (text nodes and placeholder/title attributes) using a reviewed dictionary (es.json, generated once
 * with the course model and committed — no runtime AI cost). Data (project names, numbers, user-typed text, AI chat
 * answers) is never touched. The backend receives the language in an `X-Lang` header so the AI agents answer in Spanish.
 */
import ES from './es.json'
import ES_TEMPLATES from './es_templates.json'

export type Lang = 'en' | 'es'

const OVERRIDES: Record<string, string> = {
  'AI Assistant': 'Asistente IA',
  'Investment Manager': 'Gestor de inversiones',
  'TerraMind AI': 'TerraMind AI',
  'Real estate investment': 'Inversión inmobiliaria',
  'Undo': 'Deshacer',
  'Excel model': 'Modelo de Excel',
  'Guest': 'Invitado',
  'Save my work': 'Guardar mi trabajo',
  'Sign out': 'Cerrar sesión',
  'model complete': 'modelo completo',
  'model incomplete': 'modelo incompleto',
  'fictional demo': 'demo ficticio',
  'portfolio': 'portafolio',
  'draft': 'borrador',
  'hypothetical': 'hipotético',
  'approved': 'aprobado',
  'Fund': 'Fondo',
  'Project': 'Proyecto',
  'Audio is never stored': 'El audio nunca se guarda',
  'Voice:': 'Voz:',
  'English': 'English',
  'Español': 'Español',
  'Translating the conversation…': 'Traduciendo la conversación…',
  'Translated · show original': 'Traducido · ver original',
  'Original · show translation': 'Original · ver traducción',
  "% total": "% del total",
  "Land": "Terreno",
  "Total": "Total",
  "Loan fees": "Comisiones del crédito",
  "All sections": "Todas las secciones",
  ". Your edits here apply directly; when the AI assistant proposes them, they wait for your confirmation click. TerraMind never executes financing transactions.": ". Tus cambios aquí se aplican directamente; cuando el asistente de IA los propone, esperan tu clic de confirmación. TerraMind nunca ejecuta operaciones de financiamiento.",
  "Evaluate sustainable construction measures: their cost, the savings and emissions they deliver, and who captures the benefit. Every return effect comes from re-running the full development model.": "Evalúa medidas de construcción sustentable: su costo, los ahorros y emisiones que generan y quién captura el beneficio. Cada efecto en rendimientos proviene de volver a correr el modelo de desarrollo completo.",
  "Every input in one place, with its source, date and verification status. AI-researched values stay pending until you approve them; outputs are calculated and never editable.": "Todos los insumos en un solo lugar, con su fuente, fecha y estatus de verificación. Los valores investigados por IA quedan pendientes hasta que los apruebes; los resultados se calculan y nunca son editables.",
  "Guests get a private workspace in this browser. Create an account anytime to keep it and sign in from any device; your guest projects move to the account.": "Los invitados obtienen un espacio privado en este navegador. Crea una cuenta en cualquier momento para conservarlo e iniciar sesión desde cualquier dispositivo; tus proyectos de invitado se mueven a la cuenta.",
  "Method: cost factor = actual development cost to date ÷ underwritten cost to date (applied to hard costs); sales pace = actual net units per month since sales started; price factor = achieved price ÷ underwritten effective price; schedule delay = progress gap × construction months. The whole model is then re-run, so IRR, MOIC, covenants and funding needs update together.": "Método: factor de costo = costo real de desarrollo a la fecha ÷ costo suscrito a la fecha (aplicado a costos directos); ritmo de ventas = unidades netas reales por mes desde el inicio de ventas; factor de precio = precio logrado ÷ precio efectivo suscrito; retraso = brecha de avance × meses de construcción. Luego se vuelve a correr todo el modelo, por lo que TIR, MOIC, covenants y necesidades de fondeo se actualizan juntos.",
  "Pricing (gpt-6-luna via Portkey): $0.10 per 1M input tokens, $0.01 per 1M cached input tokens, $0.50 per 1M output tokens. Web search calls are added at a planning estimate per call. Financial calculations use no tokens — they run in the deterministic engine.": "Precios (gpt-6-luna vía Portkey): $0.10 por 1M de tokens de entrada, $0.01 por 1M de tokens de entrada en caché, $0.50 por 1M de tokens de salida. Las búsquedas web se suman con una estimación de planeación por llamada. Los cálculos financieros no usan tokens: corren en el motor determinista.",
  "Record actual results (MXN). Cost, units and collections are per-month amounts; debt balance and progress are end-of-month levels. Saving re-runs the reforecast.": "Registra resultados reales (MXN). Costo, unidades y cobranza son montos mensuales; saldo de deuda y avance son niveles al cierre del mes. Guardar vuelve a correr la reproyección.",
  "Record actual results (USD). Cost, units and collections are per-month amounts; debt balance and progress are end-of-month levels. Saving re-runs the reforecast.": "Registra resultados reales (USD). Costo, unidades y cobranza son montos mensuales; saldo de deuda y avance son niveles al cierre del mes. Guardar vuelve a correr la reproyección.",
  "Two specialist agents challenge the underwriting before the chair issues a recommendation. Every financial figure comes from the deterministic engine; code-level guardrails can override the chair.": "Dos agentes especialistas cuestionan el análisis antes de que el presidente emita una recomendación. Cada cifra financiera proviene del motor determinista; las salvaguardas en código pueden anular al presidente.",
  "— click a number to change it. Lifecycle NPV is the owner-of-the-asset view at the project discount rate; Δ IRR / Δ profit are the developer impact from the full model with only that measure enabled.": "— haz clic en un número para cambiarlo. El VPN de ciclo de vida es la vista del dueño del activo a la tasa de descuento del proyecto; Δ TIR / Δ utilidad son el impacto para el desarrollador del modelo completo con solo esa medida activada.",
}
const DICT: Record<string, string> = { ...(ES as Record<string, string>), ...OVERRIDES }

const UNIT_WORDS: Record<string, string> = {
  stories: 'niveles', story: 'nivel', months: 'meses', month: 'mes', units: 'unidades', unit: 'unidad', levels: 'niveles',
  spaces: 'cajones', years: 'años', year: 'año', 'units/month': 'unidades/mes', 'spaces/unit': 'cajones/unidad', count: 'unidades',
  'stories designed': 'niveles diseñados', 'of hard': 'de costos directos', 'of hard + soft': 'de directos + indirectos', 'of revenue': 'de ingresos',
}
const PATTERNS: [RegExp, (m: RegExpMatchArray) => string][] = [
  [/^([\d.,]+) (stories|story|months|month|units|unit|levels|spaces|years|year|units\/month|spaces\/unit|count)$/, (m) => `${m[1]} ${UNIT_WORDS[m[2]]}`],
  [/^([\d.,]+%) (of hard \+ soft|of hard|of revenue)$/, (m) => `${m[1]} ${UNIT_WORDS[m[2]]}`],
  [/^Step (\d+)$/, (m) => `Paso ${m[1]}`],
  [/^STEP (\d+) · (.+)$/i, (m) => `Paso ${m[1]} · ${DICT[m[2]] || m[2]}`],
  [/^([\d,]+) in portfolio$/, (m) => `${m[1]} en portafolio`],
  [/^([\d,]+) in · ([\d,]+) out$/, (m) => `${m[1]} entrada · ${m[2]} salida`],
  [/^(\d+) uploaded$/, (m) => `${m[1]} cargados`],
  [/^(\d+) tool calls?$/, (m) => `${m[1]} llamada${m[1] === '1' ? '' : 's'} a herramientas`],
  [/^Month (\d+)$/, (m) => `Mes ${m[1]}`],
  [/^(\d+) critical · (\d+) watch$/, (m) => `${m[1]} críticas · ${m[2]} en observación`],
  [/^Connected to project #(\d+) · tools \+ engine$/, (m) => `Conectado al proyecto #${m[1]} · herramientas + motor`],
]

// Strings with numbers inside ("Approve 3 pending value(s)") are matched as templates: numbers become {0}, {1}…,
// the template is looked up, and the original numbers are put back.
const TEMPLATES = ES_TEMPLATES as Record<string, string>
const NUM = /[+\-−]?(?:(?:MXN|USD) )?\d[\d,]*(?:\.\d+)?(?:%|M|K|B|x)?/g
function fromTemplate(key: string): string | null {
  const nums: string[] = []
  const tpl = key.replace(NUM, (n) => `{${nums.push(n) - 1}}`)
  const hit = TEMPLATES[tpl]
  return hit ? hit.replace(/\{(\d+)\}/g, (_, i) => nums[+i] ?? '') : null
}

const SKIP_SELECTOR = '[data-no-translate], .msg, textarea, input, select option[data-raw], code, pre, .leaflet-container, script, style'

let current: Lang = (localStorage.getItem('tm-lang') as Lang) === 'es' ? 'es' : 'en'
const originals = new WeakMap<Node, string>()
let observer: MutationObserver | null = null

export function getLang(): Lang {
  return current
}

export function translate(text: string): string | null {
  const core = text.trim()
  if (!core) return null
  const key = core.replace(/\s+/g, ' ')
  const hit = DICT[key]
  if (hit) return text.replace(core, hit)
  for (const [re, fn] of PATTERNS) {
    const m = key.match(re)
    if (m) return text.replace(core, fn(m))
  }
  const tpl = fromTemplate(key)
  return tpl ? text.replace(core, tpl) : null
}

/** For code that builds strings itself (e.g. the speech-recognition notice). */
export function t(text: string): string {
  return current === 'es' ? translate(text) ?? text : text
}

function skip(node: Node): boolean {
  const el = node.nodeType === Node.ELEMENT_NODE ? (node as Element) : node.parentElement
  return !el || !!el.closest(SKIP_SELECTOR)
}

function translateText(node: Text) {
  if (skip(node)) return
  const value = node.nodeValue || ''
  const tr = translate(value)
  if (tr && tr !== value) {
    originals.set(node, value)
    node.nodeValue = tr
  }
}

const ATTRS = ['placeholder', 'title', 'aria-label']
function translateAttrs(el: Element) {
  if (el.closest('[data-no-translate], .leaflet-container')) return
  for (const a of ATTRS) {
    const v = el.getAttribute(a)
    if (!v || el.getAttribute(`data-i18n-${a}`) === v) continue
    const tr = translate(v)
    if (tr && tr !== v) {
      el.setAttribute(a, tr)
      el.setAttribute(`data-i18n-${a}`, tr)
    }
  }
}

function walk(root: Node) {
  if (root.nodeType === Node.TEXT_NODE) { translateText(root as Text); return }
  if (root.nodeType !== Node.ELEMENT_NODE) return
  const el = root as Element
  translateAttrs(el)
  el.querySelectorAll('[placeholder],[title],[aria-label]').forEach(translateAttrs)
  const tw = document.createTreeWalker(el, NodeFilter.SHOW_TEXT)
  let n: Node | null
  while ((n = tw.nextNode())) translateText(n as Text)
}

function start() {
  document.documentElement.lang = 'es'
  walk(document.body)
  observer = new MutationObserver((muts) => {
    for (const m of muts) {
      if (m.type === 'characterData') translateText(m.target as Text)
      else if (m.type === 'attributes') translateAttrs(m.target as Element)
      else m.addedNodes.forEach((n) => walk(n))
    }
  })
  observer.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS })
}

/** Call once at startup. */
export function initLanguage() {
  if (current === 'es') {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start)
    else start()
  } else {
    document.documentElement.lang = 'en'
  }
}

export function setLang(lang: Lang) {
  if (lang === current) return
  localStorage.setItem('tm-lang', lang)
  if (lang === 'es') {
    current = 'es'
    start()
    window.dispatchEvent(new Event('tm:lang'))
  } else {
    // restoring English: reload so React renders the original text cleanly (all data is on the server)
    current = 'en'
    observer?.disconnect()
    window.location.reload()
  }
}
