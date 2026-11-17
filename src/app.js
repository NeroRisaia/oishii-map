'use strict';

// おいしい店マップ（非公式）
// 兄弟アプリ（喫煙所マップ・タイムズ駐車場マップ）と同じ方式: 店舗データはページ内に同梱し、
// 端末内で近い順に並べて Leaflet に表示する。外部への通信は地図タイルだけ（外部 API は叩かない）。

const DATA = JSON.parse(document.getElementById('storeData').textContent);
const SW_SCOPE = '{{SW_SCOPE}}';
const LOCATED_ZOOM = 13;
const LIST_MAX = 50; // 一覧は近い順にこの件数まで
const GENRES = DATA.genres; // ジャンルのチップ（表示順）
const TAGS = DATA.tags; // 根拠タグのチップ（表示順）

const el = {
  status: document.getElementById('status'),
  geoStatus: document.getElementById('geoStatus'),
  locate: document.getElementById('locate'),
  nearest: document.getElementById('nearest'),
  genreChips: document.getElementById('genreChips'),
  tagChips: document.getElementById('tagChips'),
  filterCount: document.getElementById('filterCount'),
  clearFilters: document.getElementById('clearFilters'),
  empty: document.getElementById('empty'),
  card: document.getElementById('card'),
  cardName: document.getElementById('cardName'),
  cardArea: document.getElementById('cardArea'),
  cardGenre: document.getElementById('cardGenre'),
  cardMenu: document.getElementById('cardMenu'),
  cardBasis: document.getElementById('cardBasis'),
  cardChecked: document.getElementById('cardChecked'),
  cardTabelog: document.getElementById('cardTabelog'),
  cardRoute: document.getElementById('cardRoute'),
  listTitle: document.getElementById('listTitle'),
  items: document.getElementById('items'),
};

const stores = DATA.stores.map((s, id) => ({ ...s, id }));
const state = {
  pos: null,
  selected: null,
  genres: new Set(),
  tags: new Set(),
};

// ---------- 地図 ----------
const map = L.map('map', { zoomControl: true });
map.attributionControl.setPrefix('<a href="https://leafletjs.com" target="_blank" rel="noopener">Leaflet</a>');
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
}).addTo(map);
const allBounds = L.latLngBounds(stores.map((s) => [s.lat, s.lon]));
// 起動時は都心の掲載店が見える範囲（現在地が取れたら現在地へ寄せる）
map.fitBounds(L.latLngBounds(stores.filter((s) => s.lat > 35.55 && s.lat < 35.8 && s.lon > 139.6 && s.lon < 139.9).map((s) => [s.lat, s.lon])), { padding: [20, 20] });

function pinIcon(selected) {
  return L.divIcon({
    className: 'shop-pin' + (selected ? ' sel' : ''),
    html: '🍴',
    iconSize: [30, 30],
  });
}
const markers = new Map();
for (const s of stores) {
  const m = L.marker([s.lat, s.lon], { icon: pinIcon(false), title: s.name, keyboard: true, riseOnHover: true });
  m.on('click', (e) => {
    if (e.originalEvent) L.DomEvent.stopPropagation(e.originalEvent);
    select(s.id, { move: false });
  });
  markers.set(s.id, m);
}
let userMarker = null;

// ---------- 絞り込み（ジャンルとタグの間は AND、同じ種類の中は OR） ----------
function matches(s) {
  if (state.genres.size && !state.genres.has(s.group)) return false;
  if (state.tags.size && !s.tags.some((t) => state.tags.has(t))) return false;
  return true;
}

function filtered() {
  return stores.filter(matches);
}

function makeChips(box, values, set, countOf) {
  box.replaceChildren(
    ...values.map((v) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'chip';
      b.dataset.value = v;
      b.setAttribute('aria-pressed', 'false');
      const label = document.createElement('span');
      label.textContent = v;
      const n = document.createElement('span');
      n.className = 'n';
      n.textContent = String(countOf(v));
      b.append(label, n);
      b.addEventListener('click', () => {
        if (set.has(v)) set.delete(v);
        else set.add(v);
        b.setAttribute('aria-pressed', String(set.has(v)));
        onFilterChange();
      });
      return b;
    }),
  );
}
makeChips(el.genreChips, GENRES, state.genres, (g) => stores.filter((s) => s.group === g).length);
makeChips(el.tagChips, TAGS, state.tags, (t) => stores.filter((s) => s.tags.includes(t)).length);

el.clearFilters.addEventListener('click', () => {
  state.genres.clear();
  state.tags.clear();
  document.querySelectorAll('.chip').forEach((c) => c.setAttribute('aria-pressed', 'false'));
  onFilterChange();
});

function onFilterChange() {
  if (state.selected != null && !matches(stores[state.selected])) closeCard();
  render();
}

// ---------- 描画 ----------
function haversine(a, b) {
  const toRad = (deg) => (deg * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLon = toRad(b.lon - a.lon);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.sqrt(h));
}

function formatDistance(m) {
  if (m < 1000) return `${Math.round(m)}m`;
  if (m < 10000) return `${(m / 1000).toFixed(1)}km`;
  return `${Math.round(m / 1000)}km`;
}

function referencePoint() {
  if (state.pos) return { pt: state.pos, user: true };
  const c = map.getCenter();
  return { pt: { lat: c.lat, lon: c.lng }, user: false };
}

function sortedByDistance(list, pt) {
  return list.map((s) => ({ s, d: haversine(pt, s) })).sort((a, b) => a.d - b.d);
}

function render() {
  const list = filtered();
  const want = new Set(list.map((s) => s.id));
  for (const [id, m] of markers) {
    if (want.has(id) && !map.hasLayer(m)) m.addTo(map);
    if (!want.has(id) && map.hasLayer(m)) m.remove();
  }
  const b = map.getBounds();
  const visible = list.filter((s) => b.contains([s.lat, s.lon])).length;
  el.empty.hidden = visible > 0;

  const filtering = state.genres.size + state.tags.size > 0;
  el.filterCount.textContent = filtering ? `条件に合う店 ${list.length}件／全${stores.length}件` : `全${stores.length}件を表示中`;
  el.clearFilters.hidden = !filtering;
  el.status.textContent = `地図の範囲に ${visible}件${state.pos ? '' : '（現在地なし：地図を動かして探せます）'}`;

  renderList(list);
  updateNearestButton(list);
}

function renderList(list) {
  const { pt, user } = referencePoint();
  const sorted = sortedByDistance(list, pt);
  el.listTitle.textContent = (user ? '現在地から近い順' : '地図の中心から近い順') + (sorted.length > LIST_MAX ? `（${LIST_MAX}件まで）` : '');
  const rows = document.createDocumentFragment();
  if (!list.length) {
    const li = document.createElement('li');
    li.className = 'none';
    li.textContent = '条件に合う店がありません。絞り込みを変えてください。';
    rows.appendChild(li);
  }
  for (const { s, d } of sorted.slice(0, LIST_MAX)) {
    const li = document.createElement('li');
    const btn = document.createElement('button');
    btn.type = 'button';
    if (state.selected === s.id) btn.setAttribute('aria-current', 'true');
    const nm = document.createElement('span');
    nm.className = 'nm';
    nm.textContent = s.name;
    const dist = document.createElement('span');
    dist.className = 'dist';
    dist.textContent = formatDistance(d);
    const sub = document.createElement('span');
    sub.className = 'sub';
    sub.textContent = `${s.genre}｜${s.area}`;
    btn.append(nm, dist, sub);
    btn.addEventListener('click', () => {
      followPausedUntil = Date.now() + SELECT_FOLLOW_PAUSE_MS; // 一覧から選んだ店を見ている間は現在地へ戻さない
      select(s.id, { move: true });
    });
    li.appendChild(btn);
    rows.appendChild(li);
  }
  el.items.replaceChildren(rows);
}

// ---------- 詳細カード ----------
function routeUrl(s) {
  return `https://www.google.com/maps/search/?api=1&query=${s.lat},${s.lon}`;
}

function select(id, { move }) {
  const s = stores[id];
  if (state.selected != null && markers.get(state.selected)) markers.get(state.selected).setIcon(pinIcon(false));
  state.selected = id;
  markers.get(id).setIcon(pinIcon(true));
  markers.get(id).setZIndexOffset(1000);
  el.cardName.textContent = s.name;
  el.cardArea.textContent = s.area;
  el.cardGenre.textContent = s.genre;
  el.cardMenu.textContent = s.menu;
  el.cardBasis.textContent = s.basis;
  el.cardChecked.textContent = s.checked;
  el.cardTabelog.href = s.url;
  el.cardRoute.href = routeUrl(s);
  el.card.hidden = false;
  if (move) map.setView([s.lat, s.lon], Math.max(map.getZoom(), 15), { animate: false });
  render();
  // カードが画面外なら見える位置へ（地図の下にカードがある）
  const r = el.card.getBoundingClientRect();
  if (r.top > window.innerHeight - 80 || r.bottom < 0) el.card.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

function closeCard() {
  if (state.selected != null) {
    const m = markers.get(state.selected);
    m.setIcon(pinIcon(false));
    m.setZIndexOffset(0);
  }
  state.selected = null;
  el.card.hidden = true;
  render();
}
map.on('click', () => {
  if (state.selected != null) closeCard();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && state.selected != null) closeCard();
});

map.on('moveend', render);

// ---------- 現在地（兄弟アプリと同じ追従仕様） ----------
// 読み込み直後に開始 → 概略位置（getCurrentPosition）→ GPS（watchPosition）。
// 位置が届くたびに現在地へ寄せる（追従）。「最寄り」・一覧から選んだ直後の10秒は追従を止める。
// 地図を手で動かしたら、手を離した時点から5秒は止め、5秒後に現在地へ戻す。「現在地」ボタンで両方解除。
const geoLog = [];
function logGeo(event, detail = {}) {
  const entry = { t: new Date().toISOString(), event, secure: window.isSecureContext, ...detail };
  geoLog.push(entry);
  console.info('[おいしい店マップ] 位置情報', entry);
}

function setGeoStatus(text) {
  el.geoStatus.hidden = !text;
  el.geoStatus.textContent = text;
}

function geoFailureText(error) {
  if (!window.isSecureContext) {
    return 'このアドレスでは、ブラウザの安全上の制限により位置情報が使えないため、現在地は表示していません（https の公開版ではそのまま使えます）。地図を動かして探せます。';
  }
  if (error && error.code === 1) return '位置情報の利用が許可されていないため、現在地は表示していません。ブラウザや端末の設定で許可すると使えます。それまでは地図を動かして探せます。';
  if (error && error.code === 3) return '現在地の測位に時間がかかっています。少し待ってから、もう一度「現在地」を押してください。';
  return '今は現在地を測位できませんでした。電波の届く場所で、もう一度「現在地」を押してください。';
}

const NEAREST_FOLLOW_PAUSE_MS = 10000;
const SELECT_FOLLOW_PAUSE_MS = 10000;
let followPausedUntil = 0;
function followPaused() {
  return Date.now() < followPausedUntil;
}

function centerOn(pos) {
  map.setView([pos.lat, pos.lon], Math.max(map.getZoom(), LOCATED_ZOOM));
}

const USER_FOLLOW_PAUSE_MS = 5000;
const userGestures = new Set();
let userPausedUntil = 0;
let userResumeTimer = null;

function userPaused() {
  return userGestures.size > 0 || Date.now() < userPausedUntil;
}
function followBlocked() {
  return followPaused() || userPaused();
}
function userGestureStart(kind) {
  userGestures.add(kind);
  clearTimeout(userResumeTimer);
  userResumeTimer = null;
  logGeo('user-gesture-start', { kind });
}
function userGestureEnd(kind) {
  if (!userGestures.delete(kind) && kind !== 'instant') return;
  if (userGestures.size > 0) return;
  userPausedUntil = Date.now() + USER_FOLLOW_PAUSE_MS; // 手を離した時点から5秒
  clearTimeout(userResumeTimer);
  userResumeTimer = setTimeout(resumeAfterUserGesture, USER_FOLLOW_PAUSE_MS);
  logGeo('user-follow-paused', { kind, ms: USER_FOLLOW_PAUSE_MS });
}
function userInstantInput(kind) {
  if (userGestures.size > 0) return;
  logGeo('user-gesture-start', { kind });
  userGestureEnd('instant');
}
function resumeAfterUserGesture() {
  userResumeTimer = null;
  if (userPaused()) return;
  if (followPaused()) return; // 「最寄り」・一覧選択後の10秒停止中は、そちらの再開（次の測位）に任せる
  logGeo('follow-resumed', { by: 'user-timeout' });
  if (state.pos) centerOn(state.pos);
}
function cancelUserPause() {
  userGestures.clear();
  userPausedUntil = 0;
  clearTimeout(userResumeTimer);
  userResumeTimer = null;
}

map.on('dragstart', () => userGestureStart('drag'));
map.on('dragend', () => userGestureEnd('drag'));
function releaseDrag(e) {
  if (!userGestures.has('drag')) return;
  if (e.touches && e.touches.length > 0) return;
  userGestureEnd('drag');
}
['mouseup', 'pointerup', 'pointercancel', 'touchend', 'touchcancel'].forEach((type) => {
  document.addEventListener(type, releaseDrag, { capture: true, passive: true });
});
window.addEventListener('blur', releaseDrag);
map.on('dblclick', () => userInstantInput('dblclick-zoom'));
map.on('boxzoomend', () => userInstantInput('box-zoom'));
map.on('keydown', (e) => {
  const key = e.originalEvent && e.originalEvent.key;
  if (['+', '-', '=', '_', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(key)) userInstantInput('keyboard');
});
{
  const box = map.getContainer();
  let pinching = false;
  box.addEventListener('touchstart', (e) => {
    if (e.touches.length >= 2 && !pinching) {
      pinching = true;
      userGestureStart('pinch');
    }
  }, { passive: true });
  const pinchEnd = (e) => {
    if (pinching && e.touches.length < 2) {
      pinching = false;
      userGestureEnd('pinch');
    }
  };
  box.addEventListener('touchend', pinchEnd, { passive: true });
  box.addEventListener('touchcancel', pinchEnd, { passive: true });
  box.addEventListener('wheel', () => userInstantInput('wheel'), { passive: true });
  // ＋－ボタンは Leaflet がボタン自身でクリックの伝播を止めるため、ボタンに直接付ける
  box.querySelectorAll('.leaflet-control-zoom a').forEach((btn) => {
    btn.addEventListener('click', () => userInstantInput('zoom-button'));
  });
}

function onPosition(position, source) {
  const pos = { lat: position.coords.latitude, lon: position.coords.longitude };
  const first = state.pos == null;
  state.pos = pos;
  if (first) logGeo('ok', { source, accuracy: Math.round(position.coords.accuracy) });
  if (!userMarker) userMarker = L.circleMarker([pos.lat, pos.lon], { radius: 8, color: '#fff', weight: 3, fillColor: '#1565c0', fillOpacity: 1 }).bindTooltip('現在地').addTo(map);
  else userMarker.setLatLng([pos.lat, pos.lon]);
  if (!followBlocked()) centerOn(pos);
  if (first) setGeoStatus('');
  render();
}

function onGeoError(error, source) {
  logGeo('error', { source, code: error && error.code, message: error && error.message });
  if (state.pos) return;
  setGeoStatus(geoFailureText(error));
}

let watching = false;
function startGeolocation() {
  if (!('geolocation' in navigator)) {
    logGeo('unsupported');
    setGeoStatus('この端末・ブラウザは位置情報に対応していないため、現在地は表示していません。地図を動かして探せます。');
    return;
  }
  if (watching) return;
  watching = true;
  logGeo('start');
  navigator.geolocation.getCurrentPosition(
    (position) => {
      if (state.pos == null) onPosition(position, 'coarse');
    },
    (error) => logGeo('coarse-error', { code: error.code, message: error.message }),
    { enableHighAccuracy: false, maximumAge: 600000, timeout: 5000 },
  );
  navigator.geolocation.watchPosition(
    (position) => onPosition(position, 'gps'),
    (error) => {
      watching = false;
      onGeoError(error, 'gps');
    },
    { enableHighAccuracy: true, maximumAge: 10000 },
  );
}

el.locate.addEventListener('click', () => {
  if (!('geolocation' in navigator)) {
    startGeolocation();
    return;
  }
  followPausedUntil = 0;
  cancelUserPause();
  logGeo('follow-resumed', { by: 'locate-button' });
  if (state.pos) centerOn(state.pos);
  setGeoStatus('現在地を取得しています…');
  navigator.geolocation.getCurrentPosition(
    (position) => {
      onPosition(position, 'button');
      centerOn(state.pos);
      setGeoStatus('');
    },
    (error) => {
      logGeo('button-error', { code: error.code, message: error.message });
      setGeoStatus(state.pos ? '' : geoFailureText(error));
    },
    { enableHighAccuracy: true, maximumAge: 10000, timeout: 15000 },
  );
  startGeolocation();
});

// ---------- 「最寄り」ボタン ----------
// 絞り込み条件に合う店のうち、現在地から最も近い店を開き、10秒間だけ追従を止める。
function nearestStore(pos, list) {
  if (!pos || !list.length) return null;
  return sortedByDistance(list, pos)[0];
}

function updateNearestButton(list) {
  const t = state.pos ? nearestStore(state.pos, list) : null;
  el.nearest.textContent = t ? `最寄り（${formatDistance(t.d)}）` : '最寄り';
}

function goNearest(pos, note) {
  const t = nearestStore(pos, filtered());
  if (!t) {
    setGeoStatus('条件に合う店がありません。絞り込みを変えてください。');
    return;
  }
  setGeoStatus(note || '');
  followPausedUntil = Date.now() + NEAREST_FOLLOW_PAUSE_MS;
  logGeo('nearest-ok', { name: t.s.name, distance: Math.round(t.d) });
  select(t.s.id, { move: true });
}

el.nearest.addEventListener('click', () => {
  if (!('geolocation' in navigator)) {
    setGeoStatus('この端末・ブラウザは位置情報に対応していないため、現在地は表示していません。地図を動かして探せます。');
    return;
  }
  setGeoStatus('現在地を取得して、最寄りの店を探しています…');
  navigator.geolocation.getCurrentPosition(
    (position) => {
      followPausedUntil = Date.now() + NEAREST_FOLLOW_PAUSE_MS;
      onPosition(position, 'nearest');
      goNearest(state.pos);
    },
    (error) => {
      logGeo('nearest-error', { code: error.code, message: error.message });
      if (state.pos) {
        goNearest(state.pos, `${geoFailureText(error)} 前回の現在地から探しました。`);
        return;
      }
      setGeoStatus(geoFailureText(error));
    },
    { enableHighAccuracy: true, maximumAge: 10000, timeout: 15000 },
  );
  startGeolocation();
});

render();
startGeolocation();

// ---------- オフライン用（スコープはこのアプリのフォルダだけ） ----------
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('./sw.js', { scope: SW_SCOPE }).catch(() => {});
  });
}

window.__om = { state, stores, map, markers, geoLog, filtered, routeUrl, allBounds, followPaused, userPaused }; // 動作確認用
