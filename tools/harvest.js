() => {
  const rgb = (c) => { const m = (c || '').match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(',').map(parseFloat); if (p.length > 3 && p[3] < 0.05) return null; return '#' + p.slice(0, 3).map(v => Math.round(v).toString(16).padStart(2, '0')).join('') + (p.length > 3 && p[3] < 1 ? Math.round(p[3] * 255).toString(16).padStart(2, '0') : '') }
  const px = parseFloat, out = []
  const vis = (e) => { const r = e.getBoundingClientRect(); if (r.width < 2 || r.height < 2 || r.right < 0) return false; const s = getComputedStyle(e); return s.display !== 'none' && s.visibility !== 'hidden' }
  document.querySelectorAll('body *').forEach(e => {
    if (!vis(e) || e.closest('svg')) return
    const s = getComputedStyle(e), r = e.getBoundingClientRect(), t = (e.innerText || '').replace(/\s+/g, ' ').trim(), tag = e.tagName
    const bg = rgb(s.backgroundColor) || (s.backgroundImage.includes('gradient') ? 'gradient' : null), rad = px(s.borderTopLeftRadius), bc = px(s.borderTopWidth) ? rgb(s.borderTopColor) : null
    let kind = null
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') kind = tag === 'INPUT' && (e.type === 'checkbox' || e.type === 'radio') ? e.type : 'input'
    else if (tag === 'IMG' && r.width <= 56 && Math.abs(r.width - r.height) < 3) kind = 'avatar'
    else if (tag === 'IMG') return
    else if ((tag === 'BUTTON' || s.cursor === 'pointer') && t && t.length < 40 && r.height <= 56 && e.children.length <= 4) kind = r.height <= 34 && rad >= 6 && (bg || bc) ? 'pill-button' : 'button'
    else if (s.cursor === 'pointer' && !t && r.width <= 44 && r.height <= 44 && (bg || bc)) kind = 'icon-button'
    else if (!t && r.height >= 16 && r.height <= 26 && r.width >= 30 && r.width <= 48 && rad >= 8 && bg) kind = 'toggle'
    else if (!t && r.height <= 10 && r.width >= 30 && bg && rad >= 2) kind = 'progress'
    else if (!t && r.width >= 28 && r.width <= 48 && Math.abs(r.width - r.height) < 2 && rad >= 8 && (bg || bc) && e.querySelector('i')) kind = 'icon-tile'
    else if (t && t.length < 28 && r.height >= 16 && r.height <= 30 && rad >= 4 && (bg || bc) && e.children.length === 0 && s.cursor !== 'pointer') kind = s.fontFamily.toLowerCase().includes('mono') ? 'mono-chip' : 'badge'
    else if (t && e.children.length === 0 && s.textTransform === 'uppercase' && px(s.fontSize) <= 12.5) kind = 'eyebrow'
    if (!kind) return
    const st = { bg, color: rgb(s.color), border: bc, radius: rad, h: Math.round(r.height), font: px(s.fontSize) + '/' + s.fontWeight, pad: s.paddingLeft, shadow: s.boxShadow !== 'none', mono: s.fontFamily.toLowerCase().includes('mono') }
    if (kind !== 'button' && kind !== 'pill-button' && kind !== 'input') delete st.pad
    out.push({ kind, st, label: (t || e.getAttribute('placeholder') || '').slice(0, 30) })
  })
  return out }
