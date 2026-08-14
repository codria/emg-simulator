// Generate print-friendly SVG figures for the spec docx, rasterize to PNG.
// Figures are the single source for both docs/signal_processing_spec.md (GitHub)
// and the docx/pdf/html builds (see ../build_docx.mjs).
//
//   npm i @resvg/resvg-js            # one-off; SVG->PNG, no Chromium
//   node docs/assets/figs.mjs docs/assets
import { Resvg } from '@resvg/resvg-js'
import { writeFileSync } from 'node:fs'

const OUT = process.argv[2] || '.'            // output dir for png/svg
const FAM = 'Yu Gothic UI, Meiryo, sans-serif'
const INK = '#1f2430', SUB = '#5b6472', GRID = '#d7dce3', AXIS = '#8a93a1'
const TEAL = '#0e7aa8', AMBER = '#b07405', GREEN = '#2f9e57', RED = '#c0504d'
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
const T = (x, y, s, o = {}) =>
  `<text x="${x}" y="${y}" font-family="${FAM}" font-size="${o.fs || 15}"` +
  ` fill="${o.fill || INK}" text-anchor="${o.a || 'start'}"` +
  `${o.w ? ` font-weight="${o.w}"` : ''}${o.i ? ' font-style="italic"' : ''}>${esc(s)}</text>`

function rasterize(name, svg, w2x) {
  writeFileSync(`${OUT}/${name}.svg`, svg)
  const r = new Resvg(svg, { fitTo: { mode: 'width', value: w2x }, font: { loadSystemFonts: true, defaultFontFamily: 'Yu Gothic UI' } })
  writeFileSync(`${OUT}/${name}.png`, r.render().asPng())
  console.log('wrote', name)
}

// ---------------------------------------------------------------- pipeline
function pipeline() {
  const W = 760, cx = W / 2, boxW = 430, boxH = 54, gap = 14, titleH = 30, pad = 14, sgap = 22
  const stages = [
    { title: '① 信号処理  ―  生 EMG を「力の量」に均す', fill: '#e9f1f8', bd: '#9db4c7',
      boxes: [['生 EMG 2ch', 'サンプリング ≥ 1000 Hz'], ['帯域通過フィルタ', '20 – 450 Hz'],
        ['ノッチフィルタ', '50 / 60 Hz（電源ハム除去）'], ['整流 ＋ RMS', '窓長 = rms_window_ms'],
        ['EMA 平滑', '係数 = ema_alpha']] },
    { title: '② 正規化  ―  個人差を吸収して 0–1 に', fill: '#f1ecf8', bd: '#b3a6cf',
      boxes: [['ベースライン減算', 'baseline（脱力時に較正）'], ['スケール除算', 'scale（オンライン適応）'],
        ['ソフト飽和  tanh', '利得 = sat_gain'], ['活性度 a', '0 – 1（制御・判定に使う値）']] },
    { title: '③ マッピング  ―  0–1 を到達域→関節角に', fill: '#e7f4ec', bd: '#a3ccb0',
      boxes: [['マッピング', '左 → θ（向き） ／ 右 → r（伸び）'], ['逆運動学  IK', '(r, θ) → 6 関節角'],
        ['ロボットアーム', '6 自由度']] },
  ]
  let y = 16, parts = []
  const arrow = (yy) => `<line x1="${cx}" y1="${yy}" x2="${cx}" y2="${yy + gap}" stroke="${SUB}" stroke-width="2"/>` +
    `<path d="M${cx - 5},${yy + gap - 6} L${cx + 5},${yy + gap - 6} L${cx},${yy + gap} Z" fill="${SUB}"/>`
  stages.forEach((st, si) => {
    const bandTop = y
    const bh = titleH + pad + st.boxes.length * boxH + (st.boxes.length - 1) * gap + pad
    parts.push(`<rect x="24" y="${bandTop}" width="${W - 48}" height="${bh}" rx="12" fill="${st.fill}" stroke="${st.bd}" stroke-width="1.5"/>`)
    parts.push(T(40, bandTop + 21, st.title, { fs: 16, w: 700, fill: INK }))
    y = bandTop + titleH + pad
    st.boxes.forEach((b, bi) => {
      parts.push(`<rect x="${cx - boxW / 2}" y="${y}" width="${boxW}" height="${boxH}" rx="8" fill="#ffffff" stroke="${st.bd}" stroke-width="1.5"/>`)
      parts.push(T(cx, y + 22, b[0], { fs: 16, w: 600, a: 'middle' }))
      parts.push(T(cx, y + 42, b[1], { fs: 13, fill: SUB, a: 'middle' }))
      y += boxH
      if (bi < st.boxes.length - 1) { parts.push(arrow(y)); y += gap }
    })
    y = bandTop + bh
    if (si < stages.length - 1) { parts.push(arrow(y)); y += gap + sgap; y = bandTop + bh + sgap }
  })
  const H = y + 16
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">` +
    `<rect width="${W}" height="${H}" fill="#ffffff"/>${parts.join('')}</svg>`
  rasterize('pipeline', svg, W * 2)
}

// ---------------------------------------------------------------- tanh curve
function tanhFig() {
  const W = 660, H = 420, L = 70, R = 30, Tp = 30, B = 60
  const x0 = L, x1 = W - R, y0 = H - B, y1 = Tp
  const XMAX = 2.5, gain = 1.6
  const sx = v => x0 + (v / XMAX) * (x1 - x0)
  const sy = v => y0 + v * (y1 - y0)              // v in 0..1
  let p = []
  p.push(`<rect width="${W}" height="${H}" fill="#ffffff"/>`)
  // grid + y ticks
  for (let g = 0; g <= 1.0001; g += 0.25) {
    p.push(`<line x1="${x0}" y1="${sy(g)}" x2="${x1}" y2="${sy(g)}" stroke="${GRID}" stroke-width="1"/>`)
    p.push(T(x0 - 10, sy(g) + 5, g.toFixed(2), { fs: 12, fill: SUB, a: 'end' }))
  }
  for (let g = 0; g <= XMAX + 1e-6; g += 0.5) {
    p.push(`<line x1="${sx(g)}" y1="${y0}" x2="${sx(g)}" y2="${y1}" stroke="${GRID}" stroke-width="1"/>`)
    p.push(T(sx(g), y0 + 20, g.toFixed(1), { fs: 12, fill: SUB, a: 'middle' }))
  }
  // axes
  p.push(`<line x1="${x0}" y1="${y0}" x2="${x1}" y2="${y0}" stroke="${AXIS}" stroke-width="1.5"/>`)
  p.push(`<line x1="${x0}" y1="${y0}" x2="${x0}" y2="${y1}" stroke="${AXIS}" stroke-width="1.5"/>`)
  // hard-clip reference (dashed)
  const clip = `M${sx(0)},${sy(0)} L${sx(1)},${sy(1)} L${sx(XMAX)},${sy(1)}`
  p.push(`<path d="${clip}" fill="none" stroke="${SUB}" stroke-width="1.5" stroke-dasharray="6 5"/>`)
  // tanh curve
  let d = ''
  for (let i = 0; i <= 100; i++) { const xv = XMAX * i / 100, yv = Math.tanh(gain * xv); d += (i ? 'L' : 'M') + sx(xv).toFixed(1) + ',' + sy(yv).toFixed(1) + ' ' }
  p.push(`<path d="${d}" fill="none" stroke="${TEAL}" stroke-width="3"/>`)
  // mark full-effort point (1.0, 0.92)
  const yv1 = Math.tanh(gain)
  p.push(`<line x1="${sx(1)}" y1="${y0}" x2="${sx(1)}" y2="${sy(yv1)}" stroke="${RED}" stroke-width="1.2" stroke-dasharray="3 3"/>`)
  p.push(`<line x1="${x0}" y1="${sy(yv1)}" x2="${sx(1)}" y2="${sy(yv1)}" stroke="${RED}" stroke-width="1.2" stroke-dasharray="3 3"/>`)
  p.push(`<circle cx="${sx(1)}" cy="${sy(yv1)}" r="4.5" fill="${RED}"/>`)
  p.push(T(sx(1) + 10, sy(yv1) - 8, '満力 ≒ 0.92', { fs: 13, fill: RED, w: 600 }))
  // labels
  p.push(T((x0 + x1) / 2, H - 16, '力み比  a_pre = x / scale   （1.0 ≒ 満力）', { fs: 14, a: 'middle', fill: INK }))
  p.push(`<g transform="translate(18,${(y0 + y1) / 2}) rotate(-90)">${T(0, 0, '活性度 a', { fs: 14, a: 'middle', fill: INK })}</g>`)
  p.push(T(sx(1.55), sy(0.86), 'tanh（ソフト飽和）', { fs: 13, fill: TEAL, w: 600 }))
  p.push(T(sx(1.35), sy(1.0) - 8, 'ハードclip（比較）', { fs: 12, fill: SUB }))
  rasterize('tanh', `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">${p.join('')}</svg>`, W * 2)
}

// ---------------------------------------------------------------- adaptation
function adaptFig() {
  const W = 720, H = 400, L = 58, R = 168, Tp = 26, B = 54
  const x0 = L, x1 = W - R, y0 = H - B, y1 = Tp
  const YMAX = 1.18, Tsec = 120, dt = 0.5, N = Tsec / dt, hl = 45, fb = 0.5, rate = 0.3
  const sx = s => x0 + (s / Tsec) * (x1 - x0)
  const sy = v => y0 + (v / YMAX) * (y1 - y0)
  // x: rest → hard effort → moderate, deterministic jitter (no RNG)
  const xAt = s => { const b = s < 16 ? 0.30 : s < 40 ? 1.00 : 0.45; return Math.max(0, b + 0.04 * Math.sin(s * 1.7) * Math.cos(s * 0.6)) }
  let peak = 0.30, scale = 0.50
  const P = [], S = [], X = []
  for (let i = 0; i <= N; i++) {
    const s = i * dt, x = xAt(s)
    peak = Math.max(peak * Math.pow(0.5, dt / hl), x)      // leaky "recent max"
    scale = scale + rate * (Math.max(peak, fb) - scale)    // toward max(peak, fallback), both ways
    X.push([s, Math.min(x, YMAX)]); P.push([s, peak]); S.push([s, scale])
  }
  let p = [`<rect width="${W}" height="${H}" fill="#ffffff"/>`]
  for (let g = 0; g <= 1.0001; g += 0.25) {
    p.push(`<line x1="${x0}" y1="${sy(g)}" x2="${x1}" y2="${sy(g)}" stroke="${GRID}" stroke-width="1"/>`)
    p.push(T(x0 - 10, sy(g) + 5, g.toFixed(2), { fs: 12, fill: SUB, a: 'end' }))
  }
  p.push(`<line x1="${x0}" y1="${y0}" x2="${x1}" y2="${y0}" stroke="${AXIS}" stroke-width="1.5"/>`)
  p.push(`<line x1="${x0}" y1="${y0}" x2="${x0}" y2="${y1}" stroke="${AXIS}" stroke-width="1.5"/>`)
  for (let s = 0; s <= Tsec; s += 30) p.push(T(sx(s), y0 + 20, s + 's', { fs: 12, fill: SUB, a: 'middle' }))
  p.push(`<line x1="${x0}" y1="${sy(fb)}" x2="${x1}" y2="${sy(fb)}" stroke="#b9bfc9" stroke-width="1" stroke-dasharray="3 4"/>`)
  p.push(T(x1 - 4, sy(fb) - 5, 'fallback', { fs: 11, fill: SUB, a: 'end' }))
  p.push(`<rect x="${sx(16)}" y="${y1}" width="${sx(40) - sx(16)}" height="${y0 - y1}" fill="${AMBER}" fill-opacity="0.07"/>`)
  p.push(T((sx(16) + sx(40)) / 2, y1 + 14, '力む', { fs: 12, fill: AMBER, a: 'middle' }))
  const path = (arr, extra = '') => { let d = ''; arr.forEach((q, i) => d += (i ? 'L' : 'M') + sx(q[0]).toFixed(1) + ',' + sy(q[1]).toFixed(1) + ' '); return d }
  p.push(`<path d="${path(X)}" fill="none" stroke="#c3cad4" stroke-width="1.5"/>`)         // raw x
  p.push(`<path d="${path(P)}" fill="none" stroke="${AMBER}" stroke-width="2.5"/>`)         // peak (step)
  p.push(`<path d="${path(S)}" fill="none" stroke="${TEAL}" stroke-width="3"/>`)            // scale (smooth)
  // axis labels
  p.push(T((x0 + x1) / 2, H - 12, '時間 (s) →', { fs: 14, a: 'middle', fill: INK }))
  // legend (right gutter)
  const lx = x1 + 16
  let ly = y1 + 10
  const leg = (c, t, sw = 3, dash = '') => { p.push(`<line x1="${lx}" y1="${ly}" x2="${lx + 26}" y2="${ly}" stroke="${c}" stroke-width="${sw}" ${dash}/>`); p.push(T(lx + 32, ly + 5, t, { fs: 13, fill: INK })); ly += 26 }
  leg('#c3cad4', 'x（力み・生）', 1.5)
  leg(AMBER, 'peak（リーク）', 2.5)
  leg(TEAL, 'scale（追従）', 3)
  p.push(T(lx, ly + 8, '力むと跳ね上がり、', { fs: 12, fill: SUB }))
  p.push(T(lx, ly + 26, '放すと半減期で', { fs: 12, fill: SUB }))
  p.push(T(lx, ly + 44, 'ゆっくり減衰。', { fs: 12, fill: SUB }))
  p.push(T(lx, ly + 62, 'scale は両方向、', { fs: 12, fill: SUB }))
  p.push(T(lx, ly + 80, 'fallback が下限。', { fs: 12, fill: SUB }))
  rasterize('adapt', `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">${p.join('')}</svg>`, W * 2)
}

// ---------------------------------------------------------------- reach fan
function fanFig() {
  const W = 760, H = 430, cx = W / 2, cy = H - 70
  const rmin = 0.23, rmax = 0.70, thmin = 0, thmax = 180, mR = 0.12, mTh = 0.12
  const OUT_PX = 300, ppm = OUT_PX / rmax
  const pt = (r, thDeg) => { const a = thDeg * Math.PI / 180; return [cx + r * ppm * Math.cos(a), cy - r * ppm * Math.sin(a)] }
  const arc = (r, a0, a1) => { const [x0, y0] = pt(r, a0), [x1, y1] = pt(r, a1); return `M${x0.toFixed(1)},${y0.toFixed(1)} A${(r * ppm).toFixed(1)},${(r * ppm).toFixed(1)} 0 0 0 ${x1.toFixed(1)},${y1.toFixed(1)}` }
  const wedge = (r0, r1, a0, a1, fill, op) => {
    const [ax, ay] = pt(r1, a0), [bx, by] = pt(r1, a1), [ecx, ecy] = pt(r0, a1), [dx, dy] = pt(r0, a0)
    return `<path d="M${ax},${ay} A${(r1 * ppm)},${(r1 * ppm)} 0 0 0 ${bx},${by} L${ecx},${ecy} A${(r0 * ppm)},${(r0 * ppm)} 0 0 1 ${dx},${dy} Z" fill="${fill}" fill-opacity="${op}"/>`
  }
  let p = [`<rect width="${W}" height="${H}" fill="#ffffff"/>`]
  // full reachable fan (light) + target band (greener)
  p.push(wedge(rmin, rmax, thmin, thmax, '#dbe6f0', 1))
  const rb0 = rmin + mR * (rmax - rmin), rb1 = rmax - mR * (rmax - rmin)
  const tb0 = thmin + mTh * (thmax - thmin), tb1 = thmax - mTh * (thmax - thmin)
  p.push(wedge(rb0, rb1, tb0, tb1, GREEN, 0.28))
  // arcs
  p.push(`<path d="${arc(rmin, thmin, thmax)}" fill="none" stroke="${SUB}" stroke-width="1.5"/>`)
  p.push(`<path d="${arc(rmax, thmin, thmax)}" fill="none" stroke="${SUB}" stroke-width="1.5"/>`)
  // straight edges
  for (const th of [thmin, thmax]) { const [x, y] = pt(rmax, th), [xi, yi] = pt(rmin, th); p.push(`<line x1="${xi}" y1="${yi}" x2="${x}" y2="${y}" stroke="${SUB}" stroke-width="1.5"/>`) }
  // sample radial (r) in teal
  const thS = 58
  const [rx, ry] = pt(rmax, thS)
  p.push(`<line x1="${cx}" y1="${cy}" x2="${rx}" y2="${ry}" stroke="${TEAL}" stroke-width="2.5"/>`)
  const [rmx, rmy] = pt(rmax * 0.6, thS)
  p.push(T(rmx + 8, rmy, 'r', { fs: 20, fill: TEAL, i: true, w: 700 }))
  // theta arc (amber) near origin
  p.push(`<path d="${arc(0.24, 0, thS)}" fill="none" stroke="${AMBER}" stroke-width="2.5"/>`)
  const [tlx, tly] = pt(0.30, thS / 2)
  p.push(T(tlx, tly, 'θ', { fs: 20, fill: AMBER, i: true, w: 700 }))
  // theta=0 reference
  const [zx, zy] = pt(rmax * 0.9, 0)
  p.push(`<line x1="${cx}" y1="${cy}" x2="${zx}" y2="${zy}" stroke="${AMBER}" stroke-width="1" stroke-dasharray="4 4"/>`)
  // base
  p.push(`<circle cx="${cx}" cy="${cy}" r="6" fill="${INK}"/>`)
  p.push(`<rect x="${cx - 26}" y="${cy + 6}" width="52" height="12" rx="3" fill="#b8bec8"/>`)
  p.push(T(cx, cy + 40, 'アーム基部（原点）', { fs: 13, a: 'middle', fill: SUB }))
  // angle labels
  let [a0x, a0y] = pt(rmax, 0); p.push(T(a0x + 8, a0y + 4, 'θ = 0°', { fs: 13, fill: INK }))
  let [a9x, a9y] = pt(rmax, 90); p.push(T(a9x, a9y - 10, 'θ = 90°（前方）', { fs: 13, a: 'middle', fill: INK }))
  let [a1x, a1y] = pt(rmax, 180); p.push(T(a1x - 8, a1y + 4, 'θ = 180°', { fs: 13, a: 'end', fill: INK }))
  // r labels
  let [rmnx, rmny] = pt(rmin, 118); p.push(T(rmnx - 4, rmny + 4, 'r_min = 0.23', { fs: 12, a: 'end', fill: INK }))
  let [rmxx, rmxy] = pt(rmax, 122); p.push(T(rmxx - 4, rmxy - 6, 'r_max = 0.70', { fs: 12, a: 'end', fill: INK }))
  // legend for band
  p.push(`<rect x="40" y="24" width="18" height="18" rx="3" fill="${GREEN}" fill-opacity="0.28"/>`)
  p.push(T(64, 38, '目標の生成域（端を target_margin だけ内側に）', { fs: 13, fill: INK }))
  rasterize('fan', `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">${p.join('')}</svg>`, W * 2)
}

pipeline(); tanhFig(); adaptFig(); fanFig()
console.log('done ->', OUT)
