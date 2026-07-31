/* LinkDogger web interface.
   All dynamic content is built with textContent to avoid XSS from
   external profile data. */

const form = document.getElementById("search-form");
const companyInput = document.getElementById("company-input");
const sortSelect = document.getElementById("sort-select");
const roleInput = document.getElementById("role-input");
const locationInput = document.getElementById("location-input");
const statusBox = document.getElementById("status");
const resultsBox = document.getElementById("results");

function setStatus(message, isError) {
  statusBox.hidden = !message;
  statusBox.textContent = message || "";
  statusBox.classList.toggle("error", Boolean(isError));
}

function formatFollowers(count) {
  if (count === null || count === undefined) return "-";
  if (count >= 1000000) return (count / 1000000).toFixed(1) + "M";
  if (count >= 1000) return (count / 1000).toFixed(1) + "K";
  return String(count);
}

function scorePill(value) {
  const pill = document.createElement("span");
  pill.className = "score-pill";
  if (value === null || value === undefined) {
    pill.textContent = "-";
    return pill;
  }
  pill.classList.add(value >= 70 ? "high" : value >= 40 ? "mid" : "low");
  pill.textContent = String(value);
  return pill;
}

function buildCard(person) {
  const card = document.createElement("article");
  card.className = "card";

  const name = document.createElement("h3");
  name.textContent = person.name;
  card.appendChild(name);

  const role = document.createElement("p");
  role.className = "role";
  const company = person.company || "Unknown company";
  role.textContent = person.position
    ? `${person.position} @ ${company}`
    : company;
  card.appendChild(role);

  const meta = document.createElement("div");
  meta.className = "meta";

  const net = person.networking || {};
  const metaItems = [
    ["Location", person.location || "-"],
    ["Followers", formatFollowers(maxFollowers(person))],
    ["Networking", null],
    ["Follow-back", net.follow_back_likelihood ?? "-"],
  ];
  for (const [label, value] of metaItems) {
    const span = document.createElement("span");
    const b = document.createElement("b");
    b.textContent = `${label}: `;
    span.appendChild(b);
    if (label === "Networking") {
      span.appendChild(scorePill(net.networking_score ?? null));
    } else {
      span.appendChild(document.createTextNode(String(value)));
    }
    meta.appendChild(span);
  }
  card.appendChild(meta);

  const links = document.createElement("div");
  links.className = "links";
  for (const platform of ["linkedin", "github", "x", "website"]) {
    const profile = person.profiles[platform];
    if (!profile || !profile.url) continue;
    const anchor = document.createElement("a");
    anchor.href = profile.url;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    anchor.textContent = platform === "x" ? "X" : platform;
    links.appendChild(anchor);
  }
  card.appendChild(links);

  const sources = document.createElement("p");
  sources.className = "sources";
  sources.textContent = `Sources: ${(person.sources || []).join(", ")}`;
  card.appendChild(sources);

  return card;
}

function maxFollowers(person) {
  const counts = Object.values(person.profiles || {})
    .map((p) => p.followers)
    .filter((v) => v !== null && v !== undefined);
  return counts.length ? Math.max(...counts) : null;
}

function renderResults(payload) {
  resultsBox.replaceChildren();
  if (payload.count === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = payload.company
      ? "No publicly discoverable people found for this company."
      : "Company not found. Check the name and try again.";
    resultsBox.appendChild(empty);
    return;
  }
  for (const person of payload.results) {
    resultsBox.appendChild(buildCard(person));
  }
}

async function runSearch() {
  const company = companyInput.value.trim();
  if (!company) {
    setStatus("Enter a company name to search.", true);
    return;
  }
  const params = new URLSearchParams({
    company,
    sort: sortSelect.value,
  });
  if (roleInput.value.trim()) params.set("role", roleInput.value.trim());
  if (locationInput.value.trim()) params.set("location", locationInput.value.trim());

  setStatus(`Searching for ${company}...`);
  try {
    const response = await fetch(`/api/search?${params}`);
    if (!response.ok) throw new Error(`Server error ${response.status}`);
    const payload = await response.json();
    renderResults(payload);
    setStatus(
      `${payload.count} publicly discoverable people${
        payload.company ? ` @ ${payload.company.name}` : ""
      }`,
      false
    );
  } catch (err) {
    setStatus(`Search failed: ${err.message}`, true);
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runSearch();
});

sortSelect.addEventListener("change", () => {
  if (companyInput.value.trim()) runSearch();
});

companyInput.focus();
