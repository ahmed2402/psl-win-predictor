// Chase Predictor front end: form + ball-by-ball pad -> POST /predict -> broadcast graphic, worm and needle.
const $ = (id) => document.getElementById(id);
const form = $("console");
const css = getComputedStyle(document.documentElement);
const color = (name) => css.getPropertyValue(name).trim();
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

const LABELS = {
  balls_left: "Balls left", runs_needed: "Runs needed", wickets: "Wickets down", rrr: "Required rate",
  crr: "Current rate", runs_last12: "Runs, last 12 balls", wkts_last12: "Wickets, last 12 balls", dew_point_c: "Dew point (°C)",
};
const FIELD_NAMES = { target: "Target", runs: "Runs", wickets: "Wickets", overs: "Completed overs",
  balls: "Balls in the over", runs_last12: "Runs in the last 12 balls", wkts_last12: "Wickets in the last 12 balls" };
const NUM_FIELDS = Object.keys(FIELD_NAMES);

// Original crest badges in each franchise's well-known colours (not official logos): [monogram, field, band, ink].
// Hyderabad Kingsmen and Rawalpindiz joined in 2026; their colours here are placeholders until confirmed.
const BADGES = {
  "Islamabad United": ["IU", "#d71920", "#151515", "#ffffff"],
  "Karachi Kings": ["KK", "#0b4ea2", "#e8b731", "#ffffff"],
  "Lahore Qalandars": ["LQ", "#00843d", "#e4222b", "#ffffff"],
  "Multan Sultans": ["MS", "#0a7c6e", "#f2b705", "#ffffff"],
  "Peshawar Zalmi": ["PZ", "#fcbf16", "#151515", "#151515"],
  "Quetta Gladiators": ["QG", "#5a2d82", "#f2b705", "#ffffff"],
  "Hyderabad Kingsmen": ["HK", "#e36c1d", "#151515", "#ffffff"],
  "Rawalpindiz": ["RP", "#7d1d3f", "#c9a227", "#ffffff"],
};

function badgeSVG(team) {
  const [mono, field, band, ink] = BADGES[team] || [team.slice(0, 2).toUpperCase(), "#3a4a40", "#a9bdb0", "#ffffff"];
  return `<svg viewBox="0 0 40 46" role="img" aria-label="${team} badge">
    <clipPath id="c-${mono}"><path d="M20 1 38 6v16c0 12-8 19-18 23C10 41 2 34 2 22V6Z"/></clipPath>
    <g clip-path="url(#c-${mono})"><rect width="40" height="46" fill="${field}"/><path d="M0 30 40 18v7L0 37Z" fill="${band}"/></g>
    <path d="M20 1 38 6v16c0 12-8 19-18 23C10 41 2 34 2 22V6Z" fill="none" stroke="#eef3ea" stroke-opacity=".55" stroke-width="1.5"/>
    <text x="20" y="25" text-anchor="middle" font-family="Big Shoulders Display, sans-serif" font-weight="900" font-size="17" fill="${ink}">${mono}</text>
  </svg>`;
}

// Dew point is fetched by the visitor's browser (Render's shared IPs get rate-limited by Open-Meteo).
let coords = {};
const dewCache = {};
async function browserDew(city) {
  const day = new Date().toISOString().slice(0, 10);
  if (dewCache[city + day] !== undefined) return dewCache[city + day];
  const [lat, lon] = coords[city] || [];
  if (lat === undefined) return null;
  try {
    const url = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&hourly=dew_point_2m&timezone=auto&start_date=${day}&end_date=${day}`;
    const h = (await (await fetch(url, { signal: AbortSignal.timeout(5000) })).json()).hourly;
    const vals = h.time.map((t, i) => [Number(t.slice(11, 13)), h.dew_point_2m[i]]).filter(([hr, v]) => hr >= 16 && hr <= 22 && v !== null);
    if (!vals.length) return null;   // same 16:00-22:00 window as the training data
    return (dewCache[city + day] = +(vals.reduce((a, [, v]) => a + v, 0) / vals.length).toFixed(1));
  } catch {
    return null;   // the server then tries itself, then falls back to the training median
  }
}

let worm = null;
let shownPct = 50;
let log = [];          // deliveries logged with the pad: {runs, wkt, legal, mark}
let undoStack = [];    // form snapshots, one per logged delivery
let base12 = null;     // last-12 values typed before the pad was used

// ---------- reading and checking the form ----------
function readState() {
  const s = Object.fromEntries(new FormData(form));
  NUM_FIELDS.forEach((k) => { s[k] = Number(s[k]); });
  return s;
}

function writeState(s) {
  for (const [k, v] of Object.entries(s)) if (form.elements[k]) form.elements[k].value = v;
}

function problems(s) {   // mirrors the API's rules so most mistakes never leave the page
  const out = [];
  const bad = (name, msg) => { out.push(msg); form.elements[name]?.setAttribute("aria-invalid", "true"); };
  form.querySelectorAll("[aria-invalid]").forEach((el) => el.removeAttribute("aria-invalid"));
  for (const k of NUM_FIELDS) {
    const el = form.elements[k];
    if (!Number.isInteger(s[k]) || s[k] < Number(el.min) || s[k] > Number(el.max)) bad(k, `${FIELD_NAMES[k]} must be a whole number from ${el.min} to ${el.max}.`);
  }
  if (s.batting_team === s.bowling_team) bad("bowling_team", "Pick two different teams.");
  if (s.runs >= s.target) bad("runs", "Runs must be below the target, or the chase is already won.");
  if (s.runs_last12 > s.runs) bad("runs_last12", "Runs in the last 12 balls can't be more than the total score.");
  if (s.wkts_last12 > s.wickets) bad("wkts_last12", "Wickets in the last 12 balls can't be more than wickets lost.");
  return out;
}

function showErrors(list) {
  $("errors").replaceChildren(...list.map((t) => Object.assign(document.createElement("li"), { textContent: t })));
}

// ---------- talking to the API ----------
async function predict() {
  const s = readState();
  const errs = problems(s);
  showErrors(errs);
  if (errs.length) return;
  $("update").setAttribute("aria-busy", "true");
  $("notice").hidden = true;
  try {
    const dew = await browserDew(s.city);
    const payload = dew === null ? s : { ...s, dew_point_c: dew };
    const r = await fetch("predict", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) });
    const body = await r.json();
    if (r.status === 422) {
      showErrors(body.detail.map((d) => d.msg.replace(/^Value error, /, "")));
      return;
    }
    if (!r.ok) throw new Error(`Server answered ${r.status}`);
    render(s, body);
  } catch (e) {
    note(`Couldn't reach the predictor (${e.message}). Check the connection and press Update again.`);
  } finally {
    $("update").removeAttribute("aria-busy");
  }
}

function note(text) { $("notice").textContent = text; $("notice").hidden = false; }

// ---------- drawing ----------
function setBar(pct, chaseName, bowlName) {
  $("tug").dataset.state = "ready";
  $("chase-name").textContent = chaseName;
  $("bowl-name").textContent = bowlName;
  $("chase-badge").innerHTML = badgeSVG(chaseName);
  $("bowl-badge").innerHTML = badgeSVG(bowlName);
  $("tug-fill").style.setProperty("--p", `${pct}%`);
  $("tug-fill").classList.toggle("is-full", pct >= 100);   // at 100% drop the slant so no red shows at either end
  countTo(pct);
}

function countTo(target) {
  const from = shownPct;
  shownPct = target;
  const paint = (v) => { $("chase-pct").textContent = `${Math.round(v)}%`; $("bowl-pct").textContent = `${100 - Math.round(v)}%`; };
  if (reduceMotion) return paint(target);
  const t0 = performance.now();
  const step = (t) => {
    const k = Math.min(1, (t - t0) / 900);
    paint(from + (target - from) * (1 - Math.pow(2, -10 * k)));   // exponential ease-out, same as the bar
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

let hasShown = false;
function render(s, res) {
  const pct = res.win_probability * 100;
  const before = shownPct;
  setBar(pct, s.batting_team, s.bowling_team);
  if (hasShown && Math.abs(pct - before) >= 10) swing(pct - before, s.batting_team);
  hasShown = true;
  const balls = 120 - (s.overs * 6 + s.balls);
  const need = s.target - s.runs;
  const rrr = (need * 6 / balls).toFixed(2);
  showResult(null);
  updateScore(s);
  $("st-need").textContent = need;
  $("st-balls").textContent = balls;
  $("st-wkts").textContent = 10 - s.wickets;
  $("st-rrr").textContent = rrr;
  $("summary").textContent = `${s.batting_team} ${Math.round(pct)} percent, ${s.bowling_team} ${100 - Math.round(pct)} percent.`;
  drawWorm(res.what_if, s.runs);
  drawNeedle(res.contributions);
  $("dew").innerHTML = "";
  $("dew").append("Dew ", bold(`${res.dew_point_c.toFixed(1)}°C`), res.dew_source.startsWith("live") ? " · live, Open-Meteo" : " · weather offline, typical value used");
}

function bold(text) { return Object.assign(document.createElement("b"), { textContent: text }); }

function drawWorm(points, now) {
  if (!window.Chart) return;   // CDN blocked: the bar and needle still work
  const data = points.map((p) => ({ x: p.runs, y: +(p.win_probability * 100).toFixed(1) }));
  const radius = data.map((p) => (p.x === now ? 7 : 0));
  $("worm-text").textContent = `From ${data[0].x} to ${data.at(-1).x} runs the chance goes from ${Math.round(data[0].y)}% to ${Math.round(data.at(-1).y)}%.`;
  if (worm) {
    Object.assign(worm.data.datasets[0], { data, pointRadius: radius, pointHoverRadius: radius.map((r) => r || 4) });
    return worm.update();
  }
  Chart.defaults.font.family = color("--ui");
  Chart.defaults.color = color("--chalk-dim");
  worm = new Chart($("worm"), {
    type: "line",
    data: { datasets: [{ data, borderColor: color("--gold"), borderWidth: 3, tension: .25, pointRadius: radius,
      pointBackgroundColor: color("--ground"), pointBorderColor: color("--gold"), pointBorderWidth: 3,
      fill: { target: "origin", above: "rgba(244,194,71,.10)" } }] },
    options: {
      maintainAspectRatio: false, animation: reduceMotion ? false : { duration: 700, easing: "easeOutExpo" },
      plugins: { legend: { display: false }, tooltip: { callbacks: { title: (i) => `${i[0].parsed.x} runs`, label: (i) => `${i.parsed.y}% chase win` } } },
      scales: {   // fixed 0-100 scale so predictions stay comparable from one update to the next
        x: { type: "linear", title: { display: true, text: "Runs scored so far" }, grid: { color: color("--seam") } },
        y: { min: 0, max: 100, ticks: { stepSize: 25, callback: (v) => `${v}%` }, grid: { color: color("--seam") } },
      },
    },
  });
}

function drawNeedle(items) {
  const max = Math.max(0.05, ...items.map((c) => Math.abs(c.effect)));   // biggest push fills the half-track
  const sorted = [...items].sort((a, b) => Math.abs(b.effect) - Math.abs(a.effect));
  $("needle").replaceChildren(...sorted.map((c) => {
    const li = document.createElement("li");
    const w = (Math.abs(c.effect) / max) * 50;
    const dir = c.effect >= 0 ? "up" : "down";
    li.innerHTML = `<span class="needle__label"></span><span class="needle__track"><span class="needle__bar ${dir}"></span></span>`;
    li.querySelector(".needle__label").append(LABELS[c.feature] || c.feature, bold(String(+c.value.toFixed(2))));
    const bar = li.querySelector(".needle__bar");
    bar.style.transform = `scaleX(${w / 50})`;
    li.setAttribute("aria-label", `${LABELS[c.feature]} ${c.value}: ${dir === "up" ? "helps the chasing side" : "helps the bowlers"}`);
    return li;
  }));
}

// ---------- ball-by-ball pad ----------
const BALLS = { 0: [0, 0, 1], 1: [1, 0, 1], 2: [2, 0, 1], 3: [3, 0, 1], 4: [4, 0, 1], 6: [6, 0, 1], W: [0, 1, 1], Wd: [1, 0, 0] };

function logBall(mark) {
  const s = readState();
  const errs = problems(s);
  showErrors(errs);   // also clears any earlier error once the state is valid
  if (errs.length) return;
  if (!log.length) base12 = { r: s.runs_last12, w: s.wkts_last12 };
  undoStack.push({ ...s });
  const [runs, wkt, legal] = BALLS[mark];
  log.push({ runs, wkt, legal, mark });
  s.runs += runs;
  s.wickets += wkt;
  if (legal) { s.balls += 1; if (s.balls === 6) { s.overs += 1; s.balls = 0; } }
  // last 12 balls: real logged balls, plus the typed values fading out pro rata until 12 are logged
  const recent = log.slice(-12);
  const keep = Math.max(0, 12 - recent.length) / 12;
  s.runs_last12 = Math.min(s.runs, Math.round(base12.r * keep) + recent.reduce((a, b) => a + b.runs, 0));
  s.wkts_last12 = Math.min(s.wickets, Math.round(base12.w * keep) + recent.reduce((a, b) => a + b.wkt, 0));
  writeState(s);
  drawStrip(true);
  $("undo").disabled = false;
  sting(mark);
  play(mark);
  if (!finished(s)) predict();
}

function finished(s) {   // the chase can end on this ball: no prediction needed, just the result
  const legalBalls = s.overs * 6 + s.balls;
  let text = null, pct = null;
  if (s.runs >= s.target) [text, pct] = [`${s.batting_team} have chased it down.`, 100];
  else if (s.wickets >= 10) [text, pct] = [`${s.batting_team} are all out. ${s.bowling_team} win.`, 0];
  else if (legalBalls >= 120) [text, pct] = s.runs === s.target - 1 ? ["Scores level: it's a tie.", 50] : [`Overs are up. ${s.bowling_team} win.`, 0];
  if (text === null) return false;
  setBar(pct, s.batting_team, s.bowling_team);
  updateScore(s);
  showResult(text);
  document.querySelectorAll(".key[data-ball]").forEach((k) => { k.disabled = true; });
  return true;
}

function updateScore(s) {   // live scoreboard plate in the masthead
  $("sb-runs").textContent = s.runs;
  $("sb-wkts").textContent = s.wickets;
  $("sb-overs").textContent = `${s.overs}.${s.balls}`;
}

function showResult(text) {   // the chase is over: a result plate replaces the stat strip
  $("result").textContent = text || "";
  $("result").hidden = !text;
  $("equation").hidden = !!text;
}

function undo() {
  const prev = undoStack.pop();
  if (!prev) return;
  log.pop();
  writeState(prev);
  document.querySelectorAll(".key[data-ball]").forEach((k) => { k.disabled = false; });
  $("undo").disabled = !undoStack.length;
  drawStrip(false);
  predict();
}

function drawStrip(animateLast) {
  const recent = log.slice(-12);
  const cells = Array.from({ length: 12 }, (_, i) => {
    const li = document.createElement("li");
    const b = recent[i];
    if (!b) { li.className = "is-empty"; li.setAttribute("aria-hidden", "true"); return li; }
    li.textContent = b.mark === "0" ? "•" : b.mark;
    li.className = `b${b.mark}${animateLast && i === recent.length - 1 ? " bnew" : ""}`;
    li.setAttribute("aria-label", { 0: "dot", W: "wicket", Wd: "wide" }[b.mark] || `${b.mark} runs`);
    return li;
  });
  $("strip").replaceChildren(...cells);
}

// ---------- per-ball stings, momentum tag and optional sound ----------
const EASE = "cubic-bezier(.16, 1, .3, 1)";
const STUMPS = `<svg viewBox="0 0 30 40"><rect x="3" y="8" width="4" height="32"/><rect x="13" y="8" width="4" height="32"/>
  <rect x="23" y="8" width="4" height="32"/><rect class="bail" x="2" y="3" width="12" height="3"/><rect class="bail" x="16" y="3" width="12" height="3"/></svg>`;

function sting(mark) {
  const layer = $("sting");
  layer.getAnimations({ subtree: true }).forEach((a) => a.cancel());   // a new ball replaces the old sting
  const big = { 6: ["six", "Six"], 4: ["four", "Four"], W: ["wkt", "Wicket"] }[mark];
  layer.className = `sting sting--${big ? big[0] : "chip"}`;
  const el = document.createElement("div");
  if (big) {
    el.className = "sting__plate";
    el.innerHTML = mark === "W" ? `${STUMPS}<span>Wicket</span>` : `<span>${big[1]}</span>`;
  } else {
    el.className = `sting__chip${mark === "Wd" ? " sting__chip--wd" : ""}`;
    el.textContent = { 0: "Dot ball", 1: "+1 run", 2: "+2 runs", 3: "+3 runs", Wd: "Wide +1" }[mark];
  }
  layer.replaceChildren(el);
  let anim;
  if (reduceMotion) {
    anim = el.animate([{ opacity: 0 }, { opacity: 1, offset: .15 }, { opacity: 1, offset: .8 }, { opacity: 0 }], 900);
  } else if (!big) {
    anim = el.animate([{ opacity: 0, transform: "translateY(14px) scale(.85)" }, { opacity: 1, transform: "none", offset: .2, easing: EASE },
      { opacity: 1, offset: .7 }, { opacity: 0, transform: "translateY(-12px)" }], { duration: 950, fill: "forwards" });
  } else {
    // banner: sweeps in on the broadcast slant, holds, sweeps out past the edge of any screen width
    anim = el.animate([{ transform: "translateX(-100vw) skewX(-10deg)", easing: EASE }, { transform: "translateX(0) skewX(-10deg)", offset: .28 },
      { transform: "translateX(0) skewX(-10deg)", opacity: 1, offset: .72, easing: "cubic-bezier(.7, 0, .84, 0)" },
      { transform: "translateX(100vw) skewX(-10deg)", opacity: 0 }], { duration: 1350, fill: "forwards" });
  }
  // remove the sting once it has played; a cancel (next ball) rejects the promise, which is fine
  anim.finished.then(() => { if (layer.firstChild === el) layer.replaceChildren(); }, () => {});
  if (reduceMotion || !big) return;
  if (mark === "6") burst(layer);
  if (mark === "4") rope(layer);
  if (mark === "W") el.querySelectorAll(".bail").forEach((b, i) =>
    b.animate([{ transform: "none" }, { transform: `translate(${i ? 16 : -16}px, -30px) rotate(${i ? 75 : -75}deg)`, opacity: 0 }],
      { duration: 700, delay: 300, easing: "cubic-bezier(.2, .7, .4, 1)", fill: "forwards" }));
}

function burst(layer) {   // gold shards fly out from the centre, like a six into the stands
  for (let i = 0; i < 14; i++) {
    const a = (i / 14) * 2 * Math.PI, r = 160 + (i % 3) * 60, shard = document.createElement("span");
    shard.className = "sting__shard";
    layer.append(shard);
    shard.animate([{ transform: `rotate(${a + Math.PI / 2}rad) scale(.3)`, opacity: 1 },
      { transform: `translate(${Math.cos(a) * r}px, ${Math.sin(a) * r}px) rotate(${a + Math.PI / 2}rad) scale(1)`, opacity: 0 }],
      { duration: 950, delay: 250, easing: EASE, fill: "forwards" });
  }
}

function rope(layer) {   // the boundary rope races across under the banner
  const line = document.createElement("span");
  line.className = "sting__rope";
  layer.append(line);
  line.animate([{ transform: "scaleX(0)", opacity: 1 }, { transform: "scaleX(1)", opacity: 1, offset: .6 }, { transform: "scaleX(1)", opacity: 0 }],
    { duration: 1100, easing: EASE, fill: "forwards" });
}

function swing(delta, team) {   // one ball moved the chance by 10+ points
  const tag = $("swing");
  tag.textContent = `Momentum shift ${delta > 0 ? "+" : "−"}${Math.abs(Math.round(delta))}% ${team}`;
  tag.className = `swing swing--${delta > 0 ? "up" : "down"}`;
  tag.hidden = false;
  tag.getAnimations().forEach((a) => a.cancel());
  const anim = tag.animate(reduceMotion ? [{ opacity: 1 }, { opacity: 1 }] :
    [{ opacity: 0, transform: "translateX(-16px)" }, { opacity: 1, transform: "none", offset: .12, easing: EASE }, { opacity: 1, offset: .85 }, { opacity: 0 }],
    { duration: 2600 });
  anim.onfinish = () => { tag.hidden = true; };
}

// Sound is synthesized with Web Audio (no audio files); off until the visitor turns it on.
let audio = null;
let soundOn = false;
function noise(seconds, filterType, freq, peak, attack) {
  const buf = audio.createBuffer(1, audio.sampleRate * seconds, audio.sampleRate);
  const data = buf.getChannelData(0);
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
  const src = audio.createBufferSource(), filter = audio.createBiquadFilter(), gain = audio.createGain(), t = audio.currentTime;
  src.buffer = buf; filter.type = filterType; filter.frequency.value = freq;
  gain.gain.setValueAtTime(0.0001, t);
  gain.gain.exponentialRampToValueAtTime(peak, t + attack);
  gain.gain.exponentialRampToValueAtTime(0.0001, t + seconds);
  src.connect(filter).connect(gain).connect(audio.destination);
  src.start();
}
function tone(freqFrom, freqTo, seconds, peak) {
  const osc = audio.createOscillator(), gain = audio.createGain(), t = audio.currentTime;
  osc.frequency.setValueAtTime(freqFrom, t); osc.frequency.exponentialRampToValueAtTime(freqTo, t + seconds);
  gain.gain.setValueAtTime(peak, t); gain.gain.exponentialRampToValueAtTime(0.0001, t + seconds);
  osc.connect(gain).connect(audio.destination);
  osc.start(); osc.stop(t + seconds);
}
function play(mark) {
  if (!soundOn || !audio) return;
  const crack = () => noise(0.07, "bandpass", 2600, 0.6, 0.003);          // bat on ball
  const roar = (peak, secs) => noise(secs, "lowpass", 900, peak, 0.35);    // crowd
  if (mark === "6") { crack(); roar(0.5, 1.8); }
  else if (mark === "4") { crack(); roar(0.3, 1.2); }
  else if (mark === "W") { tone(140, 55, 0.25, 0.5); noise(0.12, "bandpass", 1400, 0.4, 0.003); roar(0.3, 1.3); }
  else if (["1", "2", "3"].includes(mark)) crack();
  else tone(900, 700, 0.06, 0.08);                                         // dot or wide: a soft tick
}
function toggleSound() {
  soundOn = !soundOn;
  if (soundOn && !audio) audio = new AudioContext();   // created on a click, as browsers require
  $("sound").setAttribute("aria-pressed", String(soundOn));
}

// ---------- wiring ----------
function fill(select, options, chosen) {
  select.replaceChildren(...options.map((o) => new Option(o, o, false, o === chosen)));
}

async function boot() {
  drawStrip(false);
  try {
    const meta = await (await fetch("meta")).json();
    fill($("batting_team"), meta.teams, "Lahore Qalandars");
    fill($("bowling_team"), meta.teams, "Karachi Kings");
    fill($("city"), meta.cities, "Lahore");
    coords = meta.coords;
    const m = meta.test_metrics;
    $("m-auc").textContent = m.roc_auc.toFixed(3);
    $("m-acc").textContent = `${(m.accuracy * 100).toFixed(0)}%`;
    $("m-f1").textContent = m.f1.toFixed(2);
    predict();   // the sample state shows the graphic working on first load
  } catch (e) {
    note(`The predictor service isn't answering (${e.message}). Reload in a moment.`);
  }
}

form.addEventListener("submit", (e) => { e.preventDefault(); predict(); });
form.addEventListener("input", () => {   // a typed edit replaces the logged history
  log = []; undoStack = []; base12 = null;
  $("undo").disabled = true;
  document.querySelectorAll(".key[data-ball]").forEach((k) => { k.disabled = false; });
  drawStrip(false);
});
document.querySelectorAll(".key[data-ball]").forEach((k) => k.addEventListener("click", () => logBall(k.dataset.ball)));
$("undo").addEventListener("click", undo);
$("sound").addEventListener("click", toggleSound);
boot();
