// In-page extractor: one rendered state -> measured layout JSON (shell regions, rows, blocks, components, slots,
// primitives, overlays, typography, colour and spacing). Generic: uses data-r / landmark roles when a kit has them,
// otherwise falls back to geometry and computed style. Called as page.evaluate(src) -> object.
() => {
  const VW = innerWidth, VH = innerHeight
  const R = (e) => { const r = e.getBoundingClientRect(); return { x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height) } }
  const cs = (e) => getComputedStyle(e)
  const visible = (e) => { const r = e.getBoundingClientRect(); if (r.width < 2 || r.height < 2 || r.right <= 0 || r.left >= VW) return false; const s = cs(e); return s.display !== 'none' && s.visibility !== 'hidden' && +s.opacity > 0.05 }
  const txt = (e) => (e.innerText || '').replace(/\s+/g, ' ').trim()
  const px = (v) => parseFloat(v) || 0
  const rgb = (c) => { const m = (c || '').match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(',').map(s => parseFloat(s)); if (p.length > 3 && p[3] < 0.05) return null; return '#' + p.slice(0, 3).map(v => Math.round(v).toString(16).padStart(2, '0')).join('') }

  // ---- shell regions
  const byRole = (r) => [...document.querySelectorAll(`[data-r="${r}"]`)].find(visible)
  const pick = (...sel) => { for (const s of sel) { const e = typeof s === 'string' ? [...document.querySelectorAll(s)].find(visible) : s; if (e) return e } return null }
  const regions = {}
  const rail = byRole('rail'); if (rail) regions.rail = R(rail)
  const side = pick(byRole('sidebar'), 'aside', '[class*=sidebar]', 'nav'); if (side) regions.sidebar = R(side)
  const top = pick(byRole('topbar'), 'header'); if (top) regions.topbar = R(top)
  const content = pick(byRole('pad'), byRole('canvas'), 'main', byRole('authwrap'), document.body)
  regions.content = R(content)
  const surface = (e) => { if (/^(BUTTON|A|INPUT|TEXTAREA|SELECT)$/.test(e.tagName)) return false; const s = cs(e); if (s.cursor === 'pointer' && e.getBoundingClientRect().height < 60) return false; const bw = ['Top', 'Right', 'Bottom', 'Left'].filter(k => px(s['border' + k + 'Width']) > 0 && rgb(s['border' + k + 'Color'])).length
    const r = e.getBoundingClientRect(); return (bw >= 3 || (s.boxShadow !== 'none' && rgb(s.backgroundColor))) && px(s.borderTopLeftRadius) >= 6 && r.width >= 100 && r.height >= 40 }

  // ---- text slots
  const slotRole = (t, s, upper) => {
    const size = px(s.fontSize), wt = +s.fontWeight || 400
    if (/^[↗↘+−-]?\s?[+−-]?\d[\d.,]*\s?(%|pt|x)$/.test(t) && size < 20) return 'delta'
    if (size >= 20 && /^[$£€+−-]?[\d.,]+[kKmM%]?$/.test(t.replace(/\s/g, ''))) return 'value'
    if (size >= 22) return 'heading'
    if (upper && size <= 12.5) return 'eyebrow'
    if (wt >= 600 && size >= 13) return 'title'
    if (size <= 12.5) return 'caption'
    return 'body'
  }
  const leafTexts = (root, max = 80) => {
    const out = []; const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
    let n; while ((n = w.nextNode()) && out.length < max) {
      const t = n.nodeValue.replace(/\s+/g, ' ').trim(); if (!t || !n.parentElement || !visible(n.parentElement)) continue
      const e = n.parentElement, s = cs(e); if (e.closest('i,svg')) continue
      const upper = s.textTransform === 'uppercase' || (t.length > 3 && t === t.toUpperCase() && /[A-Z]/.test(t))
      const r = R(e); out.push({ text: t.slice(0, 90), role: slotRole(t, s, upper), size: px(s.fontSize), weight: +s.fontWeight || 400, color: rgb(s.color), x: r.x, y: r.y })
    }
    return out
  }

  // ---- primitives
  const prim = (root) => {
    const c = {}; const add = (k) => (c[k] = (c[k] || 0) + 1)
    root.querySelectorAll('*').forEach((e) => {
      if (!visible(e)) return
      const s = cs(e), r = e.getBoundingClientRect(), t = txt(e), tag = e.tagName
      if (tag === 'BUTTON') return add('button')
      if (tag === 'INPUT') return add(e.type === 'checkbox' ? 'checkbox' : e.type === 'radio' ? 'radio' : 'input')
      if (tag === 'TEXTAREA') return add('textarea'); if (tag === 'SELECT') return add('select')
      if (tag === 'IMG') return add(r.width <= 56 && Math.abs(r.width - r.height) < 3 ? 'avatar' : 'image')
      if (tag === 'svg' && !e.parentElement.closest('svg')) return add(r.width > 120 && r.height > 60 ? 'chart' : 'icon-svg')
      if (tag === 'I' && /hgi|icon|fa-|bi-|ri-/.test(e.className)) return add('icon')
      if (s.cursor === 'pointer' && r.height <= 46 && t && t.length < 40 && px(s.borderTopLeftRadius) >= 6 && e.children.length <= 3) return add(r.height <= 34 ? 'pill' : 'button')
      if (r.height >= 16 && r.height <= 26 && r.width >= 30 && r.width <= 46 && px(s.borderTopLeftRadius) >= 8 && !t) return add('toggle')
      if (r.height <= 10 && r.width >= 40 && px(s.borderTopLeftRadius) >= 2 && rgb(s.backgroundColor) && !t) return add('progress')
      if (t && t.length < 24 && r.height >= 16 && r.height <= 28 && px(s.borderTopLeftRadius) >= 4 && rgb(s.backgroundColor) && e.children.length === 0 && s.display.includes('flex')) return add('badge')
    })
    return c
  }

  // ---- repeated items (lists, tables, card grids, chart bars)
  const sig = (e) => e.tagName + '|' + e.children.length + '|' + cs(e).display + '|' + Math.round(e.getBoundingClientRect().height / 4)
  const repeats = (root) => {
    const out = []
    root.querySelectorAll('*').forEach((p) => {
      const kids = [...p.children].filter(visible); if (kids.length < 3) return
      const m = {}; kids.forEach(k => { const g = sig(k); (m[g] = m[g] || []).push(k) })
      Object.values(m).forEach(g => { if (g.length < 3) return
        const a = R(g[0]), b = R(g[1]); const dir = Math.abs(a.y - b.y) < 4 ? 'row' : 'column'
        const hasText = g.some(k => txt(k)); out.push({ count: g.length, direction: dir, item: { w: a.w, h: a.h }, gap: dir === 'row' ? b.x - a.x - a.w : b.y - a.y - a.h,
          kind: !hasText ? 'bars' : g[0].children.length >= 3 && dir === 'column' ? 'rows' : dir === 'row' ? 'tiles' : 'list', sample: hasText ? leafTexts(g[0], 12).map(s => ({ text: s.text, role: s.role })) : [] }) })
    })
    // keep outermost distinct groups only
    return out.sort((a, b) => b.count * b.item.h - a.count * a.item.h).slice(0, 8)
  }

  // ---- blocks: outermost surfaces inside the content region (plus the page header row)
  const cR = content.getBoundingClientRect()
  const all = [...content.querySelectorAll('*')].filter(e => visible(e) && surface(e))
  const tops = all.filter(e => !all.some(o => o !== e && o.contains(e)))
  const blocks = []
  const h1 = [...content.querySelectorAll('[data-r=h1],h1')].find(visible)
  if (h1) { const row = h1.closest('[data-r=col-sm]') || h1.parentElement.parentElement; if (row && !tops.some(t => t.contains(row) || row.contains(t))) tops.unshift(row) }
  tops.forEach((e, i) => {
    const r = R(e), s = cs(e)
    const inner = all.filter(o => o !== e && e.contains(o) && !all.some(p => p !== o && p !== e && e.contains(p) && p.contains(o)))
    const slots = leafTexts(e, 60).map(x => Object.assign(x, { x: x.x - r.x, y: x.y - r.y }))
    blocks.push({ id: 'b' + i, bbox: r, rel: { x: +((r.x - cR.left - scrollX) / cR.width).toFixed(3), w: +(r.w / cR.width).toFixed(3) },
      surface: e === h1?.closest('[data-r=col-sm]') ? 'none' : { bg: rgb(s.backgroundColor), radius: px(s.borderTopLeftRadius), border: rgb(s.borderTopColor), shadow: s.boxShadow !== 'none', padding: [s.paddingTop, s.paddingRight, s.paddingBottom, s.paddingLeft].map(px) },
      eyebrow: slots.find(x => x.role === 'eyebrow')?.text || null, title: (slots.find(x => x.role === 'heading' || x.role === 'title') || {}).text || null,
      slots, primitives: prim(e), repeats: repeats(e),
      components: inner.map((o, j) => { const q = R(o); return { id: `b${i}.c${j}`, bbox: { x: q.x - r.x, y: q.y - r.y, w: q.w, h: q.h }, slots: leafTexts(o, 14).map(x => ({ text: x.text, role: x.role, size: x.size, weight: x.weight })), primitives: prim(o) } }) })
  })

  // ---- rows / columns
  const rows = []
  blocks.slice().sort((a, b) => a.bbox.y - b.bbox.y).forEach(b => {
    const row = rows.find(r => b.bbox.y < r.y + r.h - 8 && b.bbox.y + b.bbox.h > r.y + 8)
    if (row) { row.blocks.push(b.id); row.h = Math.max(row.h, b.bbox.y + b.bbox.h - row.y) } else rows.push({ y: b.bbox.y, h: b.bbox.h, blocks: [b.id] })
  })
  rows.forEach((r, i) => { const bs = r.blocks.map(id => blocks.find(b => b.id === id)).sort((a, b) => a.bbox.x - b.bbox.x); r.blocks = bs.map(b => b.id)
    r.index = i; r.cols = bs.length; r.ratios = bs.map(b => b.rel.w); r.gaps = bs.slice(1).map((b, k) => b.bbox.x - bs[k].bbox.x - bs[k].bbox.w)
    r.gap_below = i < rows.length - 1 ? rows[i + 1].y - r.y - r.h : null })

  // ---- overlays (menus, popovers, modals, drawers, toasts)
  const overlays = [...document.querySelectorAll('body *')].filter(e => { if (!visible(e)) return false; const s = cs(e); return (s.position === 'absolute' || s.position === 'fixed') && +s.zIndex >= 20 && e.getBoundingClientRect().width > 120 && txt(e) })
    .filter((e, _, a) => !a.some(o => o !== e && o.contains(e)))
    .map(e => { const s = cs(e); const r = R(e); return { bbox: r, position: s.position, kind: r.w > VW * 0.6 && r.h > VH * 0.6 ? 'modal' : r.h > VH * 0.7 ? 'drawer' : r.h < 70 ? 'toast' : 'menu', slots: leafTexts(e, 30).map(x => ({ text: x.text, role: x.role })), primitives: prim(e) } })

  // ---- interactive inventory (for flow discovery)
  const clickables = [...content.ownerDocument.querySelectorAll('button, a, input, textarea, select, [role=button], *')].filter(e => {
    if (!visible(e)) return false; const s = cs(e); if (s.cursor !== 'pointer' && !/^(BUTTON|A|INPUT|TEXTAREA|SELECT)$/.test(e.tagName)) return false
    return !(e.parentElement && cs(e.parentElement).cursor === 'pointer' && e.parentElement.tagName !== 'BODY') })
  const controls = clickables.map((e, i) => { const r = R(e); const region = Object.entries(regions).find(([k, b]) => k !== 'content' && r.x >= b.x - 2 && r.x < b.x + b.w && r.y >= b.y - 2 && r.y < b.y + b.h)?.[0] || 'content'
    return { i, tag: e.tagName.toLowerCase(), label: (txt(e) || e.getAttribute('placeholder') || e.getAttribute('aria-label') || e.querySelector('i')?.className || '').slice(0, 60), region, bbox: r } })

  // ---- typography, colour, spacing, density
  const tset = {}, cset = {}, bset = {}
  document.querySelectorAll('body *').forEach(e => { if (!visible(e)) return; const s = cs(e)
    if ([...e.childNodes].some(n => n.nodeType === 3 && n.nodeValue.trim())) { const k = px(s.fontSize) + '/' + s.fontWeight; tset[k] = (tset[k] || 0) + 1; const c = rgb(s.color); if (c) cset[c] = (cset[c] || 0) + 1 }
    const b = rgb(s.backgroundColor); if (b) { const r = e.getBoundingClientRect(); bset[b] = (bset[b] || 0) + Math.round(r.width * r.height / 1000) } })
  const rank = (o, n) => Object.entries(o).sort((a, b) => b[1] - a[1]).slice(0, n).map(([k, v]) => ({ v: k, n: v }))
  const fam = cs(document.body).fontFamily
  const blockArea = blocks.reduce((a, b) => a + b.bbox.w * b.bbox.h, 0)
  return {
    viewport: { w: VW, h: VH }, page: { w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight },
    title: txt(h1 || document.createElement('i')) || document.title, crumbs: top ? txt(top).slice(0, 80) : '',
    shell: { regions, font: fam }, layout: { rows, content_width: Math.round(cR.width), above_fold_rows: rows.filter(r => r.y < VH).length },
    blocks, overlays, controls,
    typography: rank(tset, 14), colors: { text: rank(cset, 10), background: rank(bset, 10) },
    density: { blocks: blocks.length, controls: controls.length, text_nodes: blocks.reduce((a, b) => a + b.slots.length, 0), block_coverage: +(blockArea / Math.max(1, cR.width * Math.max(cR.height, VH))).toFixed(2), scroll_screens: +(document.documentElement.scrollHeight / VH).toFixed(2) }
  }
}
