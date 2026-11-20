'use strict';
const $ = id => document.getElementById(id);
const canvas = $('map'), ctx = canvas.getContext('2d');
let metadata = [], locations = [], visible = [], state = {}, selected = null;
let zoom = 1, pan = [0, 0], size = [0, 0], image = null, hits = [], drag = null, moved = false;
let confirmed = new Set(), hintCache = new Map();
const done = id => confirmed.has(id);
function hint(location) {
  if (!hintCache.has(location.id)) hintCache.set(location.id, TrackerLogic.evaluate(location.requires, state.inventory || {}, metadata, location.ballad));
  return hintCache.get(location.id);
}
const hintLabel = location => hint(location).met === true ? 'Item conditions met' : hint(location).met === false ? 'Missing required items' : 'Review requirements';
function filtered() {
  const query = $('search').value.toLowerCase();
  return locations.filter(l => (!$('region').value || l.region === $('region').value)
    && (!$('kind').value || l.kind === $('kind').value)
    && (!$('logic').value || ($('logic').value === 'met' ? hint(l).met === true : hint(l).met === false))
    && (!$('hide').checked || !done(l.id)) && `${l.name} ${l.region}`.toLowerCase().includes(query));
}
function render() {
  visible = filtered();
  const completed = locations.filter(l => done(l.id)).length;
  $('progress').textContent = `${completed} / ${locations.length} checks`;
  $('items').textContent = `${state.received || 0} items received`;
  $('bar').max = Math.max(1, locations.length); $('bar').value = completed;
  const mapped = visible.filter(l => l.position).length;
  $('result-count').textContent = `${visible.length} checks · ${mapped} on map${mapped < visible.length ? ` · ${visible.length - mapped} without a map position` : ''}`;
  const fragment = document.createDocumentFragment();
  for (const l of visible) {
    const button = document.createElement('button');
    button.className = (done(l.id) ? 'done ' : '') + (selected?.id === l.id ? 'selected' : '');
    button.textContent = `${done(l.id) ? '✓ ' : ''}${l.name}`;
    const small = document.createElement('small');
    small.textContent = `${l.region} · ${hintLabel(l)}${l.position ? '' : ' · list only'}`;
    button.append(small); button.onclick = () => select(l, true); fragment.append(button);
  }
  if (!visible.length) { const p = document.createElement('p'); p.textContent = 'No checks match these filters.'; fragment.append(p); }
  $('results').replaceChildren(fragment); draw();
}
function openDetail() {
  const detail = $('detail'); detail.hidden = false; detail.replaceChildren();
  const close = document.createElement('button'); close.textContent = '×'; close.className = 'close';
  close.setAttribute('aria-label', 'Close check details'); close.onclick = () => { detail.hidden = true; selected = null; render(); };
  detail.append(close); return detail;
}
function select(location, focus = false) {
  selected = location; const detail = openDetail();
  const tag = document.createElement('span'); tag.className = 'eyebrow'; tag.textContent = `${location.region} / ${location.kind}`; detail.append(tag);
  const title = document.createElement('h3'); title.textContent = location.name; detail.append(title);
  const coords = document.createElement('p'); coords.className = 'coords';
  coords.textContent = location.position ? `X ${location.position[0].toFixed(1)} · Z ${location.position[2].toFixed(1)}` : 'No map position available.'; detail.append(coords);
  if (location.positionSource === 'entrance') {
    const entrance = document.createElement('p'); entrance.textContent = 'Inside this shrine. The marker shows its overworld entrance.'; detail.append(entrance);
  }
  const status = document.createElement('p'); status.textContent = done(location.id) ? '✓ Checked by game / Archipelago' : 'Unchecked'; detail.append(status);
  const titleHint = document.createElement('p'); titleHint.className = 'hint'; titleHint.textContent = hintLabel(location); detail.append(titleHint);
  const requirements = document.createElement('p'); requirements.textContent = hint(location).text; detail.append(requirements);
  const limit = document.createElement('p'); limit.textContent = 'Item conditions only. Region access, story events, environmental supplies, and goal prerequisites still apply.'; detail.append(limit);
  if (focus && location.position) { zoom = Math.max(zoom, 3); const s = scale(); pan = [-location.position[0] * s, -location.position[2] * s]; }
  render();
}
function selectGroup(group) {
  if (group.length === 1) { select(group[0]); return; }
  selected = null; const detail = openDetail();
  const title = document.createElement('h3'); title.textContent = `${group.length} checks at this location`; detail.append(title);
  for (const location of group) {
    const button = document.createElement('button'); button.className = 'group-check';
    button.textContent = `${done(location.id) ? '✓ ' : ''}${location.name}`; button.onclick = () => select(location); detail.append(button);
  }
  draw();
}
// The game's full 12×10 map covers X ±6000, Z ±5000. The Z column is west of A.
// Both background and markers use this same world-to-screen transformation.
function scale() { return Math.min(size[0] / 12000, size[1] / 10000) * zoom; }
function project(x, z) { const s = scale(); return [size[0] / 2 + pan[0] + x * s, size[1] / 2 + pan[1] + z * s]; }
function world(x, y) { const s = scale(); return [(x - size[0] / 2 - pan[0]) / s, (y - size[1] / 2 - pan[1]) / s]; }
function draw() {
  const w = canvas.clientWidth, h = canvas.clientHeight, ratio = devicePixelRatio || 1;
  if (size[0] !== w || size[1] !== h || canvas.width !== Math.round(w * ratio)) {
    size = [w, h]; canvas.width = Math.round(w * ratio); canvas.height = Math.round(h * ratio);
  }
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.fillStyle = '#111b20'; ctx.fillRect(0, 0, w, h); hits = [];
  if (!w || !h || !image) return;
  const a = project(-6000, -5000), b = project(6000, 5000);
  ctx.drawImage(image, ...a, b[0] - a[0], b[1] - a[1]);
  const groups = new Map();
  for (const location of visible) {
    if (!location.position) continue;
    const key = `${location.position[0].toFixed(1)},${location.position[2].toFixed(1)}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(location);
  }
  for (const group of groups.values()) {
    const location = group[0], [x, y] = project(location.position[0], location.position[2]);
    if (x < -20 || y < -20 || x > w + 20 || y > h + 20) continue;
    const isSelected = group.some(l => l.id === selected?.id), allDone = group.every(l => done(l.id));
    const color = allDone ? '#899b91' : group.some(l => ['shrine', 'tower'].includes(l.kind)) || location.positionSource === 'entrance' ? '#65cbea' : ['miniboss', 'boss'].includes(location.kind) ? '#ef9b85' : '#e5bc72';
    ctx.fillStyle = color; ctx.strokeStyle = '#102027'; ctx.lineWidth = 2;
    if (isSelected) { ctx.beginPath(); ctx.arc(x, y, 14, 0, Math.PI * 2); ctx.strokeStyle = '#fff'; ctx.lineWidth = 3; ctx.stroke(); ctx.strokeStyle = '#102027'; ctx.lineWidth = 2; }
    ctx.beginPath(); const r = group.length > 1 ? 10 : 6;
    if (group.length > 1 || location.kind === 'chest') ctx.arc(x, y, r, 0, Math.PI * 2);
    else if (['miniboss', 'boss'].includes(location.kind)) { ctx.moveTo(x, y - r - 1); ctx.lineTo(x + r, y + r); ctx.lineTo(x - r, y + r); ctx.closePath(); }
    else { ctx.moveTo(x, y - r - 1); ctx.lineTo(x + r, y); ctx.lineTo(x, y + r + 1); ctx.lineTo(x - r, y); ctx.closePath(); }
    ctx.fill(); ctx.stroke();
    if (group.length > 1) { ctx.fillStyle = '#102027'; ctx.font = 'bold 11px system-ui'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(String(group.length), x, y); }
    hits.push({x, y, group});
  }
}
function zoomAt(factor, x = size[0] / 2, y = size[1] / 2) {
  const p = world(x, y); zoom = Math.max(.75, Math.min(25, zoom * factor));
  const after = project(...p); pan[0] += x - after[0]; pan[1] += y - after[1]; draw();
}
function hitAt(x, y) {
  return hits.filter(hit => Math.hypot(x - hit.x, y - hit.y) < 13)
    .sort((a,b) => Math.hypot(x-a.x,y-a.y) - Math.hypot(x-b.x,y-b.y))[0];
}
canvas.onwheel = event => { event.preventDefault(); const r = canvas.getBoundingClientRect(); zoomAt(event.deltaY < 0 ? 1.15 : 1/1.15, event.clientX-r.left, event.clientY-r.top); };
canvas.onpointerdown = event => { drag = [event.clientX, event.clientY]; moved = false; canvas.setPointerCapture(event.pointerId); $('hover').hidden = true; };
canvas.onpointermove = event => {
  const r = canvas.getBoundingClientRect();
  if (drag) {
    const dx = event.clientX-drag[0], dy = event.clientY-drag[1];
    if (Math.abs(dx)+Math.abs(dy)>2) moved = true;
    pan[0] += dx; pan[1] += dy; drag = [event.clientX,event.clientY]; draw(); return;
  }
  const hit = hitAt(event.clientX-r.left,event.clientY-r.top), hover = $('hover'); hover.hidden = !hit;
  if (hit) { hover.textContent = hit.group.length === 1 ? hit.group[0].name : `${hit.group.length} checks · ${hit.group[0].name.split(' - Chest')[0]}`;
    hover.style.left = `${Math.max(8, Math.min(size[0]-285, event.clientX-r.left+16))}px`; hover.style.top = `${Math.max(8, event.clientY-r.top-38)}px`; }
};
canvas.onpointerleave = () => { $('hover').hidden = true; };
canvas.onpointercancel = () => { drag = null; };
canvas.onpointerup = event => { drag = null; if (moved) return; const r = canvas.getBoundingClientRect(); const hit = hitAt(event.clientX-r.left,event.clientY-r.top); if (hit) selectGroup(hit.group); };
canvas.onkeydown = event => {
  if (event.key === '+' || event.key === '=') zoomAt(1.2);
  else if (event.key === '-') zoomAt(1/1.2);
  else if (['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)) {
    pan[0] += event.key==='ArrowLeft'?40:event.key==='ArrowRight'?-40:0;
    pan[1] += event.key==='ArrowUp'?40:event.key==='ArrowDown'?-40:0; draw();
  } else return;
  event.preventDefault();
};
$('zoom-in').onclick = () => zoomAt(1.3); $('zoom-out').onclick = () => zoomAt(1/1.3);
$('reset').onclick = () => { zoom = 1; pan = [0,0]; draw(); };
for (const id of ['search','region','kind','logic','hide']) $(id).oninput = render;
function renderInventory() {
  const rows = Object.entries(state.inventory || {}).sort(([a],[b]) => a.localeCompare(b));
  const progression = new Set(metadata.filter(item => item.progression).map(item => item.name)); progression.add('Paraglider');
  rows.sort(([a],[b]) => Number(progression.has(b))-Number(progression.has(a)));
  $('inventory-count').textContent = `· ${rows.filter(([name]) => progression.has(name)).length} types`;
  const fragment = document.createDocumentFragment();
  for (const [name,count] of rows) { const row = document.createElement('div'); row.textContent = `${progression.has(name)?'◆ ':''}${name} × ${count}`; fragment.append(row); }
  if (!rows.length) { const row = document.createElement('p'); row.textContent = 'Connect to your AP slot to see items.'; fragment.append(row); }
  $('inventory').replaceChildren(fragment);
  $('delivery-status').textContent = `${state.delivered || 0} / ${state.received || 0} receipts processed${state.delivery?' · '+state.delivery:''}`;
}
async function json(path) { const response = await fetch(path); if (!response.ok) throw Error(`HTTP ${response.status}`); return response.json(); }
async function loadMap() {
  try {
    const info = await json('/api/map'); if (!info.available) throw Error(info.error || 'Map not built');
    const background = new Image();
    await new Promise((resolve, reject) => {
      background.onload = resolve;
      background.onerror = () => reject(Error('Could not load map image'));
      background.src = '/map.webp';
    });
    image = background; $('mode').textContent = 'Game map · offline'; draw();
  } catch (error) { $('mode').textContent = error.message; $('map-error').hidden = false; }
}
async function poll() {
  try {
    const next = await json('/api/state'); if (!next.identity) throw Error('Waiting for game snapshot');
    state = next; confirmed = new Set(state.checks || []); hintCache.clear();
    $('connection').textContent = `${state.player} · ${state.connected?'Connected':'Offline / preview'}`;
    renderInventory(); render(); if (selected) select(selected);
  } catch (error) { $('connection').textContent = `Tracker unavailable · ${error.message}`; }
  setTimeout(poll,1500);
}
new ResizeObserver(draw).observe(canvas);
(async () => {
  loadMap();
  try {
    const data = await Promise.all([json('/api/locations'),json('/api/items')]); locations = data[0]; metadata = data[1].data;
    for (const [id,values] of [['region',locations.map(l=>l.region)],['kind',locations.map(l=>l.kind)]]) {
      for (const value of [...new Set(values)].sort()) { const option = document.createElement('option'); option.value = value; option.textContent = value; $(id).append(option); }
    }
    await poll();
  } catch (error) { $('connection').textContent = `Could not load checks: ${error.message}`; }
})();
