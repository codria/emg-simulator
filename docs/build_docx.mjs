// Build the client-facing spec documents from signal_processing_spec.md.
// Swaps the FIG markers (mermaid / ASCII diagram blocks) for the generated
// PNG figures (docs/assets/*.png, see assets/figs.mjs), then produces:
//   docs/signal_processing_spec.docx   (editable handoff)
//   docs/signal_processing_spec.html   (self-contained; browser print -> PDF)
//   docs/signal_processing_spec.pdf    (via headless Edge, if found)
// Figures carry explicit cm widths so nothing overflows the page.
//
//   node docs/build_docx.mjs           (run from repo root; needs pandoc on PATH)
import { readFileSync, writeFileSync, rmSync, existsSync } from 'node:fs'
import { execFileSync } from 'node:child_process'

const SRC = 'docs/signal_processing_spec.md'
const TMP = 'docs/_docx_build.md'

const CAP = {
  pipeline: '信号処理パイプライン（全体の流れ）',
  tanh: 'ソフト飽和 tanh の入出力（sat_gain = 1.6）',
  adapt: 'オンライン適応：peak は段差状に上がり、scale は平滑に追従',
  fan: '到達域（環状の扇形）と目標生成域',
}

// --- swap FIG markers for figure images ------------------------------------
const lines = readFileSync(SRC, 'utf8').split(/\r?\n/)
const out = []
let consume = 0                       // 0=off, 1=await opening fence, 2=inside fence
for (const line of lines) {
  if (consume === 1) {
    if (line.trim().startsWith('```')) { consume = 2; continue }
    if (line.trim() === '') continue
    consume = 0                       // no fence followed — fall through
  } else if (consume === 2) {
    if (line.trim().startsWith('```')) consume = 0
    continue
  }
  const m = line.match(/^<!--FIG-(REPLACE|HERE) (\w+) (\d+)-->\s*$/)
  if (m) {
    const [, kind, name, w] = m
    out.push('', `![${CAP[name]}](assets/${name}.png){ width=${w}cm }`, '')
    if (kind === 'REPLACE') consume = 1
    continue
  }
  out.push(line)
}
writeFileSync(TMP, out.join('\n'), 'utf8')

// --- pandoc: docx + self-contained html ------------------------------------
const pandoc = (args) => execFileSync('pandoc', args, { cwd: 'docs', stdio: 'inherit' })
pandoc(['_docx_build.md', '-o', 'signal_processing_spec.docx',
  '--toc', '--toc-depth=2', '--metadata', 'lang=ja'])
pandoc(['_docx_build.md', '-o', 'signal_processing_spec.html',
  '--standalone', '--embed-resources', '--toc', '--toc-depth=2',
  '--metadata', 'lang=ja', '--metadata', 'title=信号処理・制御パラメータ仕様',
  '-c', 'assets/spec.css'])
console.log('wrote docx + html')

// --- headless Edge: html -> pdf (optional) ---------------------------------
const EDGES = [
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
]
const edge = EDGES.find(existsSync)
if (edge) {
  const root = process.cwd().replace(/\\/g, '/')
  execFileSync(edge, ['--headless=new', '--disable-gpu', '--no-pdf-header-footer',
    `--print-to-pdf=${root}/docs/signal_processing_spec.pdf`,
    `file:///${root}/docs/signal_processing_spec.html`], { stdio: 'ignore' })
  console.log('wrote pdf (via Edge)')
} else {
  console.log('Edge not found — skip pdf (open the docx in Word -> Save as PDF)')
}

rmSync(TMP, { force: true })
