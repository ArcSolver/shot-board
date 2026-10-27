// Static board viewer: answers the app's /api calls from files the build
// produced with the real server, so nothing here talks to a GPU or a backend.
// Picks and reviews stay in this browser (localStorage).
(() => {
  'use strict';
  const KEY = 'shotboard-static:v1:';
  const GPU_ONLY = 'To render new takes, run Shot Board locally with your own ComfyUI.';
  const realFetch = window.fetch.bind(window);
  const files = new Map();
  const boards = new Map();

  class HttpError extends Error { constructor(status, message) { super(message); this.status = status; } }
  const json = (data, status = 200) => new Response(JSON.stringify(data), {status, headers: {'Content-Type': 'application/json'}});
  const boardPath = (id) => `data/boards/${encodeURIComponent(id)}`;

  async function load(path) {
    if (!files.has(path)) {
      files.set(path, realFetch(path).then(r => { if (!r.ok) throw new HttpError(404, 'Not found'); return r.json(); }));
    }
    try { return structuredClone(await files.get(path)); } catch (error) { files.delete(path); throw error; }
  }
  const examples = () => load('data/examples.json');
  const shipped = (id) => load(boardPath(id) + '.json');

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

  async function route(method, url, body) {
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
      if (!['landscape', 'portrait'].includes(layout)) throw new HttpError(422, 'Choose landscape or portrait.');
      if (picks(board) !== picks(await shipped(board.id))) throw new HttpError(409, 'The storyboard here uses the saved picks. Press Reset, or run Shot Board locally to export your own picks.');
      return realFetch(`${boardPath(board.id)}/storyboard-${layout}.png`);
    }
    if (['PATCH', 'POST'].includes(method)) throw new HttpError(409, GPU_ONLY);
    throw new HttpError(404, 'Not found');
  }

  window.fetch = (input, init = {}) => {
    const url = typeof input === 'string' ? input : input.url;
    if (!url.startsWith('/api/')) return realFetch(input, init);
    let body;
    try { body = init.body ? JSON.parse(init.body) : undefined; } catch { return Promise.resolve(json({detail: 'Please check your inputs.'}, 422)); }
    return route((init.method || 'GET').toUpperCase(), url, body)
      .catch(error => json({detail: error instanceof HttpError ? error.message : 'Request failed'}, error.status || 500));
  };

  window.SB = {
    imageURL: (id, file) => `${boardPath(id)}/images/${encodeURIComponent(file)}`,
    health() {
      const el = document.getElementById('connection');
      el.closest('.engine').hidden = true;
    },
    async exportBoard(board) {
      const original = await shipped(board.id);
      if (picks(board) !== picks(original) || reviews(board) !== reviews(original)) {
        throw new Error('The ZIP here holds the saved picks and reviews. Press Reset, or run Shot Board locally to export your own.');
      }
      const link = document.createElement('a');
      link.href = `${boardPath(board.id)}/shot-board.zip`; link.download = 'shot-board.zip';
      document.body.append(link); link.click(); link.remove();
    },
    reset() {
      for (const key of Object.keys(localStorage)) if (key.startsWith(KEY)) localStorage.removeItem(key);
      location.hash = ''; location.reload();
    },
  };

  restore();
  document.addEventListener('DOMContentLoaded', () => { document.getElementById('static-reset').onclick = () => window.SB.reset(); });
})();
