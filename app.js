const form = document.querySelector("#question-form");
const question = document.querySelector("#question");
const mode = document.querySelector("#mode");
const ask = document.querySelector("#ask");
const compare = document.querySelector("#compare");
const status = document.querySelector("#status");
const results = document.querySelector("#results");
const title = document.querySelector("#result-title");
const response = document.querySelector("#response");
const labels = {
  answered: "Answered",
  partially_answered: "Partially answered",
  needs_clarification: "Needs clarification",
  insufficient_evidence: "Insufficient evidence",
};
const modes = { bm25: "BM25", semantic: "Semantic", hybrid: "Hybrid" };

let ready = false;
let busy = true;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function setBusy(nextBusy) {
  busy = nextBusy;
  ask.disabled = !ready || busy;
  compare.disabled = !ready || busy;
  results.setAttribute("aria-busy", String(busy));
}

function showAnswer(result, submittedQuestion) {
  title.textContent = labels[result.outcome];
  const passages = new Map();
  for (const source of result.retrieved) {
    const details = element("details");
    details.append(
      element("summary", `${source.id} · ${source.title}`),
      element("p", source.text),
    );
    passages.set(source.id, details);
  }

  if (result.claims.length) {
    const claims = element("ul", "", "claims");
    for (const claim of result.claims) {
      const row = element("li");
      const cite = element("button", claim.source_id, "cite");
      cite.type = "button";
      cite.setAttribute("aria-label", `Open source ${claim.source_id}`);
      cite.addEventListener("click", () => {
        const source = passages.get(claim.source_id);
        source.open = true;
        source.querySelector("summary").focus();
      });
      row.append(element("blockquote", claim.text), cite);
      claims.append(row);
    }
    response.append(claims);
  }

  if (result.unanswered.length) {
    if (result.claims.length) response.append(element("h3", "What the notes leave open"));
    const list = element("ul", "", "unanswered");
    for (const line of result.unanswered) list.append(element("li", line));
    response.append(list);
  }

  if (result.choices.length) {
    response.append(element("p", "Which edition did you mean?"));
    const choices = element("div", "", "choices");
    for (const choice of result.choices) {
      const button = element("button", `${choice.code} · ${choice.title} · ${choice.artist}`, "chip");
      button.type = "button";
      button.addEventListener("click", () => {
        question.value = `${submittedQuestion.slice(0, 388).replace(/[?.!]+$/, "")} (${choice.code})?`;
        form.requestSubmit(ask);
      });
      choices.append(button);
    }
    response.append(choices);
  }

  if (passages.size) {
    response.append(element("h3", "Cited release notes"), ...passages.values());
  }
  if (result.search_hits.length) {
    const candidates = element("details");
    candidates.append(
      element("summary", `Search candidates · ${modes[result.mode]}`),
      element("p", "These are unfiltered matches. The answer only cites passages that match the resolved release and question."),
      rankedList(result.search_hits),
    );
    response.append(candidates);
  }
}

function rankedList(hits) {
  if (!hits.length) return element("p", "No matching passages.");
  const list = element("ol");
  for (const hit of hits) {
    const row = element("li");
    const detail = element("details");
    const ranks = [];
    if (hit.bm25_rank !== null) ranks.push(`BM25 #${hit.bm25_rank}`);
    if (hit.semantic_rank !== null) ranks.push(`Semantic #${hit.semantic_rank}`);
    detail.append(
      element("summary", `${hit.id} · ${hit.title}`),
      element("p", hit.text),
      element("p", ranks.join(" / "), "source-code"),
    );
    row.append(detail);
    list.append(row);
  }
  return list;
}

function showComparison(rankings) {
  title.textContent = "Retrieval comparison";
  response.append(element("p", "The top five candidates per mode. Open a match to see its passage and contributing ranks."));
  const groups = element("div", "", "rankings");
  for (const [key, hits] of Object.entries(rankings)) {
    const group = element("section");
    group.append(element("h3", modes[key]), rankedList(hits));
    groups.append(group);
  }
  response.append(groups);
}

function startWorker() {
  const worker = new Worker("worker.js", { type: "module" });
  const failStartup = () => {
    ready = false;
    setBusy(false);
    status.textContent = "The browser engine couldn’t start. Reload to retry or run the Python CLI from the source repository.";
  };
  worker.addEventListener("error", failStartup);
  worker.addEventListener("message", ({ data }) => {
    if (data.type === "ready") {
      ready = true;
      setBusy(false);
      status.textContent = "Ready · 20 releases loaded";
      return;
    }
    if (data.type === "startup-error") {
      failStartup();
      return;
    }

    setBusy(false);
    if (data.type === "question-error") {
      status.textContent = "The engine couldn’t run that query. Please try again.";
      return;
    }

    response.replaceChildren();
    if (data.action === "compare") showComparison(data.result);
    else showAnswer(data.result, data.question);
    status.textContent = `Showing results for “${data.question}”`;
    title.focus();
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const value = question.value.trim();
    if (!ready || busy || !value) return;
    setBusy(true);
    status.textContent = "Searching the catalogue…";
    worker.postMessage({ question: value, mode: mode.value, action: event.submitter?.value || "answer" });
  });
  document.querySelectorAll("[data-example]").forEach((example) => {
    example.addEventListener("click", () => {
      question.value = example.dataset.example;
      if (ready && !busy) form.requestSubmit(example.hasAttribute("data-compare") ? compare : ask);
      else question.focus();
    });
  });
}

startWorker();
