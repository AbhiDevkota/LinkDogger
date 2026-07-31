/* LinkDogger web interface — search, filter and render results.
 * All user/remote data is rendered with textContent (XSS-safe).
 */
"use strict";

const els = {
  form: document.getElementById("search-form"),
  company: document.getElementById("company-input"),
  provider: document.getElementById("provider-select"),
  searchButton: document.getElementById("search-button"),
  sort: document.getElementById("sort-select"),
  role: document.getElementById("role-input"),
  location: document.getElementById("location-input"),
  limit: document.getElementById("limit-input"),
  filterButton: document.getElementById("filter-button"),
  panel: document.getElementById("results-panel"),
  summaryTitle: document.getElementById("summary-title"),
  summaryMeta: document.getElementById("summary-meta"),
  sourceBadges: document.getElementById("source-badges"),
  warnings: document.getElementById("warnings"),
  results: document.getElementById("results"),
  empty: document.getElementById("empty-state"),
  emptyTitle: document.getElementById("empty-title"),
  emptyMessage: document.getElementById("empty-message"),
  suggestions: document.getElementById("suggestions"),
};

const PLATFORM_LABELS = {
  linkedin: "LinkedIn",
  github: "GitHub",
  x: "X",
  website: "Website",
};

const SOURCE_TITLES = {
  ok: "healthy",
  "no-data": "no data",
  partial: "partial",
  unavailable: "unavailable",
  error: "error",
};

function initialsOf(name) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function hashHue(name) {
  let hash = 0;
  for (const char of name) {
    hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  }
  return hash % 360;
}

function formatNumber(value) {
  if (value == null) return "—";
  if (value >= 1_000_000) return (value / 1_000_000).toFixed(1).replace(/\.0$/, "") + "M";
  if (value >= 1_000) return (value / 1_000).toFixed(1).replace(/\.0$/, "") + "k";
  return String(value);
}

function maxFollowers(profiles) {
  let max = null;
  for (const profile of Object.values(profiles)) {
    if (profile && profile.followers != null) {
      max = max === null ? profile.followers : Math.max(max, profile.followers);
    }
  }
  return max;
}

function iconSvg(name) {
  const paths = {
    location:
      '<path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 0 1 16 0z"></path><circle cx="12" cy="10" r="3"></circle>',
    mail: '<rect x="2" y="4" width="20" height="16" rx="2"></rect><path d="m22 7-10 6L2 7"></path>',
  };
  return (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    paths[name] +
    "</svg>"
  );
}

/* ---------- Element helpers (textContent only, never innerHTML) ---------- */

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/* ---------- URL state ---------- */

function currentQuery() {
  const params = new URLSearchParams();
  const company = els.company.value.trim();
  if (company) params.set("q", company);
  const provider = els.provider.value;
  if (provider && provider !== "mock") params.set("provider", provider);
  const sort = els.sort.value;
  if (sort && sort !== "followback-desc") params.set("sort", sort);
  const role = els.role.value.trim();
  if (role) params.set("role", role);
  const location = els.location.value.trim();
  if (location) params.set("location", location);
  const limit = els.limit.value;
  if (limit && limit !== "25") params.set("limit", limit);
  return params;
}

function saveUrlState() {
  const params = currentQuery();
  const qs = params.toString();
  history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
}

function loadUrlState() {
  const params = new URLSearchParams(window.location.search);
  const q = params.get("q");
  if (!q) return false;
  els.company.value = q;
  if (params.has("provider")) els.provider.value = params.get("provider");
  if (params.has("sort")) els.sort.value = params.get("sort");
  if (params.has("role")) els.role.value = params.get("role");
  if (params.has("location")) els.location.value = params.get("location");
  if (params.has("limit")) els.limit.value = params.get("limit");
  return true;
}

/* ---------- Loading, empty and error states ---------- */

function showSkeletons() {
  els.panel.hidden = false;
  els.empty.hidden = true;
  els.results.replaceChildren();
  for (let i = 0; i < 6; i++) {
    const card = el("div", "skeleton-card");
    const row = el("div", "skeleton-row");
    row.appendChild(el("div", "skeleton skeleton-avatar"));
    const lines = el("div");
    lines.style.flex = "1";
    lines.appendChild(el("div", "skeleton skeleton-line w70"));
    lines.appendChild(el("div", "skeleton skeleton-line w45"));
    row.appendChild(lines);
    card.appendChild(row);
    card.appendChild(el("div", "skeleton skeleton-line"));
    card.appendChild(el("div", "skeleton skeleton-line w70"));
    els.results.appendChild(card);
  }
}

function showEmpty(title, message) {
  els.results.replaceChildren();
  els.emptyTitle.textContent = title;
  els.emptyMessage.textContent = message;
  els.empty.hidden = false;
}

function showError(message) {
  els.panel.hidden = false;
  els.summaryTitle.textContent = "Search failed";
  els.summaryMeta.textContent = "";
  els.sourceBadges.replaceChildren();
  els.warnings.hidden = true;
  showEmpty("Something went wrong", message);
}

/* ---------- Rendering ---------- */

function renderSourceBadges(sourceStatus) {
  els.sourceBadges.replaceChildren();
  for (const [platform, status] of Object.entries(sourceStatus)) {
    const label = PLATFORM_LABELS[platform] || platform;
    const badge = el("span", `source-badge ${status}`, `${label} · ${SOURCE_TITLES[status] || status}`);
    badge.title = `${label} enrichment source: ${SOURCE_TITLES[status] || status}`;
    els.sourceBadges.appendChild(badge);
  }
}

function renderWarnings(warnings) {
  if (!warnings || warnings.length === 0) {
    els.warnings.hidden = true;
    els.warnings.replaceChildren();
    return;
  }
  els.warnings.replaceChildren();
  for (const message of warnings) {
    els.warnings.appendChild(el("p", "", message));
  }
  els.warnings.hidden = false;
}

function renderSummary(data) {
  els.panel.hidden = false;
  if (data.company) {
    els.summaryTitle.textContent =
      `${data.count} ${data.count === 1 ? "person" : "people"} at ${data.company.name}`;
    const meta = [`Resolved: ${data.company.name}`];
    if (data.company.domain) meta.push(`Domain: ${data.company.domain}`);
    meta.push(`Generated: ${new Date(data.generated_at).toLocaleString()}`);
    if (data.filtered_out_count > 0) {
      meta.push(`${data.filtered_out_count} excluded by filters`);
    }
    els.summaryMeta.textContent = meta.join("  ·  ");
  } else {
    els.summaryTitle.textContent = `No results for “${data.query}”`;
    els.summaryMeta.textContent = `Generated: ${new Date(data.generated_at).toLocaleString()}`;
  }
  renderSourceBadges(data.source_status || {});
  renderWarnings(data.warnings);
}

function renderPerson(person) {
  const card = el("article", "person-card");

  /* Header: avatar + name + position */
  const top = el("div", "card-top");
  const avatar = el("div", "avatar", initialsOf(person.name));
  avatar.style.background =
    `linear-gradient(135deg, hsl(${hashHue(person.name)} 60% 42%), ` +
    `hsl(${(hashHue(person.name) + 45) % 360} 62% 34%))`;
  avatar.setAttribute("aria-hidden", "true");

  const heading = el("div", "card-heading");
  heading.appendChild(el("h3", "person-name", person.name));
  const positionBits = [person.position, person.company].filter(Boolean);
  if (positionBits.length > 0) {
    const position = el("p", "person-position");
    position.appendChild(el("span", "", person.position || ""));
    if (person.position && person.company) position.appendChild(document.createTextNode(" at "));
    if (person.company) position.appendChild(el("span", "company-name", person.company));
    heading.appendChild(position);
  }
  top.appendChild(avatar);
  top.appendChild(heading);
  card.appendChild(top);

  /* Details: location, email */
  const details = [];
  if (person.location) details.push([iconSvg("location"), person.location]);
  if (person.email) details.push([iconSvg("mail"), person.email]);
  if (details.length > 0) {
    const row = el("div", "person-details");
    for (const [icon, text] of details) {
      const span = el("span");
      span.innerHTML = icon;
      span.appendChild(el("span", "", text));
      row.appendChild(span);
    }
    card.appendChild(row);
  }

  /* Bio */
  if (person.bio) {
    card.appendChild(el("p", "person-bio", person.bio));
  }

  /* Stats: followers, networking score, influence */
  const followers = maxFollowers(person.profiles || {});
  const networking = person.networking || {};
  const stats = el("div", "card-stats");
  const statBlocks = [
    ["Followers", formatNumber(followers)],
    ["Network", formatNumber(networking.networking_score)],
    ["Influence", formatNumber(networking.influence_score)],
  ];
  for (const [label, value] of statBlocks) {
    const stat = el("div", "stat");
    stat.appendChild(el("div", "stat-value", value));
    stat.appendChild(el("div", "stat-label", label));
    stats.appendChild(stat);
  }
  card.appendChild(stats);

  if (networking.networking_score != null) {
    const bar = el("div", "score-bar");
    const fill = el("div", "score-bar-fill");
    fill.style.width = `${Math.min(100, Math.max(0, networking.networking_score))}%`;
    bar.appendChild(fill);
    card.appendChild(bar);
  }

  /* Pills: follow-back likelihood + profile links */
  const pills = el("div", "pill-row");
  if (networking.follow_back_likelihood != null) {
    const likelihood = networking.follow_back_likelihood;
    const pill = el(
      "span",
      `pill followback${likelihood < 50 ? " weak" : ""}`,
      `Follow-back ${likelihood}%`
    );
    pill.title = "Estimated likelihood this person follows back";
    pills.appendChild(pill);
  }
  for (const [platform, profile] of Object.entries(person.profiles || {})) {
    if (!profile) continue;
    const label = PLATFORM_LABELS[platform] || platform;
    if (profile.url) {
      const link = el("a", "pill", label);
      link.href = profile.url;
      link.target = "_blank";
      link.rel = "noopener";
      pills.appendChild(link);
    } else if (profile.username) {
      pills.appendChild(el("span", "pill", `${label}: @${profile.username}`));
    }
  }
  if (pills.childElementCount > 0) card.appendChild(pills);

  /* Footer: sources */
  if (person.sources && person.sources.length > 0) {
    const footer = el("div", "card-footer");
    footer.appendChild(el("span", "", `Sources: ${person.sources.join(", ")}`));
    footer.appendChild(el("span", "", `${Object.keys(person.profiles || {}).length} profile(s)`));
    card.appendChild(footer);
  }

  return card;
}

function render(data) {
  renderSummary(data);
  if (!data.results || data.results.length === 0) {
    if (!data.company) {
      showEmpty(
        "Company not found",
        `We couldn't resolve “${data.query}”. Try a different company name.`
      );
    } else {
      showEmpty("No people match", "Try clearing the role or location filters.");
    }
    return;
  }
  els.empty.hidden = true;
  els.results.replaceChildren();
  for (const person of data.results) {
    els.results.appendChild(renderPerson(person));
  }
}

/* ---------- Search flow ---------- */

async function runSearch() {
  const company = els.company.value.trim();
  if (!company) return;

  showSkeletons();
  saveUrlState();
  els.searchButton.disabled = true;
  els.searchButton.textContent = "Searching…";

  const params = new URLSearchParams({ company });
  const provider = els.provider.value;
  if (provider && provider !== "mock") params.set("provider", provider);
  const role = els.role.value.trim();
  if (role) params.set("role", role);
  const location = els.location.value.trim();
  if (location) params.set("location", location);
  const limit = els.limit.value;
  if (limit) params.set("limit", limit);
  params.set("sort", els.sort.value);

  try {
    const response = await fetch(`/api/search?${params.toString()}`);
    if (!response.ok) {
      let detail = `Request failed (${response.status})`;
      try {
        const body = await response.json();
        if (body && body.detail) detail = body.detail;
      } catch (_) {
        /* non-JSON error body */
      }
      throw new Error(detail);
    }
    render(await response.json());
  } catch (error) {
    showError(error.message || "Unexpected error");
  } finally {
    els.searchButton.disabled = false;
    els.searchButton.textContent = "Search";
  }
}

/* ---------- Events ---------- */

els.form.addEventListener("submit", (event) => {
  event.preventDefault();
  runSearch();
});

els.suggestions.addEventListener("click", (event) => {
  const chip = event.target.closest(".chip");
  if (!chip) return;
  els.company.value = chip.dataset.company;
  runSearch();
});

els.provider.addEventListener("change", () => {
  if (els.company.value.trim()) runSearch();
});

els.sort.addEventListener("change", () => {
  if (els.company.value.trim()) runSearch();
});

els.filterButton.addEventListener("click", runSearch);

if (loadUrlState()) {
  runSearch();
} else {
  els.company.focus();
}
