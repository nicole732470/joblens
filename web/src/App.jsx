import { useState } from "react";
import { analyzeJob, API } from "./api";

function verdictClass(decision) {
  const d = (decision || "").toLowerCase();
  if (d === "apply") return "verdict-apply";
  if (d.includes("near")) return "verdict-near";
  if (d === "consider") return "verdict-consider";
  if (d === "skip") return "verdict-skip";
  return "verdict-default";
}

export default function App() {
  const [company, setCompany] = useState("");
  const [title, setTitle] = useState("");
  const [jd, setJd] = useState("");
  const [resume, setResume] = useState("");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");
  const [report, setReport] = useState(null);
  const [elapsed, setElapsed] = useState(null);

  async function onAnalyze() {
    if (jd.trim().length < 40) {
      setStatus("Paste a longer job description first.");
      return;
    }
    setLoading(true);
    setStatus("Analyzing…");
    setReport(null);
    const t0 = performance.now();
    try {
      const data = await analyzeJob({
        jd_text: jd,
        company,
        title,
        resume_text: resume,
      });
      setReport(data);
      setElapsed(((performance.now() - t0) / 1000).toFixed(1));
      setStatus("");
    } catch (err) {
      setStatus(`Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  const rec = report?.recommendation;
  const decision = rec?.decision || "—";
  const sp = report?.sponsorship;
  const rf = report?.resume_fit;
  const co = report?.company;

  return (
    <div className="app">
      <header className="header">
        <span className="mark" aria-hidden="true">
          JL
        </span>
        <div>
          <h1>JobLens</h1>
          <p className="tagline">See a company before you apply</p>
        </div>
      </header>

      <main className="main">
        <label>
          Company
          <input
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            placeholder="e.g. Amazon"
          />
        </label>
        <label>
          Job title
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Senior Software Engineer"
          />
        </label>
        <label>
          Job description
          <textarea
            rows={10}
            value={jd}
            onChange={(e) => setJd(e.target.value)}
            placeholder="Paste the full JD from LinkedIn or the company site…"
          />
        </label>
        <label>
          Resume{" "}
          <span className="hint">(optional — server uses default if empty)</span>
          <textarea
            rows={5}
            value={resume}
            onChange={(e) => setResume(e.target.value)}
            placeholder="Paste resume to override…"
          />
        </label>
        <button className="analyze" type="button" disabled={loading} onClick={onAnalyze}>
          {loading ? "Analyzing…" : "Analyze"}
        </button>
        <p className="status">{status}</p>

        {report && (
          <div className="results">
            <div className="verdict-card">
              <h2>Verdict</h2>
              <span className={`verdict-badge ${verdictClass(decision)}`}>{decision}</span>
              {rec?.reasoning && <p style={{ marginTop: 12 }}>{rec.reasoning}</p>}
              {rec?.fit_ratio != null && (
                <p className="debug">
                  Fit {Math.round(rec.fit_ratio * 100)}% · Track {rec.track_label || "—"} ·{" "}
                  {elapsed}s
                </p>
              )}
            </div>

            {sp && (
              <div className="section">
                <h3>H-1B sponsorship</h3>
                <p>
                  {sp.matched
                    ? `${sp.company?.name || company} — ${sp.match_confidence || "matched"} (${sp.total_lca_count || 0} LCAs)`
                    : sp.reason || "No match in index"}
                </p>
              </div>
            )}

            {co?.available && (
              <div className="section">
                <h3>Company fit</h3>
                <p>
                  {co.company_label || "—"} — {co.summary || "Scored vs your profile"}
                </p>
              </div>
            )}

            {rf?.available && (
              <div className="section">
                <h3>Resume match</h3>
                <p>
                  {rf.strong_matches?.length || 0} strong · {rf.partial_matches?.length || 0}{" "}
                  partial · {rf.missing?.length || 0} gaps
                  {rf.match_method ? ` (${rf.match_method})` : ""}
                </p>
              </div>
            )}
          </div>
        )}
      </main>

      <footer className="footer">
        API: {API} · H-1B deep lookup in Chrome extension
      </footer>
    </div>
  );
}
