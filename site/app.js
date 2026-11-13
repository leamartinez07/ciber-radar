"use strict";

// El HTML ya trae todas las noticias. Esto solo agrega tiempos relativos, búsqueda y filtros.
const TZ = "America/Argentina/Buenos_Aires";
const STALE_AFTER_MS = 30 * 60 * 1000;
const MAX_RESULTS = 80;
const EN = document.documentElement.lang.startsWith("en");
const T = EN ? {
  locale: "en-US", regions: { ar: "Argentina", latam: "Latin America", mundo: "World" }, alert: "Alert",
  categories: { Filtraciones: "Data breaches", Estafas: "Scams", "Deepfakes e IA": "Deepfakes & AI",
    Vulnerabilidades: "Vulnerabilities", "Estado y defensa": "Government & defense" },
  now: "just now", minutes: (n) => `${n} min ago`, hours: (n) => `${n} h ago`, today: "Today", yesterday: "Yesterday",
  fresh: "NEW", offline: "Search failed. Check your connection.", results: (n) => (n === 1 ? "1 result" : `${n} results`), within: " in ",
  themes: { light: "light", dark: "dark" }, theme: "Theme", switchTo: "Switch to",
} : {
  locale: "es-AR", regions: { ar: "Argentina", latam: "Latinoamérica", mundo: "Mundo" }, alert: "Alerta", categories: {},
  now: "recién", minutes: (n) => `hace ${n} min`, hours: (n) => `hace ${n} h`, today: "Hoy", yesterday: "Ayer",
  fresh: "NUEVO", offline: "No se pudo buscar. Revisá la conexión.", results: (n) => (n === 1 ? "1 resultado" : `${n} resultados`), within: " en ",
  themes: { light: "claro", dark: "oscuro" }, theme: "Tema", switchTo: "Cambiar a",
};

const $ = (id) => document.getElementById(id);
const dayKey = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
const longDay = new Intl.DateTimeFormat(T.locale, { timeZone: TZ, weekday: "long", day: "numeric", month: "long", year: "numeric" });
const shortDate = new Intl.DateTimeFormat(T.locale, { timeZone: TZ, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const loadedAt = Date.now();

function storageGet(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function storageSet(key, value) {
  try { localStorage.setItem(key, value); } catch { /* el modo privado puede bloquearlo */ }
}

function capitalize(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function normalize(text) {
  return text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function relative(iso) {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return T.now;
  if (minutes < 60) return T.minutes(minutes);
  if (minutes < 24 * 60) return T.hours(Math.round(minutes / 60));
  return null;
}

function refreshTimes(root = document) {
  root.querySelectorAll("time[data-rel]").forEach((node) => {
    const label = relative(node.dateTime);
    if (label) node.textContent = label;
  });
}

function refreshDays() {
  const today = dayKey.format(new Date());
  const yesterday = dayKey.format(new Date(Date.now() - 864e5));
  document.querySelectorAll("[data-day]").forEach((node) => {
    if (node.dataset.day === today) node.textContent = T.today;
    else if (node.dataset.day === yesterday) node.textContent = T.yesterday;
  });
  $("today").textContent = capitalize(longDay.format(new Date()));
}

function markNew(lastVisit) {
  if (!lastVisit) return;
  document.querySelectorAll("article[data-seen]").forEach((node) => {
    if (node.dataset.seen > lastVisit) node.querySelector(".meta").append(" · ", el("span", "new", T.fresh));
  });
}

function storyNode(item) {
  const node = el("article", "story");
  node.dataset.region = item.region;
  const tags = el("p", "tags");
  tags.append(el("span", `chip chip-${item.region}`, T.regions[item.region] || item.region));
  if (item.alert) tags.append(el("span", "flag", T.alert));
  node.append(tags);
  const title = el("h3");
  const link = el("a", "", item.title);
  link.href = /^https?:\/\//i.test(item.url) ? item.url : "#";
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  title.append(link);
  const pageLang = EN ? "en" : "es";
  if (item.lang && item.lang !== pageLang) title.lang = item.lang;
  node.append(title);
  if (item.summary) node.append(el("p", "summary", item.summary));
  const meta = el("p", "meta");
  if (item.category !== "General") meta.append(el("span", "subject", T.categories[item.category] || item.category), " · ");
  meta.append(`${item.source} `, el("span", "when", `· ${relative(item.published) || shortDate.format(new Date(item.published))}`));
  node.append(meta);
  return node;
}

let index = null;
async function loadIndex() {
  if (!index) {
    const response = await fetch("/data/latest.json");
    if (!response.ok) throw new Error(String(response.status));
    index = (await response.json()).items;
  }
  return index;
}

function showPage() {
  $("results").hidden = true;
  $("results").replaceChildren();
  $("page").hidden = false;
}

function showResults(nodes, message) {
  const results = $("results");
  const grid = el("div", "day-grid");
  grid.append(...nodes);
  results.replaceChildren(el("h2", "day", message), grid);
  results.hidden = false;
  $("page").hidden = true;
}

let searchRun = 0;
function inCurrentSection(item) {
  const view = $("contenido").dataset.view;
  if (view === "alert") return item.alert;
  return view ? item.region === view : true;
}

async function search(raw) {
  const run = ++searchRun;
  const words = normalize(raw.trim()).split(/\s+/).filter(Boolean);
  const topic = $("category").value;
  if (!words.length && !topic) {
    showPage();
    return;
  }
  let items;
  try {
    items = await loadIndex();
  } catch {
    if (run === searchRun) showResults([], T.offline);
    return;
  }
  if (run !== searchRun) return;
  const found = items.filter((item) => {
    if (!inCurrentSection(item) || (topic && item.category !== topic)) return false;
    const text = normalize(`${item.title} ${item.summary} ${item.source}`);
    return words.every((word) => text.includes(word));
  });
  const count = T.results(found.length);
  const quoted = EN ? `“${raw.trim()}”` : `«${raw.trim()}»`;
  const label = [raw.trim() && quoted, topic && (T.categories[topic] || topic)].filter(Boolean).join(T.within);
  showResults(found.slice(0, MAX_RESULTS).map(storyNode), `${count}: ${label}`);
}

function bindSearch() {
  const query = $("query");
  if (!query) return; // la página de vulnerabilidades no tiene buscador
  let timer;
  query.addEventListener("input", (event) => {
    clearTimeout(timer);
    timer = setTimeout(() => search(event.target.value), 150);
  });
  query.addEventListener("focus", () => loadIndex().catch(() => {}), { once: true });
  $("category").addEventListener("change", () => search(query.value));
  document.querySelector(".tools").addEventListener("submit", (event) => event.preventDefault());
}

// Filtro de la página de vulnerabilidades: oculta las filas que no coinciden.
function bindVulnFilter() {
  const input = $("vuln-filter");
  if (!input) return;
  const rows = [...document.querySelectorAll(".vuln-table tbody tr")].map((row) => [row, normalize(row.textContent)]);
  input.addEventListener("input", () => {
    const words = normalize(input.value.trim()).split(/\s+/).filter(Boolean);
    let shown = 0;
    for (const [row, text] of rows) {
      row.hidden = !words.every((word) => text.includes(word));
      if (!row.hidden) shown += 1;
    }
    document.querySelectorAll(".vuln-block").forEach((block) => {
      block.hidden = !block.querySelector("tbody tr:not([hidden])");
    });
    $("vuln-empty").hidden = shown > 0;
  });
  input.form.addEventListener("submit", (event) => event.preventDefault());
}

function bind() {
  bindSearch();
  bindVulnFilter();
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    const searching = $("query")?.value || $("category")?.value;
    if (Date.now() - loadedAt > STALE_AFTER_MS && !searching) location.reload();
    else refreshTimes();
  });
}

// Tema: claro (el de entrada) u oscuro. theme.js lo aplica antes de pintar. No sigue al sistema.
const THEME_COLORS = { light: "#ffffff", dark: "#101010" };

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  document.querySelectorAll('meta[name="theme-color"]').forEach((meta) => { meta.content = THEME_COLORS[theme]; });
  const next = theme === "dark" ? "light" : "dark";
  const button = $("theme");
  button.setAttribute("aria-label", `${T.theme}: ${T.themes[theme]}. ${T.switchTo} ${T.themes[next]}`);
  button.title = `${T.theme}: ${T.themes[theme]}`;
}

function bindTheme() {
  const button = $("theme");
  if (!button) return;
  let theme = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
  applyTheme(theme);
  button.addEventListener("click", () => {
    theme = theme === "dark" ? "light" : "dark";
    applyTheme(theme);
    storageSet("ciber-radar:theme", theme);
  });
}

function registerWorker() {
  if (!("serviceWorker" in navigator)) return;
  const policy = window.trustedTypes?.createPolicy("radar", {
    createScriptURL: (url) => (url === "/sw.js" ? url : ""),
  });
  const url = policy ? policy.createScriptURL("/sw.js") : "/sw.js";
  window.addEventListener("load", () => {
    navigator.serviceWorker.register(url).catch(() => { /* la app funciona igual sin esto */ });
  });
}

// En celular el menú se desplaza: deja a la vista la sección actual.
function revealCurrentSection() {
  const nav = document.querySelector(".sections");
  const current = nav?.querySelector('[aria-current="page"]');
  if (!current || nav.scrollWidth <= nav.clientWidth) return;
  nav.scrollLeft = current.offsetLeft - (nav.clientWidth - current.offsetWidth) / 2;
}

function start() {
  markNew(storageGet("ciber-radar:last-visit"));
  storageSet("ciber-radar:last-visit", new Date().toISOString().slice(0, 19) + "+00:00");
  refreshTimes();
  refreshDays();
  bind();
  bindTheme();
  revealCurrentSection();
  registerWorker();
}

start();
