import { loadPyodide } from "./runtime/pyodide.mjs";

const runtime = new URL("runtime/", self.location.href).href;

async function initialise() {
  const py = await loadPyodide({ indexURL: runtime });
  py.FS.mkdir("data");

  const files = ["silt_relay.py", "data/releases.json", "data/vectors.tsv"];
  await Promise.all(files.map(async (file) => {
    const response = await fetch(file, { cache: "no-cache" });
    if (!response.ok) throw new Error(`Could not load ${file}: ${response.status}`);
    py.FS.writeFile(file, new Uint8Array(await response.arrayBuffer()));
  }));

  py.runPython(`
import json
from silt_relay import Archive, DATA, MODES
archive = Archive.from_directory(DATA)

def run_question(action, question, mode, vinyl_only):
    if action == "compare":
        result = {name: archive.search(question, name) for name in MODES}
    elif action == "dig":
        result = archive.dig(question, mode, vinyl_only=vinyl_only)
    else:
        result = archive.answer(question, mode)
    return json.dumps(result, ensure_ascii=False)
`);
  return py;
}

const engine = initialise();
engine.then(() => postMessage({ type: "ready" }), (error) => {
  console.error(error);
  postMessage({ type: "startup-error" });
});

self.onmessage = async ({ data }) => {
  try {
    const py = await engine;
    const runQuestion = py.globals.get("run_question");
    try {
      const result = JSON.parse(runQuestion(data.action, data.question, data.mode, data.vinylOnly));
      postMessage({ type: "result", action: data.action, question: data.question, result });
    } finally {
      runQuestion.destroy();
    }
  } catch (error) {
    console.error(error);
    postMessage({ type: "question-error" });
  }
};
