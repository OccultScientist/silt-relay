const form = document.querySelector("#question-form");
const question = document.querySelector("#question");
const mode = document.querySelector("#mode");
const dig = document.querySelector("#dig");
const vinylOnly = document.querySelector("#vinyl-only");
const viewButtons = [...document.querySelectorAll("[data-view]")];
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

const draft = {
  dig: { question: question.value, mode: mode.value },
  ask: { question: "When did Glass Current come out, and did the vinyl ship?", mode: "bm25" },
};
let view = "dig";
let ready = false;
let busy = true;
let focusResult = true;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function setBusy(nextBusy) {
  busy = nextBusy;
  dig.disabled = !ready || busy;
  ask.disabled = !ready || busy;
  compare.disabled = !ready || busy;
  for (const button of viewButtons) button.disabled = ready && busy;
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

function sourceNote(source, label, open = false) {
  const details = element("details", "", "release-note");
  details.open = open;
  const summary = element("summary", label + " ");
  summary.append(element("span", source.id, "source-code"));
  details.append(summary, element("p", source.text));
  return details;
}

function editionPanel(label, sources) {
  const panel = element("section", "", "edition");
  panel.append(element("h4", label + " · " + sources.date.code), element("p", sources.date.title));
  panel.append(
    sourceNote(sources.date, "Release date"),
    sourceNote(sources.format, "Format"),
    sourceNote(sources.tracks, "Tracklist", true),
  );
  return panel;
}

function showEditions(comparison, open) {
  const details = element("details", "", "edition-comparison");
  details.open = open;
  details.append(element("summary", "Compare original and reissue"));
  const changes = element("div", "", "edition-changes");
  changes.append(element("h4", "What changed"));
  if (comparison.added.length) {
    changes.append(element("p", "Added on the reissue · " + comparison.added.join(", ")));
  }
  if (comparison.original_only.length) {
    changes.append(element("p", "Original edition only · " + comparison.original_only.join(", ")));
  }
  if (!comparison.added.length && !comparison.original_only.length) {
    changes.append(element("p", "Both notes list the same tracks."));
  }
  changes.append(element("p", "Derived from " + comparison.original.tracks.id + " and " + comparison.reissue.tracks.id, "source-code"));
  const grid = element("div", "", "edition-grid");
  grid.append(editionPanel("Original", comparison.original), editionPanel("Reissue", comparison.reissue));
  details.append(changes, grid, sourceNote(comparison.relationship, "How the editions are linked"));
  return details;
}

function showSoundCues(card, record) {
  const matching = Object.entries(record.matched).map(([term, cue]) => (
    term === cue ? term : term + " → " + cue
  ));
  if (matching.length) card.append(element("p", "Sound evidence · " + matching.join(", "), "dig-criteria"));
  if (record.unmatched.length) {
    card.append(element("p", "Unconfirmed in this sound note · " + record.unmatched.join(", "), "dig-criteria"));
  }
}

function showDig(result) {
  const count = result.matches.length;
  const partialCount = result.matches.filter(record => record.partial_sound).length;
  if (!count) title.textContent = "No supported matches";
  else if (partialCount === count) title.textContent = "Only partial sound matches";
  else title.textContent = count + (count === 1 ? " match in the crate" : " matches in the crate");
  if (result.message) {
    response.append(element("p", result.message));
    return;
  }

  const criteria = [];
  if (result.sound_terms.length) criteria.push("Sound · " + result.sound_terms.join(", "));
  if (result.formats.length) {
    const label = result.exclusive_formats ? "Documented only in · " : "Format · ";
    criteria.push(label + result.formats.join(result.format_alternatives ? " or " : " and "));
  }
  if (result.vinyl_only) criteria.push("Confirmed vinyl only");
  if (result.reissues_only) criteria.push("Linked reissues only");
  if (criteria.length) response.append(element("p", criteria.join("  /  "), "dig-criteria"));
  if (result.reference) {
    response.append(sourceNote(result.reference, "Reference sound · " + result.reference.title, true));
    response.append(element("p", "Similar suggestions share wording from these sound notes.", "dig-criteria"));
  }
  if (result.format_conflicts.length) {
    response.append(element("p", "The named edition’s format note does not support the requested format."));
    for (const source of result.format_conflicts) response.append(sourceNote(source, "Recorded format · " + source.title, true));
  } else if (!count) {
    response.append(element("p", "No sound note and documented edition satisfy this search. Try fewer terms or another format."));
  }

  const stack = element("div", "", "crate-stack");
  for (const record of result.matches) {
    const card = element("article", "", "crate-record");
    card.append(element("p", record.code + " / " + record.artist, "eyebrow"));
    card.append(element("h3", record.title));
    if (record.partial_sound) card.append(element("p", "Partial sound match", "eyebrow"));
    showSoundCues(card, record);
    if (record.shared_cues.length) {
      card.append(element("p", "Shared wording with the reference · " + record.shared_cues.join(", "), "dig-criteria"));
    }
    card.append(sourceNote(record.sound, "Sound note · " + record.sound.title, true));
    if (record.format_check) {
      const messages = {
        documented: "Follow-up · the cited notes document " + record.format_check.format,
        proposed: "Follow-up · " + record.format_check.format + " was proposed. Release is unconfirmed.",
        unconfirmed: "Follow-up · the cited format notes do not confirm " + record.format_check.format + ".",
      };
      card.append(element("p", messages[record.format_check.status], "dig-criteria"));
    }
    if (record.formats.length) {
      card.append(element("h4", "Documented formats · " + record.formats.join(", ")));
    }
    for (const source of record.format_sources) {
      card.append(sourceNote(source, "Format · " + source.title));
    }
    for (const source of record.proposed) {
      card.append(sourceNote(source, "Proposed pressing · release unconfirmed"));
    }
    for (const comparison of record.comparisons) card.append(showEditions(comparison, result.compare_requested));
    stack.append(card);
  }

  for (const proposal of result.proposals) {
    const card = element("article", "", "crate-record proposal");
    card.append(element("p", "Proposal · " + proposal.sound.code, "eyebrow"));
    card.append(element("h3", proposal.sound.title));
    card.append(element("p", "There’s a sound match, but the notes only document a vinyl proposal."));
    showSoundCues(card, proposal);
    card.append(sourceNote(proposal.sound, "Sound note"));
    for (const source of proposal.sources) card.append(sourceNote(source, "Pressing proposal", true));
    stack.append(card);
  }
  response.append(stack);
}

function changeView(nextView) {
  if (nextView === view) return;
  draft[view] = { question: question.value, mode: mode.value };
  view = nextView;
  const digging = view === "dig";
  for (const button of viewButtons) {
    button.setAttribute("aria-pressed", String(button.dataset.view === view));
  }
  document.querySelector("#question-label").textContent = digging ? "What are you digging for?" : "Your question";
  document.querySelector("#vinyl-option").hidden = !digging;
  document.querySelector("#dig-examples").hidden = !digging;
  document.querySelector("#ask-examples").hidden = digging;
  document.querySelector("#result-label").textContent = digging ? "From the crate" : "Catalogue response";
  dig.hidden = !digging;
  ask.hidden = compare.hidden = digging;
  question.value = draft[view].question;
  mode.value = draft[view].mode;
  title.textContent = digging ? "Dig by sound" : "Awaiting a question";
  response.replaceChildren(element("p", digging ?
    "Try a mood, an instrument or a rhythm. Add a format to narrow the search." :
    "Ask about a date, format, tracklist, credit, sound or edition. Use a release title or catalogue number."));
  if (ready) status.textContent = "Ready · 21 releases loaded";
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
  const worker = new Worker("worker.js?v=scope", { type: "module" });
  function run(action, focus = true) {
    const value = question.value.trim();
    if (!ready || busy || !value) return;
    focusResult = focus;
    setBusy(true);
    status.textContent = "Searching the catalogue…";
    worker.postMessage({ question: value, mode: mode.value, action, vinylOnly: vinylOnly.checked });
  }
  for (const button of viewButtons) {
    button.addEventListener("click", () => changeView(button.dataset.view));
  }
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
      status.textContent = "Ready · 21 releases loaded";
      if (view === "dig") run("dig", false);
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
    if (data.action === "dig") showDig(data.result);
    else if (data.action === "compare") showComparison(data.result);
    else showAnswer(data.result, data.question);
    status.textContent = `Showing results for “${data.question}”`;
    if (focusResult) title.focus();
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    run(event.submitter?.value || (view === "dig" ? "dig" : "answer"));
  });
  document.querySelectorAll("[data-example]").forEach((example) => {
    example.addEventListener("click", () => {
      question.value = example.dataset.example;
      if (ready && !busy) {
        const button = view === "dig" ? dig : example.hasAttribute("data-compare") ? compare : ask;
        form.requestSubmit(button);
      } else question.focus();
    });
  });
}

startWorker();
