// Search page. Safety rule: scraped text is only ever inserted as text (textContent via el()),
// never as HTML, and links are only followed when they are http(s). See PLAN.md section 11.
"use strict";

const PAGE_SIZE = 100; // the API maximum: a normal 7-day window (about 70 ads) fits on one page
const POLL_MS = 2000;
const FILTERS = ["date_from", "date_to", "q", "tag"];
const tehranTime = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Tehran", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
});
const jalaliDay = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
  timeZone: "UTC", year: "numeric", month: "long", day: "numeric",
});

const $ = (id) => document.getElementById(id);
const state = { page: 1, selected: null, polling: null };

// Build an element; children are elements or strings (strings become text nodes, never markup).
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "onclick") node.addEventListener("click", value);
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child !== null && child !== undefined) node.append(child instanceof Node ? child : String(child));
  }
  return node;
}

function safeUrl(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok && response.status !== 409) {
    throw new Error(typeof data.detail === "string" ? data.detail : `HTTP ${response.status}`);
  }
  return { status: response.status, data };
}

const utcTime = (iso) => iso ? iso.replace("T", " ").replace("Z", " UTC") : "—";
const tehran = (iso) => iso ? tehranTime.format(new Date(iso)) : "—";
const jalaliOf = (day) => day ? jalaliDay.format(new Date(day + "T00:00:00Z")) : "";
const jalaliShort = (day) => new Intl.DateTimeFormat("fa-IR-u-ca-persian", { timeZone: "UTC", month: "short", day: "numeric" })
  .format(new Date(day + "T00:00:00Z"));
const pct = (value) => value === null || value === undefined ? "—" : `${value}%`;
const badge = (status) => el("span", { class: `badge ${status}` }, status.replaceAll("_", " "));

function tagChips(tags) {
  return el("div", { class: "chips" },
    tags.map((t) => el("span", { class: `chip ${t.kind}`, dir: "auto", title: `${t.kind}: ${t.slug}` }, t.label || t.slug)));
}

// --- filters <-> page URL -------------------------------------------------------------------

function filtersFromForm() {
  const form = $("search");
  const { date_from: from, date_to: to } = form.elements;
  if (from.value && to.value && from.value > to.value) [from.value, to.value] = [to.value, from.value]; // swapped dates
  const filters = {};
  for (const name of FILTERS) {
    const value = form.elements[name].value.trim();
    if (value) filters[name] = value;
  }
  return filters;
}

function showJalaliBesideDates() {
  for (const span of document.querySelectorAll(".jalali")) {
    span.textContent = jalaliOf($("search").elements[span.dataset.for].value);
  }
}

function writeUrl(filters) {
  const params = new URLSearchParams(filters);
  if (state.page > 1) params.set("page", state.page);
  history.replaceState(null, "", params.toString() ? `?${params}` : location.pathname);
}

function readUrl() {
  const params = new URLSearchParams(location.search);
  for (const name of FILTERS) $("search").elements[name].value = params.get(name) || "";
  state.page = Math.max(1, parseInt(params.get("page"), 10) || 1);
  showJalaliBesideDates();
}

// --- results and detail ---------------------------------------------------------------------

async function search() {
  const filters = filtersFromForm();
  writeUrl(filters);
  const params = new URLSearchParams({ ...filters, page: state.page, page_size: PAGE_SIZE });
  $("search-error").hidden = true;
  let data;
  try {
    ({ data } = await api(`/api/postings?${params}`));
  } catch (error) {
    $("search-error").textContent = error.message;
    $("search-error").hidden = false;
    return;
  }
  const lastPage = Math.max(1, Math.ceil(data.total / data.page_size));
  if (data.page > lastPage) { // e.g. ?page=999 from an old or edited link: go to the last real page
    state.page = lastPage;
    return search();
  }
  const first = data.total ? (data.page - 1) * data.page_size + 1 : 0;
  const last = Math.min(data.total, data.page * data.page_size);
  const filtered = Object.keys(filters).length > 0;
  $("showing").textContent = data.total ? `Showing ${first}–${last} of ${data.total}` : "";
  $("empty").hidden = data.total > 0;
  $("empty").textContent = filtered
    ? "No postings match these filters. Press “Show all” to see every posting."
    : "No postings stored yet. Press “Collect now” to collect the last 7 days.";
  $("pager").hidden = lastPage <= 1;
  $("results").replaceChildren(...data.items.map((item) => el("li", {
    class: item.id === state.selected ? "selected" : "",
    "data-id": item.id,
    onclick: () => showDetail(item.id),
  },
    el("div", { class: "title", dir: "auto" }, item.title),
    el("div", { class: "meta" }, el("span", { dir: "rtl" }, jalaliOf(item.published_date_tehran)),
      ` · ${item.published_date_tehran} (Tehran)`),
    tagChips(item.tags),
    el("div", { class: "snippet", dir: "auto" }, item.snippet),
  )));
  $("prev").disabled = data.page <= 1;
  $("next").disabled = last >= data.total;
  highlightDay(filters);
}

async function showDetail(id) {
  const { data } = await api(`/api/postings/${id}`);
  state.selected = id;
  for (const li of $("results").children) li.classList.toggle("selected", Number(li.dataset.id) === id);
  $("detail").hidden = false;
  document.body.classList.add("detail-open");
  $("detail-title").textContent = data.title;
  $("detail-meta").replaceChildren("Published ", el("span", { dir: "rtl" }, jalaliOf(data.published_date_tehran)),
    ` · ${data.published_date_tehran} (Tehran) · collected ${utcTime(data.collected_at)} · updated ${utcTime(data.updated_at)}`);
  $("detail-tags").replaceChildren(tagChips(data.tags));
  $("detail-note").hidden = !data.members_only_omitted;
  $("detail-body").textContent = data.body;
  const link = $("detail-link");
  const href = safeUrl(data.url);
  link.hidden = !href;
  if (href) link.href = href;
  else link.removeAttribute("href");
  $("detail").scrollTop = 0;
}

function closeDetail() {
  $("detail").hidden = true;
  document.body.classList.remove("detail-open");
}

// --- per-day bars and tags ------------------------------------------------------------------

async function loadStats() {
  const { data } = await api("/api/stats");
  const colour = (key) => `var(--g-${key})`;
  const totals = Object.fromEntries(data.groups.map((g) => [g.key, 0]));
  for (const day of data.days) for (const [key, n] of Object.entries(day.groups)) totals[key] += n;
  const shown = data.groups.filter((g) => totals[g.key] > 0); // colours stay fixed per group, never re-assigned

  $("legend").replaceChildren(...shown.map((g) => {
    const swatch = el("span", { class: "swatch" });
    swatch.style.background = colour(g.key); // CSSOM, allowed by the CSP
    return el("span", { class: "legend-item" }, swatch, `${g.label} `, el("span", { class: "muted" }, `(${totals[g.key]})`));
  }));

  const most = Math.max(1, ...data.days.map((d) => d.count));
  $("days").replaceChildren(...data.days.map((day) => {
    const stack = el("div", { class: "stack" }, shown.filter((g) => day.groups[g.key]).map((g) => {
      const seg = el("div", { class: "seg" });
      seg.style.background = colour(g.key);
      seg.style.flex = `${day.groups[g.key]} 1 0`;
      return seg;
    }));
    const share = day.count / most; // the tallest day fills the plot, leaving room for its count label
    stack.style.height = `calc(${share * 100}% - ${share * 26}px)`;
    const parts = shown.filter((g) => day.groups[g.key]).map((g) => `${g.label} ${day.groups[g.key]}`).join(", ");
    const button = el("button", {
      type: "button", class: "day", "data-date": day.date,
      "aria-label": `${day.date}: ${day.count} postings${parts ? ` (${parts})` : ""}. Show them.`,
      onclick: () => filterDay(day.date),
    }, el("div", { class: "plot" }, el("span", { class: "count" }, day.count), stack),
      el("span", { class: "label", dir: "rtl" }, jalaliShort(day.date)), el("span", { class: "label greg" }, day.date.slice(5)));
    button.addEventListener("mouseenter", () => showTooltip(button, day, shown));
    button.addEventListener("focus", () => showTooltip(button, day, shown));
    button.addEventListener("mouseleave", () => { $("tooltip").hidden = true; });
    button.addEventListener("blur", () => { $("tooltip").hidden = true; });
    return button;
  }));

  $("days-table").replaceChildren(
    el("thead", {}, el("tr", {}, el("th", {}, "Tehran day"), shown.map((g) => el("th", {}, g.label)), el("th", {}, "Total"))),
    el("tbody", {}, data.days.map((day) => el("tr", {},
      el("td", {}, el("span", { dir: "rtl" }, jalaliOf(day.date)), ` · ${day.date}`),
      shown.map((g) => el("td", {}, day.groups[g.key])), el("td", {}, el("strong", {}, day.count))))),
  );
  highlightDay(filtersFromForm());
}

function showTooltip(button, day, shown) {
  const tip = $("tooltip");
  const rows = shown.filter((g) => day.groups[g.key]).map((g) => {
    const swatch = el("span", { class: "swatch" });
    swatch.style.background = `var(--g-${g.key})`;
    return el("div", { class: "tt-row" }, swatch, el("span", {}, g.label), el("span", { class: "tt-n" }, day.groups[g.key]));
  });
  tip.replaceChildren(
    el("div", { class: "tt-title" }, el("span", { dir: "rtl" }, jalaliOf(day.date)), ` · ${day.date}`),
    ...(rows.length ? rows : [el("div", {}, "No postings")]),
    el("div", { class: "tt-row" }, el("strong", {}, "Total"), el("strong", { class: "tt-n" }, day.count)),
  );
  tip.hidden = false;
  const chart = tip.parentElement.getBoundingClientRect();
  const box = button.getBoundingClientRect();
  const left = box.left - chart.left + box.width / 2 - tip.offsetWidth / 2;
  tip.style.left = `${Math.max(0, Math.min(left, chart.width - tip.offsetWidth))}px`;
  tip.style.top = "0px";
}

function filterDay(day) {
  const form = $("search");
  form.elements.date_from.value = day;
  form.elements.date_to.value = day;
  showJalaliBesideDates();
  state.page = 1;
  search();
}

function highlightDay(filters) {
  for (const bar of $("days").children) {
    bar.classList.toggle("active", filters.date_from === bar.dataset.date && filters.date_to === bar.dataset.date);
  }
}

async function loadTags() {
  const { data } = await api("/api/tags");
  const select = $("search").elements.tag;
  const chosen = select.value || new URLSearchParams(location.search).get("tag") || "";
  select.replaceChildren(el("option", { value: "" }, "Any tag"),
    ...data.items.map((t) => el("option", { value: t.slug }, `${t.label || t.slug} · ${t.kind === "province" ? "province" : "field"} (${t.count})`)));
  select.value = chosen;
}

// --- runs, Collect now ----------------------------------------------------------------------

const tehranDay = (iso) => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tehran" }).format(new Date(iso));

function tile(label, value, sub, kind = "") {
  return el("div", { class: `tile ${kind}` },
    el("span", { class: "tile-label" }, label), el("span", { class: "tile-value" }, value),
    sub ? el("span", { class: "tile-sub" }, sub) : null);
}

function showLastRun(run) {
  if (!run) {
    $("run-status").replaceChildren(tile("Last run", "None yet", "Press Collect now to collect the last 7 days", "wide"));
    return;
  }
  const first = run.window_start ? tehranDay(run.window_start) : null;
  const last = run.window_end ? tehranDay(new Date(Date.parse(run.window_end) - 1000).toISOString()) : null;
  $("run-status").replaceChildren(
    tile("Last run", badge(run.status), `#${run.id} · ${tehran(run.started_at)}`, "main"),
    tile("Window (Tehran days)", first ? el("span", { dir: "rtl" }, `${jalaliShort(first)} – ${jalaliShort(last)}`) : "—",
      first ? `${first} → ${last.slice(5)}` : "", "main"),
    tile("New", run.new), tile("Updated", run.updated), tile("Unchanged", run.unchanged), tile("Rejected", run.rejected),
  );
}

async function loadRuns() {
  const { data } = await api("/api/runs?limit=10");
  showLastRun(data.items[0]);
  $("runs").replaceChildren(...data.items.map((run) => el("tr", { "data-id": run.id, onclick: () => showRunIssues(run.id) },
    el("td", {}, run.id), el("td", {}, tehran(run.started_at)), el("td", {}, badge(run.status)),
    el("td", {}, run.new), el("td", {}, run.updated), el("td", {}, run.unchanged), el("td", {}, run.rejected),
    el("td", {}, `${run.errors} / ${run.warnings}`), el("td", {}, run.cards_per_page_avg ?? "—"),
    el("td", {}, pct(run.date_ok_pct)), el("td", {}, pct(run.body_ok_pct)), el("td", {}, pct(run.tags_ok_pct)),
  )));
  const running = data.items.find((run) => run.status === "running");
  if (running && !state.polling) follow(running.id);
  return data.items;
}

async function showRunIssues(id) {
  const { data } = await api(`/api/runs/${id}`);
  for (const row of $("runs").children) row.classList.toggle("selected", Number(row.dataset.id) === id);
  const box = $("run-issues");
  box.hidden = false;
  if (!data.issues.length) {
    box.replaceChildren(el("p", {}, `Run #${id}: no issues.`));
    return;
  }
  // Every issue is listed; big groups start folded so the list stays readable.
  box.replaceChildren(el("p", {}, `Run #${id} issues by code:`), ...data.issues.map((group) => {
    const details = el("details", {},
      el("summary", {}, el("strong", {}, `${group.code} `), el("span", { class: "muted" }, `${group.severity} × ${group.count}`)),
      el("ul", {}, group.items.map((issue) => {
        const href = safeUrl(issue.url);
        return el("li", {}, issue.detail.split("\n")[0], " ",
          href ? el("a", { href, rel: "noopener noreferrer", target: "_blank" }, issue.url) : "",
          issue.snapshot_path ? el("span", { class: "muted" }, ` · saved page: ${issue.snapshot_path}`) : "");
      })));
    details.open = group.count <= 20;
    return details;
  }));
}

async function collectNow() {
  $("collect").disabled = true;
  try {
    const { status, data } = await api("/api/runs", { method: "POST", headers: { "X-Collect-Trigger": "1" } });
    if (status === 409 && data.run_id) {
      showProgress(`A run is already in progress (#${data.run_id}); following it.`);
    }
    follow(data.run_id);
  } catch (error) {
    showProgress(`Could not start: ${error.message}`);
    $("collect").disabled = false;
  }
}

function showProgress(...parts) {
  $("progress").hidden = false;
  $("progress-text").replaceChildren(...parts);
}

function follow(id) {
  if (!id) return;
  $("collect").disabled = true;
  clearInterval(state.polling);
  const tick = async () => {
    const { data: run } = await api(`/api/runs/${id}`);
    const codes = run.issues.map((g) => `${g.code} ×${g.count}`).join(", ");
    if (run.status === "running") {
      showProgress(`Run #${id} running · ${run.pages_listing} listing pages, ${run.pages_posting} postings read · ` +
        `${run.errors} errors, ${run.warnings} warnings so far`);
      return;
    }
    clearInterval(state.polling);
    state.polling = null;
    $("collect").disabled = false;
    showProgress(`Run #${id} finished: `, badge(run.status),
      ` · ${run.new} new, ${run.updated} updated, ${run.unchanged} unchanged, ${run.rejected} rejected`,
      codes ? ` · issues: ${codes}` : " · no issues");
    await refresh();
  };
  state.polling = setInterval(() => tick().catch(() => {}), POLL_MS);
  tick().catch(() => {});
}

async function refresh() {
  await Promise.all([loadRuns(), loadStats(), loadTags()]);
  await search();
}

// --- wiring ---------------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  readUrl();
  $("search").addEventListener("submit", (event) => {
    event.preventDefault();
    state.page = 1;
    search();
  });
  $("search").addEventListener("input", showJalaliBesideDates);
  $("show-all").addEventListener("click", () => {
    $("search").reset();
    showJalaliBesideDates();
    state.page = 1;
    search();
  });
  $("prev").addEventListener("click", () => { state.page -= 1; search(); });
  $("next").addEventListener("click", () => { state.page += 1; search(); });
  $("collect").addEventListener("click", collectNow);
  $("detail-close").addEventListener("click", closeDetail);
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeDetail(); });
  refresh().catch((error) => showProgress(`Could not load data: ${error.message}`));
});
