"use strict";

// El HTML ya trae todas las noticias. Esto solo agrega tiempos relativos, búsqueda y filtros.
const TZ = "America/Argentina/Buenos_Aires";
const STALE_AFTER_MS = 30 * 60 * 1000;
const MAX_RESULTS = 80;
const REGIONS = { ar: "Argentina", latam: "Latinoamérica", mundo: "Mundo" };

const $ = (id) => document.getElementById(id);
const dayKey = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
const longDay = new Intl.DateTimeFormat("es-AR", { timeZone: TZ, weekday: "long", day: "numeric", month: "long", year: "numeric" });
const shortDate = new Intl.DateTimeFormat("es-AR", { timeZone: TZ, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
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
  if (minutes < 1) return "recién";
  if (minutes < 60) return `hace ${minutes} min`;
  if (minutes < 24 * 60) return `hace ${Math.round(minutes / 60)} h`;
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
    if (node.dataset.day === today) node.textContent = "Hoy";
    else if (node.dataset.day === yesterday) node.textContent = "Ayer";
  });
  $("today").textContent = capitalize(longDay.format(new Date()));
}

function markNew(lastVisit) {
  if (!lastVisit) return;
  document.querySelectorAll("article[data-seen]").forEach((node) => {
    if (node.dataset.seen > lastVisit) node.querySelector(".meta").append(" · ", el("span", "new", "NUEVO"));
  });
}

function storyNode(item) {
  const node = el("article", "story");
  const topic = item.category === "General" ? REGIONS[item.region] : item.category;
  node.append(el("p", item.alert ? "kicker is-alert" : "kicker", item.alert ? `Alerta · ${topic}` : topic));
  const title = el("h3");
  const link = el("a", "", item.title);
  link.href = /^https?:\/\//i.test(item.url) ? item.url : "#";
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  title.append(link);
  if (item.lang && item.lang !== "es") title.lang = item.lang;
  node.append(title);
  if (item.summary) node.append(el("p", "summary", item.summary));
  node.append(el("p", "meta", `${item.source} · ${relative(item.published) || shortDate.format(new Date(item.published))}`));
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
    if (run === searchRun) showResults([], "No se pudo buscar. Revisá la conexión.");
    return;
  }
  if (run !== searchRun) return;
  const found = items.filter((item) => {
    if (!inCurrentSection(item) || (topic && item.category !== topic)) return false;
    const text = normalize(`${item.title} ${item.summary} ${item.source}`);
    return words.every((word) => text.includes(word));
  });
  const count = found.length === 1 ? "1 resultado" : `${found.length} resultados`;
  const label = [raw.trim() && `«${raw.trim()}»`, topic].filter(Boolean).join(" en ");
  showResults(found.slice(0, MAX_RESULTS).map(storyNode), `${count}: ${label}`);
}

function bind() {
  let timer;
  $("query").addEventListener("input", (event) => {
    clearTimeout(timer);
    timer = setTimeout(() => search(event.target.value), 150);
  });
  $("query").addEventListener("focus", () => loadIndex().catch(() => {}), { once: true });
  $("category").addEventListener("change", () => search($("query").value));
  document.querySelector(".tools").addEventListener("submit", (event) => event.preventDefault());
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    if (Date.now() - loadedAt > STALE_AFTER_MS && !$("query").value && !$("category").value) location.reload();
    else refreshTimes();
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

function start() {
  markNew(storageGet("ciber-radar:last-visit"));
  storageSet("ciber-radar:last-visit", new Date().toISOString().slice(0, 19) + "+00:00");
  refreshTimes();
  refreshDays();
  bind();
  registerWorker();
}

start();
