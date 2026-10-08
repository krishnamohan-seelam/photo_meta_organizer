/*
 * Shared sample library for the UI prototypes in src/prototypes.
 * Plain browser script (no build step): it defines window.PMO with sample photos shaped like
 * the API's PhotoMetadata (flattened), procedural SVG "photographs" so the prototypes work offline,
 * and a small inline icon set modelled on lucide-react, which the real app already uses.
 */
;(function () {
  'use strict'

  const PHOTOS = [
    { id: 'a1', name: 'DSC04928_Tokyo_Tower_Sunset.ARW', title: 'Tokyo Tower Sunset', make: 'Sony', camera: 'Sony α7 IV', lens: 'FE 35mm F1.4 GM', f: 2.8, ss: '1/250', iso: 400, fl: 35, date: '2026-05-14T18:42', place: 'Tokyo', country: 'Japan', rating: 5, flag: true, tags: ['travel', 'japan', 'architecture', 'sunset'], w: 3, h: 2, scene: 'sunsetCity', mb: 25.3, fmt: 'ARW', lat: 35.6586, lon: 139.7454 },
    { id: 'a2', name: 'R0012044_Shibuya_Crossing.DNG', title: 'Shibuya Crossing', make: 'Ricoh', camera: 'Ricoh GR III', lens: 'GR 18.3mm F2.8', f: 2.8, ss: '1/60', iso: 3200, fl: 18, date: '2026-05-14T21:10', place: 'Tokyo', country: 'Japan', rating: 4, flag: false, tags: ['travel', 'japan', 'street', 'night'], w: 3, h: 2, scene: 'cityNight', mb: 22.1, fmt: 'DNG', lat: 35.6595, lon: 139.7005 },
    { id: 'a3', name: 'DSC05110_Mt_Fuji_Dawn.ARW', title: 'Mt Fuji at Dawn', make: 'Sony', camera: 'Sony α7 IV', lens: 'FE 70-200mm F2.8 GM II', f: 8, ss: '1/500', iso: 100, fl: 135, date: '2026-05-15T05:31', place: 'Fujikawaguchiko', country: 'Japan', rating: 5, flag: true, tags: ['travel', 'japan', 'landscape'], w: 16, h: 9, scene: 'fuji', mb: 27.8, fmt: 'ARW', lat: 35.5171, lon: 138.7517 },
    { id: 'a4', name: 'IMG_8392_Kyoto_Bamboo_Path.CR3', title: 'Bamboo Grove Path', make: 'Canon', camera: 'Canon EOS R5', lens: 'RF 24-70mm F2.8L', f: 4, ss: '1/125', iso: 800, fl: 24, date: '2026-05-16T08:15', place: 'Kyoto', country: 'Japan', rating: 4, flag: false, tags: ['travel', 'japan', 'nature'], w: 2, h: 3, scene: 'bamboo', mb: 38.9, fmt: 'CR3', lat: 35.0167, lon: 135.6713 },
    { id: 'a5', name: 'DSCF2231_Fushimi_Inari.RAF', title: 'Fushimi Inari Gates', make: 'Fujifilm', camera: 'Fujifilm X-T5', lens: 'XF 16-55mm F2.8', f: 5.6, ss: '1/60', iso: 1600, fl: 23, date: '2026-05-16T16:40', place: 'Kyoto', country: 'Japan', rating: 3, flag: false, tags: ['travel', 'japan', 'architecture'], w: 2, h: 3, scene: 'gates', mb: 31.2, fmt: 'RAF', lat: 34.9671, lon: 135.7727 },
    { id: 'a6', name: 'DSCF2302_Arashiyama_Maples.RAF', title: 'Arashiyama Maples', make: 'Fujifilm', camera: 'Fujifilm X-T5', lens: 'XF 56mm F1.2', f: 1.2, ss: '1/1000', iso: 160, fl: 56, date: '2026-05-17T10:05', place: 'Kyoto', country: 'Japan', rating: 4, flag: false, tags: ['nature', 'japan'], w: 4, h: 3, scene: 'autumn', mb: 29.4, fmt: 'RAF', lat: 35.0094, lon: 135.6668 },
    { id: 'a7', name: 'IMG_8611_Nara_Portrait.CR3', title: 'Portrait in Nara Park', make: 'Canon', camera: 'Canon EOS R5', lens: 'RF 85mm F1.2L', f: 1.2, ss: '1/800', iso: 100, fl: 85, date: '2026-05-18T14:22', place: 'Nara', country: 'Japan', rating: 5, flag: true, tags: ['portrait', 'japan'], w: 4, h: 5, scene: 'portrait', mb: 41.0, fmt: 'CR3', lat: 34.6851, lon: 135.843 },
    { id: 'a8', name: 'R0012310_Dotonbori_Neon.DNG', title: 'Dotonbori Neon', make: 'Ricoh', camera: 'Ricoh GR III', lens: 'GR 18.3mm F2.8', f: 2.8, ss: '1/30', iso: 6400, fl: 18, date: '2026-05-18T22:47', place: 'Osaka', country: 'Japan', rating: 2, flag: false, tags: ['street', 'night', 'japan'], w: 2, h: 3, scene: 'cityNight', mb: 21.7, fmt: 'DNG', lat: 34.6687, lon: 135.5013 },
    { id: 'a9', name: 'IMG_4410_Okinawa_Reef.HEIC', title: 'Okinawa Reef Lagoon', make: 'Apple', camera: 'iPhone 15 Pro', lens: 'Main 24mm ƒ1.78', f: 1.8, ss: '1/2000', iso: 50, fl: 24, date: '2026-05-21T12:03', place: 'Okinawa', country: 'Japan', rating: 3, flag: false, tags: ['travel', 'ocean'], w: 4, h: 3, scene: 'ocean', mb: 3.1, fmt: 'HEIC', lat: 26.6869, lon: 127.8775 },
    { id: 'b1', name: 'DSC01877_Aurora_Kirkjufell.ARW', title: 'Aurora over Kirkjufell', make: 'Sony', camera: 'Sony α7 IV', lens: 'FE 14mm F1.8 GM', f: 1.8, ss: '8s', iso: 3200, fl: 14, date: '2026-02-11T23:18', place: 'Grundarfjörður', country: 'Iceland', rating: 5, flag: true, tags: ['iceland', 'night', 'landscape'], w: 3, h: 2, scene: 'aurora', mb: 26.5, fmt: 'ARW', lat: 64.9417, lon: -23.3058 },
    { id: 'b2', name: 'DSC01934_Reynisfjara.ARW', title: 'Reynisfjara Black Sand', make: 'Sony', camera: 'Sony α7 IV', lens: 'FE 24-105mm F4 G', f: 11, ss: '0.5s', iso: 100, fl: 24, date: '2026-02-13T11:40', place: 'Vík', country: 'Iceland', rating: 4, flag: false, tags: ['iceland', 'ocean', 'landscape'], w: 16, h: 9, scene: 'blackBeach', mb: 25.9, fmt: 'ARW', lat: 63.4044, lon: -19.0447 },
    { id: 'b3', name: 'DSC_7741_Skogafoss.NEF', title: 'Skógafoss', make: 'Nikon', camera: 'Nikon Z8', lens: 'Z 24-120mm f/4 S', f: 16, ss: '1/2s', iso: 64, fl: 35, date: '2026-02-13T15:02', place: 'Skógar', country: 'Iceland', rating: 4, flag: false, tags: ['iceland', 'landscape', 'waterfall'], w: 2, h: 3, scene: 'waterfall', mb: 45.7, fmt: 'NEF', lat: 63.5321, lon: -19.5114 },
    { id: 'b4', name: 'DSC_7802_Jokulsarlon.NEF', title: 'Jökulsárlón Ice Lagoon', make: 'Nikon', camera: 'Nikon Z8', lens: 'Z 24-120mm f/4 S', f: 8, ss: '1/320', iso: 200, fl: 50, date: '2026-02-14T10:30', place: 'Jökulsárlón', country: 'Iceland', rating: 3, flag: false, tags: ['iceland', 'landscape'], w: 3, h: 2, scene: 'ice', mb: 44.2, fmt: 'NEF', lat: 64.0784, lon: -16.2306 },
    { id: 'b5', name: 'IMG_3381_Reykjavik_Harbour.HEIC', title: 'Reykjavík Harbour Dusk', make: 'Apple', camera: 'iPhone 15 Pro', lens: 'Main 24mm ƒ1.78', f: 1.8, ss: '1/120', iso: 250, fl: 24, date: '2026-02-15T17:12', place: 'Reykjavík', country: 'Iceland', rating: 2, flag: false, tags: ['iceland', 'city'], w: 4, h: 3, scene: 'harbor', mb: 2.8, fmt: 'HEIC', lat: 64.1505, lon: -21.9406 },
    { id: 'b6', name: 'DSC_5520_Thar_Dunes.NEF', title: 'Thar Desert Dunes', make: 'Nikon', camera: 'Nikon Z8', lens: 'Z 70-200mm f/2.8 S', f: 8, ss: '1/1000', iso: 100, fl: 120, date: '2026-01-08T17:20', place: 'Jaisalmer', country: 'India', rating: 4, flag: false, tags: ['travel', 'india', 'landscape'], w: 16, h: 9, scene: 'dunes', mb: 47.3, fmt: 'NEF', lat: 26.9157, lon: 70.9083 },
    { id: 'b7', name: 'DSCF1044_Hawa_Mahal.RAF', title: 'Hawa Mahal Facade', make: 'Fujifilm', camera: 'Fujifilm X-T5', lens: 'XF 16-55mm F2.8', f: 8, ss: '1/400', iso: 125, fl: 16, date: '2026-01-11T09:45', place: 'Jaipur', country: 'India', rating: 4, flag: true, tags: ['travel', 'india', 'architecture'], w: 4, h: 5, scene: 'hawa', mb: 30.6, fmt: 'RAF', lat: 26.9239, lon: 75.8267 },
    { id: 'b8', name: 'IMG_9020_Garden_Peonies.CR3', title: 'Garden Peonies', make: 'Canon', camera: 'Canon EOS R5', lens: 'RF 100mm F2.8L Macro', f: 2.8, ss: '1/250', iso: 200, fl: 100, date: '2026-04-19T07:58', place: 'Home', country: '', rating: 3, flag: false, tags: ['macro', 'garden'], w: 1, h: 1, scene: 'peonies', mb: 36.4, fmt: 'CR3', lat: null, lon: null },
    { id: 'b9', name: 'DSC_6012_Biei_Snowfield.NEF', title: 'Biei Snowfield', make: 'Nikon', camera: 'Nikon Z8', lens: 'Z 24-120mm f/4 S', f: 11, ss: '1/800', iso: 100, fl: 70, date: '2026-01-29T13:05', place: 'Biei', country: 'Japan', rating: 3, flag: false, tags: ['japan', 'landscape', 'winter'], w: 3, h: 2, scene: 'snow', mb: 43.9, fmt: 'NEF', lat: 43.588, lon: 142.4669 },
  ]

  const COLLECTIONS = [
    { name: 'Japan 2026', ids: ['a1', 'a2', 'a3', 'a4', 'a5', 'a6', 'a7', 'a8', 'a9'] },
    { name: 'Iceland Winter', ids: ['b1', 'b2', 'b3', 'b4', 'b5'] },
    { name: 'Portfolio', ids: ['a1', 'a3', 'a7', 'b1', 'b7'] },
  ]

  // ---------------------------------------------------------------- procedural "photographs"
  const SCENES = {
    sunsetCity: { sky: ['#2a1b4a', '#ff8a4c'], sun: { x: 0.7, y: 0.6, r: 0.07, c: '#ffe0a8' }, city: { c: '#1a1024', lit: ['#ffcf7a'], h: 0.42 } },
    cityNight: { sky: ['#04060d', '#1d2547'], city: { c: '#070a14', lit: ['#7fd3ff', '#ff5fa2', '#ffd36b'], h: 0.62 } },
    fuji: { sky: ['#f2a98f', '#fde6cc'], peak: { c: '#5b6f9e', snow: '#f4f6fb' }, layers: [{ c: '#2f3b58', y: 0.86, a: 0.03 }] },
    bamboo: { sky: ['#d6e8b8', '#7aa352'], stripes: { c: ['#2f4f1f', '#3e6b2a', '#5a8a3a', '#24401a'], n: 26, min: 0.15, max: 0.45 } },
    gates: { sky: ['#2a0d08', '#9b2a17'], stripes: { c: ['#e0491f', '#b8331a', '#f26a33', '#3a120b'], n: 11, min: 0.45, max: 0.9 } },
    autumn: { sky: ['#2e160b', '#9c3f18'], bokeh: { c: ['#ff8a3d', '#d9452b', '#f5c04a', '#ffb067'], n: 40 } },
    portrait: { sky: ['#1f2b1d', '#5f7346'], bokeh: { c: ['#c8d98a', '#f2e6a0', '#8fb36a'], n: 28 }, subject: true },
    ocean: { sky: ['#4fbfe0', '#c4f1ff'], water: ['#1fb3c9', '#0b6f8f'], y: 0.52 },
    aurora: { sky: ['#01040c', '#0a1a30'], stars: 90, aurora: ['#4dffb0', '#8a6bff'], layers: [{ c: '#03070d', y: 0.8, a: 0.09 }] },
    blackBeach: { sky: ['#8b97a3', '#d2d9df'], water: ['#59646e', '#1c2126'], y: 0.58, stacks: '#16191c' },
    waterfall: { sky: ['#9fb7a0', '#e1ebdc'], layers: [{ c: '#3f5a3a', y: 0.22, a: 0.06 }], fall: true },
    ice: { sky: ['#a9cde6', '#eef7fc'], water: ['#2f6585', '#16384d'], y: 0.6, floes: true },
    harbor: { sky: ['#5b6ea8', '#f7a072'], water: ['#43507d', '#1e2540'], y: 0.7, city: { c: '#2a2f4a', lit: ['#ffd27a'], h: 0.22, palette: ['#c9473f', '#e8a23c', '#4fa8c4', '#e9e4da'] } },
    dunes: { sky: ['#f3b766', '#fde8bf'], sun: { x: 0.25, y: 0.33, r: 0.05, c: '#fff6e0' }, layers: [{ c: '#e09a4a', y: 0.6, a: 0.06, smooth: true }, { c: '#c97a2c', y: 0.72, a: 0.06, smooth: true }, { c: '#a95d1c', y: 0.86, a: 0.04, smooth: true }] },
    hawa: { sky: ['#6fb0e6', '#d3e9f8'], facade: { c: '#e8826a', win: '#a9493a' } },
    peonies: { sky: ['#2c1220', '#b44f7a'], bokeh: { c: ['#ffb3cf', '#ff7aa8', '#ffe1ec', '#e0457f'], n: 34 } },
    snow: { sky: ['#c9d8e8', '#f6f9fc'], layers: [{ c: '#dbe5ef', y: 0.55, a: 0.08, smooth: true }, { c: '#eef3f8', y: 0.7, a: 0.05, smooth: true }, { c: '#ffffff', y: 0.84, a: 0.03, smooth: true }], trees: true },
  }

  function seeded(seed) {
    let s = 7
    for (const ch of seed) s = (s * 31 + ch.charCodeAt(0)) >>> 0
    return () => {
      s = (s * 1664525 + 1013904223) >>> 0
      return s / 4294967296
    }
  }

  const n1 = (v) => Math.round(v * 10) / 10

  function sceneSvg(p) {
    const W = 600
    const H = Math.round((600 * p.h) / p.w)
    const S = SCENES[p.scene]
    const r = seeded(p.id)
    let o = ''
    o += `<defs><linearGradient id="s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${S.sky[0]}"/><stop offset="1" stop-color="${S.sky[1]}"/></linearGradient>`
    if (S.water) o += `<linearGradient id="w" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${S.water[0]}"/><stop offset="1" stop-color="${S.water[1]}"/></linearGradient>`
    o += `<radialGradient id="v" cx=".5" cy=".5" r=".75"><stop offset=".55" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".45"/></radialGradient>`
    o += `<filter id="b"><feGaussianBlur stdDeviation="5"/></filter><filter id="b2"><feGaussianBlur stdDeviation="18"/></filter></defs>`
    o += `<rect width="${W}" height="${H}" fill="url(#s)"/>`

    if (S.stars) for (let i = 0; i < S.stars; i++) o += `<circle cx="${n1(r() * W)}" cy="${n1(r() * H * 0.7)}" r="${n1(r() * 1.3 + 0.3)}" fill="#fff" opacity="${n1(r() * 0.8 + 0.2)}"/>`
    if (S.aurora) {
      S.aurora.forEach((c, i) => {
        let d = `M0 ${n1(H * (0.32 + i * 0.1))}`
        for (let x = 0; x < W; x += 75) d += ` Q${x + 37} ${n1(H * (0.12 + r() * 0.3 + i * 0.08))} ${x + 75} ${n1(H * (0.3 + r() * 0.12 + i * 0.08))}`
        o += `<path d="${d}" stroke="${c}" stroke-width="${46 - i * 14}" fill="none" opacity=".6" filter="url(#b2)"/>`
      })
    }
    if (S.sun) {
      const s = S.sun
      o += `<circle cx="${s.x * W}" cy="${s.y * H}" r="${s.r * W * 2.6}" fill="${s.c}" opacity=".3" filter="url(#b2)"/><circle cx="${s.x * W}" cy="${s.y * H}" r="${s.r * W}" fill="${s.c}"/>`
    }
    if (S.peak) {
      const k = S.peak
      o += `<polygon points="${W * 0.06},${H * 0.88} ${W * 0.45},${H * 0.3} ${W * 0.55},${H * 0.3} ${W * 0.94},${H * 0.88}" fill="${k.c}"/>`
      o += `<polygon points="${W * 0.37},${H * 0.42} ${W * 0.45},${H * 0.3} ${W * 0.55},${H * 0.3} ${W * 0.63},${H * 0.42} ${W * 0.58},${H * 0.39} ${W * 0.53},${H * 0.44} ${W * 0.48},${H * 0.39} ${W * 0.42},${H * 0.44}" fill="${k.snow}"/>`
    }
    if (S.stripes) {
      const st = S.stripes
      for (let i = 0; i < st.n; i++) {
        const bw = (W / st.n) * (st.min + r() * (st.max - st.min))
        o += `<rect x="${n1(r() * W)}" y="0" width="${n1(bw)}" height="${H}" fill="${st.c[i % st.c.length]}" opacity="${n1(0.75 + r() * 0.25)}"/>`
      }
      if (p.scene === 'gates') for (let i = 0; i < 5; i++) o += `<rect x="0" y="${n1(H * (0.08 + i * 0.2))}" width="${W}" height="${n1(H * 0.03)}" fill="#2a0b06" opacity=".55"/>`
    }
    ;(S.layers || []).forEach((L) => {
      const n = L.smooth ? 6 : 16
      const ys = Array.from({ length: n + 1 }, () => H * (L.y - r() * L.a * 2 + L.a))
      let d = `M0 ${H} L0 ${n1(ys[0])}`
      for (let i = 1; i <= n; i++) {
        const x = (i / n) * W
        if (L.smooth) d += ` Q${n1(x - W / n / 2)} ${n1(Math.min(ys[i - 1], ys[i]) - H * 0.05)} ${n1(x)} ${n1(ys[i])}`
        else d += ` L${n1(x)} ${n1(ys[i])}`
      }
      o += `<path d="${d} L${W} ${H} Z" fill="${L.c}"/>`
    })
    if (S.trees) for (let i = 0; i < 7; i++) {
      const x = W * (0.15 + r() * 0.7), y = H * (0.6 + r() * 0.1), t = 14 + r() * 14
      o += `<polygon points="${n1(x)},${n1(y - t * 2)} ${n1(x - t / 2)},${n1(y)} ${n1(x + t / 2)},${n1(y)}" fill="#3d4f45" opacity=".8"/>`
    }
    if (S.fall) {
      o += `<rect x="${W * 0.42}" y="${H * 0.2}" width="${W * 0.16}" height="${H * 0.8}" fill="#f6fbff" opacity=".9" filter="url(#b)"/>`
      o += `<ellipse cx="${W / 2}" cy="${H * 0.95}" rx="${W * 0.45}" ry="${H * 0.12}" fill="#fff" opacity=".7" filter="url(#b2)"/>`
      o += `<rect x="0" y="${H * 0.25}" width="${W * 0.4}" height="${H * 0.75}" fill="#2f4a2b"/><rect x="${W * 0.6}" y="${H * 0.25}" width="${W * 0.4}" height="${H * 0.75}" fill="#34502f"/>`
    }
    if (S.water) {
      const wy = H * S.y
      o += `<rect y="${n1(wy)}" width="${W}" height="${n1(H - wy)}" fill="url(#w)"/>`
      for (let i = 0; i < 14; i++) o += `<rect x="${n1(r() * W)}" y="${n1(wy + r() * (H - wy))}" width="${n1(30 + r() * 120)}" height="1.5" fill="#fff" opacity="${n1(0.1 + r() * 0.25)}"/>`
      if (S.stacks) o += `<polygon points="${W * 0.62},${n1(wy + 4)} ${W * 0.66},${n1(wy - H * 0.3)} ${W * 0.7},${n1(wy - H * 0.26)} ${W * 0.72},${n1(wy + 4)}" fill="${S.stacks}"/><polygon points="${W * 0.76},${n1(wy + 4)} ${W * 0.79},${n1(wy - H * 0.18)} ${W * 0.82},${n1(wy + 4)}" fill="${S.stacks}"/>`
      if (S.floes) for (let i = 0; i < 6; i++) {
        const x = r() * W, y = wy + 10 + r() * (H - wy - 30), s = 20 + r() * 50
        o += `<polygon points="${n1(x)},${n1(y)} ${n1(x + s * 0.4)},${n1(y - s * 0.5)} ${n1(x + s)},${n1(y - s * 0.3)} ${n1(x + s * 1.2)},${n1(y)}" fill="${i % 2 ? '#e8f6ff' : '#9fd8f0'}"/>`
      }
    }
    if (S.city) {
      const C = S.city
      const base = S.water ? H * S.y : H
      let x = -10
      while (x < W) {
        const bw = 22 + r() * 48
        const bh = H * C.h * (0.35 + r() * 0.8)
        const fill = C.palette ? C.palette[Math.floor(r() * C.palette.length)] : C.c
        o += `<rect x="${n1(x)}" y="${n1(base - bh)}" width="${n1(bw)}" height="${n1(bh)}" fill="${fill}"/>`
        for (let wy = base - bh + 6; wy < base - 6; wy += 9) for (let wx = x + 4; wx < x + bw - 6; wx += 8)
          if (r() > 0.62) o += `<rect x="${n1(wx)}" y="${n1(wy)}" width="3.5" height="4" fill="${C.lit[Math.floor(r() * C.lit.length)]}" opacity=".9"/>`
        x += bw + 2
      }
      if (p.scene === 'sunsetCity') o += `<polygon points="${W * 0.36},${base} ${W * 0.4},${H * 0.12} ${W * 0.44},${base}" fill="#ff5a2a"/><rect x="${W * 0.395}" y="${H * 0.06}" width="3" height="${H * 0.08}" fill="#ff5a2a"/>`
    }
    if (S.facade) {
      const F = S.facade
      o += `<rect x="${W * 0.05}" y="${H * 0.14}" width="${W * 0.9}" height="${H * 0.86}" fill="${F.c}"/>`
      for (let row = 0; row < 7; row++) for (let col = 0; col < 9; col++) {
        const cx = W * (0.1 + col * 0.1), cy = H * (0.2 + row * 0.115)
        o += `<rect x="${n1(cx - 9)}" y="${n1(cy)}" width="18" height="${n1(H * 0.06)}" rx="9" fill="${F.win}"/>`
      }
      for (let i = 0; i < 7; i++) o += `<circle cx="${W * (0.12 + i * 0.13)}" cy="${H * 0.14}" r="${W * 0.035}" fill="${F.c}"/>`
    }
    if (S.bokeh) {
      const B = S.bokeh
      for (let i = 0; i < B.n; i++) o += `<circle cx="${n1(r() * W)}" cy="${n1(r() * H)}" r="${n1(10 + r() * 55)}" fill="${B.c[i % B.c.length]}" opacity="${n1(0.2 + r() * 0.5)}"${i % 3 ? ' filter="url(#b)"' : ''}/>`
    }
    if (S.subject) {
      o += `<ellipse cx="${W / 2}" cy="${H * 1.02}" rx="${W * 0.32}" ry="${H * 0.3}" fill="#2d2622"/>`
      o += `<rect x="${W * 0.46}" y="${H * 0.55}" width="${W * 0.08}" height="${H * 0.2}" fill="#c08d70"/>`
      o += `<ellipse cx="${W / 2}" cy="${H * 0.44}" rx="${W * 0.13}" ry="${H * 0.15}" fill="#d9a585"/>`
      o += `<path d="M${W * 0.36} ${H * 0.44} Q${W * 0.38} ${H * 0.22} ${W / 2} ${H * 0.25} Q${W * 0.63} ${H * 0.22} ${W * 0.64} ${H * 0.46} Q${W * 0.6} ${H * 0.32} ${W / 2} ${H * 0.31} Q${W * 0.4} ${H * 0.32} ${W * 0.36} ${H * 0.44} Z" fill="#241a15"/>`
    }
    o += `<rect width="${W}" height="${H}" fill="url(#v)"/>`
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">${o}</svg>`
  }

  const cache = new Map()
  /** A data: URI for the photo's stand-in image. In the real app this is /api/photos/{hash}/thumbnail. */
  function src(p) {
    if (!cache.has(p.id)) cache.set(p.id, 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(sceneSvg(p)))
    return cache.get(p.id)
  }

  // ---------------------------------------------------------------- icons (lucide paths)
  const I = {
    grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/>',
    calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    map: '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
    kanban: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 7v7M12 7v4M16 7v9"/>',
    chart: '<path d="M3 3v18h18"/><path d="M18 17V9M13 17V5M8 17v-3"/>',
    search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    sliders: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
    eyeOff: '<path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.53 13.53 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><path d="m2 2 20 20"/>',
    flag: '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><path d="M4 22v-7"/>',
    star: '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5M12 15V3"/>',
    folderPlus: '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/><path d="M12 10v6M9 13h6"/>',
    folder: '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    copy: '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    chevronDown: '<path d="m6 9 6 6 6-6"/>',
    chevronLeft: '<path d="m15 18-6-6 6-6"/>',
    chevronRight: '<path d="m9 18 6-6-6-6"/>',
    camera: '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/><circle cx="12" cy="13" r="3"/>',
    tag: '<path d="M12.59 2.59A2 2 0 0 0 11.17 2H4a2 2 0 0 0-2 2v7.17a2 2 0 0 0 .59 1.42l8.7 8.7a2.43 2.43 0 0 0 3.42 0l6.58-6.58a2.43 2.43 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
    table: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
    moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    arrowLeft: '<path d="m12 19-7-7 7-7M19 12H5"/>',
    aperture: '<circle cx="12" cy="12" r="10"/><path d="m14.31 8 5.74 9.94M9.69 8h11.48M7.38 12l5.74-9.94M9.69 16 3.95 6.06M14.31 16H2.83M16.62 12l-5.74 9.94"/>',
    image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.09-3.09a2 2 0 0 0-2.82 0L6 21"/>',
    plus: '<path d="M5 12h14M12 5v14"/>',
    maximize: '<path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3"/>',
    panelLeft: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18"/>',
    panelRight: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M15 3v18"/>',
    database: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/>',
    command: '<path d="M15 6v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3V6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3"/>',
    sparkles: '<path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/>',
    layers: '<path d="m12 2 10 5-10 5L2 7Z"/><path d="m2 17 10 5 10-5M2 12l10 5 10-5"/>',
  }

  function icon(name, size = 16, sw = 1.75) {
    return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${I[name]}</svg>`
  }

  // ---------------------------------------------------------------- helpers
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  function fmtDate(iso, withTime = true) {
    const [d, t] = iso.split('T')
    const [y, m, day] = d.split('-').map(Number)
    return `${day} ${MONTHS[m - 1]} ${y}${withTime ? ' · ' + t : ''}`
  }
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
  /** A fake but stable SHA-256-looking hash, for display only. */
  function hash(p) {
    const r = seeded(p.name)
    let h = ''
    for (let i = 0; i < 64; i++) h += '0123456789abcdef'[Math.floor(r() * 16)]
    return h
  }
  function countBy(list, key) {
    const m = new Map()
    for (const p of list) for (const k of [].concat(key(p))) m.set(k, (m.get(k) || 0) + 1)
    return [...m.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])))
  }

  window.PMO = { PHOTOS, COLLECTIONS, src, icon, fmtDate, esc, hash, countBy, seeded }
})()
