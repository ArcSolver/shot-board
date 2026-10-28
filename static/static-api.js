// Static board viewer: answers the app's /api calls from files the build
// produced with the real server, so nothing here talks to a GPU or a backend.
// Picks and reviews stay in this browser (localStorage). With the saved picks
// and reviews, the storyboard and ZIP are the server's own files; after a
// change they are assembled here from the original stills and the pieces of
// the app's manifest the build serialized.
(() => {
  'use strict';
  const KEY = 'shotboard-static:v7:';
  const GPU_ONLY = 'To render new takes, run Shot Board locally with your own ComfyUI.';
  const realFetch = window.fetch.bind(window);
  const files = new Map();
  const boards = new Map();
  let sizedImages = {};

  class HttpError extends Error { constructor(status, message) { super(message); this.status = status; } }
  const json = (data, status = 200) => new Response(JSON.stringify(data), {status, headers: {'Content-Type': 'application/json'}});
  const boardPath = (id) => `data/boards/${encodeURIComponent(id)}`;
  const imageURL = (id, file) => `${boardPath(id)}/images/${encodeURIComponent(file)}`;

  async function load(path) {
    if (!files.has(path)) {
      files.set(path, realFetch(path).then(r => { if (!r.ok) throw new HttpError(404, 'Not found'); return r.json(); }));
    }
    try { return structuredClone(await files.get(path)); } catch (error) { files.delete(path); throw error; }
  }
  const examples = () => load('data/examples.json');
  const shipped = (id) => load(boardPath(id) + '.json');
  // Sized WebP copies of every still, made by the build; the app asks for them through SB.sized.
  const imagesReady = load('data/images.json').then(map => { sizedImages = map; }).catch(() => {});

  function save(board) {
    boards.set(board.id, board);
    try { localStorage.setItem(KEY + board.id, JSON.stringify(board)); } catch { /* private mode or quota: keep it in memory */ }
  }
  function restore() {
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (!key?.startsWith(KEY)) continue;
      try { const board = JSON.parse(localStorage.getItem(key)); boards.set(board.id, board); } catch { localStorage.removeItem(key); }
    }
  }
  async function boardFor(id) {
    if (boards.has(id)) return boards.get(id);
    if ((await examples()).some(ex => ex.board.id === id)) { const board = await shipped(id); save(board); return board; }
    throw new HttpError(404, 'Board not found');
  }
  function shotFor(board, sid) {
    const shot = board.shots.find(s => s.id === sid);
    if (!shot) throw new HttpError(404, 'Shot not found');
    return shot;
  }
  const picks = (board) => JSON.stringify(board.shots.map(s => s.picked));
  const reviews = (board) => JSON.stringify(board.review || []);
  const samePicks = async (board) => picks(board) === picks(await shipped(board.id));
  const saved = async (board) => await samePicks(board) && reviews(board) === reviews(await shipped(board.id));

  // ---- Original stills, checked against the board's SHA-256 like the server's export ----
  const originals = new Map();
  const hex = (buffer) => [...new Uint8Array(buffer)].map(b => b.toString(16).padStart(2, '0')).join('');
  async function sha256(data) {
    if (!crypto.subtle) throw new Error('Exporting here needs an https page.');
    return hex(await crypto.subtle.digest('SHA-256', data));
  }
  async function original(url, sha) {
    if (!originals.has(url)) originals.set(url, realFetch(url).then(r => { if (!r.ok) throw new Error('A picked image could not be loaded.'); return r.arrayBuffer(); }));
    try {
      const data = await originals.get(url);
      if (await sha256(data) !== sha) throw new Error('A picked image changed; export stopped.');
      return new Uint8Array(data);
    } catch (error) { originals.delete(url); throw error; }
  }
  function selected(board) {
    return board.shots.map(shot => {
      const take = shot.takes.find(t => t.id === shot.picked && t.status === 'succeeded');
      if (!take) throw new Error('Pick one completed take for every shot before exporting.');
      return {shot, take};
    });
  }

  // ---- Storyboard: the layout of shotboard/storyboard.py, drawn on a canvas from the originals ----
  const LAYOUTS = {landscape: [1600, 900], portrait: [1080, 1350]};
  const FONT = '"Helvetica Neue", Helvetica, Arial, sans-serif';
  function wrap(ctx, text, width) {
    const lines = [];
    let line = '';
    for (const char of text) {
      if (char === '\n' || ctx.measureText(line + char).width > width) { lines.push(line); line = char === '\n' ? '' : char; } else line += char;
    }
    return [...lines, line];
  }
  async function storyboardPng(board, layout) {
    if (!LAYOUTS[layout]) throw new Error('Choose landscape or portrait.');
    const chosen = selected(board);
    const stills = await Promise.all(chosen.map(({take}) => original(imageURL(board.id, take.image), take.image_sha256)
      .then(data => createImageBitmap(new Blob([data], {type: 'image/png'})))));
    const [width, height] = LAYOUTS[layout];
    const canvas = document.createElement('canvas');
    canvas.width = width; canvas.height = height;
    const ctx = canvas.getContext('2d');
    const font = (size) => { ctx.font = `${size}px ${FONT}`; return size; };
    ctx.textBaseline = 'top'; ctx.imageSmoothingQuality = 'high';
    ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, width, height);
    const [margin, gap] = layout === 'landscape' ? [42, 20] : [34, 18];
    font(21); ctx.fillStyle = '#0066cc'; ctx.fillText('SHOT BOARD', margin, 26);
    const scene = board.config.scene.split(/\s+/).filter(Boolean).join(' ');
    let size = font(24), lines = wrap(ctx, scene, width - 2 * margin);
    while (lines.length * (size + 6) > 180 && size > 6) { size = font(size - 1); lines = wrap(ctx, scene, width - 2 * margin); }
    let y = 65;
    ctx.fillStyle = '#1d1d1f';
    for (const line of lines) { ctx.fillText(line, margin, y); y += size + 6; }
    const top = y + 20, bottom = height - 63, cols = layout === 'landscape' ? 3 : 2, rows = Math.ceil(chosen.length / cols);
    const cellW = Math.floor((width - 2 * margin - gap * (cols - 1)) / cols), cellH = Math.floor((bottom - top - gap * (rows - 1)) / rows);
    if (cellH < 70) throw new Error('Scene line is too long for this storyboard layout. Shorten the scene before exporting.');
    chosen.forEach(({shot}, i) => {
      const x = margin + (i % cols) * (cellW + gap), cy = top + Math.floor(i / cols) * (cellH + gap);
      ctx.fillStyle = '#f5f5f7'; ctx.fillRect(x, cy, cellW + 1, cellH + 1);
      const imageH = cellH - 43, still = stills[i], scale = Math.min(cellW / still.width, imageH / still.height, 1);
      const w = Math.round(still.width * scale), h = Math.round(still.height * scale);
      ctx.drawImage(still, x + Math.floor((cellW - w) / 2), cy + Math.floor((imageH - h) / 2), w, h);
      const label = `${String(i + 1).padStart(2, '0')}  ${shot.title}`;
      let labelSize = font(16), labelLines = wrap(ctx, label, cellW - 90);
      while (labelLines.length > 2 && labelSize > 6) { labelSize = font(labelSize - 1); labelLines = wrap(ctx, label, cellW - 90); }
      ctx.fillStyle = '#1d1d1f';
      labelLines.forEach((line, index) => ctx.fillText(line, x + 12, cy + imageH + 5 + index * 18));
    });
    stills.forEach(still => still.close());
    return new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('The storyboard could not be drawn.')), 'image/png'));
  }

  // ---- ZIP: the members and manifest of core.export_board, stored uncompressed ----
  const CRC = new Uint32Array(256).map((_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c >>> 0; });
  function crc32(data) { let c = 0xffffffff; for (let i = 0; i < data.length; i++) c = CRC[(c ^ data[i]) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; }
  function zip(entries) {
    const now = new Date(), utf8 = new TextEncoder();
    const time = (now.getHours() << 11) | (now.getMinutes() << 5) | (now.getSeconds() >> 1);
    const date = ((now.getFullYear() - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate();
    const body = [], central = [];
    let offset = 0;
    for (const {name, data} of entries) {
      const file = utf8.encode(name), crc = crc32(data);
      const local = new DataView(new ArrayBuffer(30)), record = new DataView(new ArrayBuffer(46));
      [[0, 0x04034b50, 4], [4, 20, 2], [6, 0x0800, 2], [10, time, 2], [12, date, 2], [14, crc, 4], [18, data.length, 4], [22, data.length, 4], [26, file.length, 2]]
        .forEach(([at, value, bytes]) => bytes === 4 ? local.setUint32(at, value, true) : local.setUint16(at, value, true));
      [[0, 0x02014b50, 4], [4, 20, 2], [6, 20, 2], [8, 0x0800, 2], [12, time, 2], [14, date, 2], [16, crc, 4], [20, data.length, 4], [24, data.length, 4], [28, file.length, 2], [42, offset, 4]]
        .forEach(([at, value, bytes]) => bytes === 4 ? record.setUint32(at, value, true) : record.setUint16(at, value, true));
      body.push(local, file, data); central.push(record, file);
      offset += 30 + file.length + data.length;
    }
    const size = central.reduce((total, part) => total + part.byteLength, 0), end = new DataView(new ArrayBuffer(22));
    end.setUint32(0, 0x06054b50, true); end.setUint16(8, entries.length, true); end.setUint16(10, entries.length, true);
    end.setUint32(12, size, true); end.setUint32(16, offset, true);
    return new Blob([...body, ...central, end], {type: 'application/zip'});
  }
  // json.dumps(value, indent=2) as the app writes it. Values with floats come pre-serialized from the build (Raw).
  class Raw { constructor(text) { this.text = text; } }
  const ascii = (text) => text.replace(/[\u007f-￿]/g, c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
  function py(value, depth = 0) {
    const pad = (n) => '\n' + '  '.repeat(n);
    if (value instanceof Raw) return value.text.replaceAll('\n', pad(depth));
    if (Array.isArray(value)) return value.length ? `[${value.map(v => pad(depth + 1) + py(v, depth + 1)).join(',')}${pad(depth)}]` : '[]';
    if (value && typeof value === 'object') {
      const keys = Object.keys(value);
      return keys.length ? `{${keys.map(k => `${pad(depth + 1)}${ascii(JSON.stringify(k))}: ${py(value[k], depth + 1)}`).join(',')}${pad(depth)}}` : '{}';
    }
    if (typeof value === 'number' && !Number.isInteger(value)) throw new Error('Export stopped: unexpected number in the manifest.');
    return ascii(JSON.stringify(value));
  }
  async function zipBlob(board) {
    const parts = await load(`${boardPath(board.id)}/export.json`), utf8 = new TextEncoder();
    const entries = [], written = new Set(), shots = [];
    for (const {shot, take} of selected(board)) {
      const part = parts.takes[`${shot.id}/${take.id}`];
      if (!part) throw new Error('This take cannot be exported here. Run Shot Board locally to export it.');
      entries.push({name: `stills/${shot.id}.png`, data: await original(imageURL(board.id, take.image), take.image_sha256)});
      const reference = take.reference;
      if (reference && !written.has(reference.image)) {
        entries.push({name: reference.image, data: await original(parts.references[reference.image], reference.image_sha256)});
        written.add(reference.image);
      }
      if (part.workflow !== null) entries.push({name: `workflows/${shot.id}.api.json`, data: utf8.encode(part.workflow)});
      if (part.submitted !== null) entries.push({name: `workflows/${shot.id}.submitted.api.json`, data: utf8.encode(part.submitted)});
      const review = (board.review || []).find(r => r.shot === shot.id && r.take === take.id) || {shot: shot.id, take: take.id, verdict: 'pending', note: ''};
      shots.push(new Raw(part.entry.replace('"@@REVIEW@@"', () => py(review, 1))));
    }
    // With the saved picks the server's storyboards still apply (only reviews changed); otherwise draw them.
    const storyboards = [], savedPicks = await samePicks(board);
    for (const [layout, [width, height]] of Object.entries(LAYOUTS)) {
      const file = `storyboard-${layout}.png`;
      const blob = savedPicks ? await realFetch(`${boardPath(board.id)}/${file}`).then(r => { if (!r.ok) throw new Error('The storyboard could not be loaded.'); return r.blob(); }) : await storyboardPng(board, layout);
      const data = new Uint8Array(await blob.arrayBuffer());
      entries.push({name: file, data});
      storyboards.push({file, width, height, sha256: await sha256(data), layout_version: 1, fit: 'contain',
        selections: board.shots.map(s => ({shot_id: s.id, take_id: s.picked}))});
    }
    const manifest = parts.manifest
      .replace('"@@REVIEW_LIST@@"', () => py(board.review || [], 1))
      .replace('"@@STORYBOARDS@@"', () => py(storyboards, 1))
      .replace('"@@SHOTS@@"', () => py(shots, 1));
    entries.push({name: 'manifest.json', data: utf8.encode(manifest)});
    return zip(entries);
  }
  function download(href, name) {
    const link = document.createElement('a');
    link.href = href; link.download = name;
    document.body.append(link); link.click(); link.remove();
  }

  async function route(method, url, body) {
    await imagesReady;
    const [path, query] = url.split('?');
    const p = path.split('/').filter(Boolean).slice(1);
    const is = (m, ...pattern) => m === method && p.length === pattern.length && pattern.every((x, i) => x === '*' || x === p[i]);
    if (is('GET', 'config')) return json(await load('data/config.json'));
    if (is('GET', 'health')) return json({proxy_ready: false, reference_components_present: false, checkpoint_present: false});
    if (is('GET', 'examples')) return json(await examples());
    if (is('POST', 'examples', '*', 'open')) {
      const example = (await examples()).find(ex => ex.slug === p[1]);
      if (!example) throw new HttpError(404, 'Example not found');
      await boardFor(example.board.id);
      return json({id: example.board.id});
    }
    if (is('GET', 'boards')) return json([...boards.values()].reverse().map(b => ({id: b.id, title: b.title})));
    if (is('POST', 'boards')) throw new HttpError(409, GPU_ONLY);
    if (p[0] !== 'boards' || !p[1]) throw new HttpError(404, 'Not found');
    const board = await boardFor(p[1]);
    if (is('GET', 'boards', '*')) return json(structuredClone(board));
    if (is('POST', 'boards', '*', 'cancel')) return json({ok: true});
    if (is('POST', 'boards', '*', 'shots', '*', 'pick')) {
      const shot = shotFor(board, p[3]), continuity = board.continuity || {}, hero = continuity.hero || {};
      if (continuity.enabled && hero.shot_id === shot.id && hero.take_id !== body?.take_id) throw new HttpError(409, 'Turn off Keep continuity before changing the hero pick.');
      if (!shot.takes.some(t => t.id === body?.take_id && t.status === 'succeeded')) throw new HttpError(409, 'Pick a completed take');
      shot.picked = body.take_id; save(board);
      return json({ok: true});
    }
    if (is('PUT', 'boards', '*', 'shots', '*', 'takes', '*', 'review')) {
      const shot = shotFor(board, p[3]);
      if (!shot.takes.some(t => t.id === p[5])) throw new HttpError(404, 'Take not found');
      if (!['pass', 'fail', 'pending'].includes(body?.verdict) || typeof (body.note ?? '') !== 'string' || (body.note ?? '').length > 400) throw new HttpError(422, 'Please check your inputs.');
      const list = board.review ||= [];
      let review = list.find(r => r.shot === shot.id && r.take === p[5]);
      if (!review) { review = {shot: shot.id, take: p[5]}; list.push(review); }
      Object.assign(review, {verdict: body.verdict, note: body.note ?? ''}); save(board);
      return json(structuredClone(review));
    }
    if (is('GET', 'boards', '*', 'storyboard')) {
      const layout = new URLSearchParams(query).get('layout') || 'landscape';
      if (!LAYOUTS[layout]) throw new HttpError(422, 'Choose landscape or portrait.');
      // Saved picks: show a WebP copy of the server's storyboard and download the PNG itself.
      if (await samePicks(board)) {
        const response = await realFetch(`${boardPath(board.id)}/storyboard-${layout}.webp`);
        response.download = `${boardPath(board.id)}/storyboard-${layout}.png`;
        return response;
      }
      try { return new Response(await storyboardPng(board, layout), {headers: {'Content-Type': 'image/png'}}); } catch (error) { throw new HttpError(409, error.message); }
    }
    if (['PATCH', 'POST'].includes(method)) throw new HttpError(409, GPU_ONLY);
    throw new HttpError(404, 'Not found');
  }

  window.fetch = (input, init = {}) => {
    const url = typeof input === 'string' ? input : input.url;
    if (!url.startsWith('/api/')) return realFetch(input, init);
    if (/\/shots\/[^/]+\/import$/.test(url)) return Promise.resolve(json({detail: 'To import a reference, run Shot Board locally.'}, 409));
    let body;
    try { body = init.body ? JSON.parse(init.body) : undefined; } catch { return Promise.resolve(json({detail: 'Please check your inputs.'}, 422)); }
    return route((init.method || 'GET').toUpperCase(), url, body)
      .catch(error => json({detail: error instanceof HttpError ? error.message : 'Request failed'}, error.status || 500));
  };

  let exporting = false;
  window.SB = {
    imageURL,
    sized(url) {
      const entry = sizedImages[url];
      return entry && {src: entry.src, srcset: entry.tiers.map(([width, file]) => `${file} ${width}w`).join(', '), width: entry.width, height: entry.height};
    },
    storyboardDownload: (response, objectUrl) => response.download || objectUrl,
    health() {
      const el = document.getElementById('connection');
      el.closest('.engine').hidden = true;
    },
    zipBlob,
    async exportBoard(board) {
      if (exporting) return;
      if (await saved(board)) return download(`${boardPath(board.id)}/shot-board.zip`, 'shot-board.zip');
      const button = document.getElementById('export'), label = button.textContent;
      exporting = true; button.textContent = 'Preparing ZIP…'; button.setAttribute('aria-busy', 'true');
      try {
        const href = URL.createObjectURL(await zipBlob(board));
        download(href, 'shot-board.zip');
        setTimeout(() => URL.revokeObjectURL(href), 60000);
      } finally { exporting = false; button.textContent = label; button.removeAttribute('aria-busy'); }
    },
    reset() {
      for (const key of Object.keys(localStorage)) if (key.startsWith(KEY)) localStorage.removeItem(key);
      location.hash = ''; location.reload();
    },
  };

  restore();
  document.addEventListener('DOMContentLoaded', () => {
    const dialog = document.getElementById('reset-dialog');
    document.getElementById('static-reset').onclick = () => dialog.showModal();
    document.getElementById('reset-cancel').onclick = () => dialog.close();
    document.getElementById('reset-confirm').onclick = () => window.SB.reset();
  });
})();
