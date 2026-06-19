import { useState } from "react";
import {
  analyzeJob,
  API,
  getProfile,
  login,
  parseJobUrl,
  register,
  saveProfile,
  uploadResumePdf,
} from "./api";
import { useAuth } from "./AuthContext";

const TRACK_OPTIONS = [
  { id: "pm_eng", label: "Product / TPM" },
  { id: "ai_eng", label: "AI Engineer" },
  { id: "data_eng", label: "Data Engineer" },
  { id: "swe", label: "Software Engineer" },
];

const STEPS = ["Account", "Preferences", "Job link", "Resume", "Results"];

function verdictClass(d) {
  const x = (d || "").toLowerCase();
  if (x === "apply") return "verdict-apply";
  if (x.includes("near")) return "verdict-near";
  if (x === "consider") return "verdict-consider";
  if (x === "skip") return "verdict-skip";
  return "";
}

export default function App() {
  const { token, email, isLoggedIn, setSession, logout } = useAuth();
  const [step, setStep] = useState(0);
  const [status, setStatus] = useState("");

  // Auth
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");

  // Profile
  const [selectedTracks, setSelectedTracks] = useState([]);
  const [dealbreakers, setDealbreakers] = useState("");
  const [locations, setLocations] = useState("");

  // Job
  const [jobUrl, setJobUrl] = useState("");
  const [jdText, setJdText] = useState("");
  const [company, setCompany] = useState("");
  const [title, setTitle] = useState("");

  // Resume
  const [resumeFile, setResumeFile] = useState(null);
  const [resumeUploaded, setResumeUploaded] = useState(false);

  // Result
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);

  function err(msg) {
    setStatus(msg);
  }

  async function handleRegister() {
    try {
      const data = await register(authEmail, authPassword);
      setSession(data.token, data.email);
      setStatus("");
      setStep(1);
    } catch (e) {
      err(String(e.message));
    }
  }

  async function handleLogin() {
    try {
      const data = await login(authEmail, authPassword);
      setSession(data.token, data.email);
      setStatus("");
      setStep(1);
    } catch (e) {
      err(String(e.message));
    }
  }

  function continueAsGuest() {
    setStep(1);
    setStatus("");
  }

  async function savePreferences() {
    if (!isLoggedIn) {
      setStep(2);
      return;
    }
    try {
      let profile = {};
      try {
        profile = await getProfile(token);
      } catch {
        profile = { tracks: [], dealbreakers: [], locations: { summary: "" } };
      }
      profile.tracks = selectedTracks.map((id) => {
        const t = TRACK_OPTIONS.find((o) => o.id === id);
        return { id, label: t?.label || id, priority: 1, example_titles: [] };
      });
      profile.dealbreakers = dealbreakers
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);
      profile.locations = { ...(profile.locations || {}), summary: locations };
      await saveProfile(token, profile);
      setStatus("");
      setStep(2);
    } catch (e) {
      err(String(e.message));
    }
  }

  async function fetchJob() {
    setLoading(true);
    setStatus("Fetching job page…");
    try {
      const data = await parseJobUrl(jobUrl);
      if (!data.ok) {
        err(data.reason || "Could not parse URL");
        setLoading(false);
        return;
      }
      setJdText(data.jd_text || "");
      setCompany(data.company || "");
      setTitle(data.title || "");
      setStatus("Job details loaded.");
      setStep(3);
    } catch (e) {
      err(String(e.message));
    } finally {
      setLoading(false);
    }
  }

  async function uploadResume() {
    if (!resumeFile) {
      err("Select a PDF resume");
      return;
    }
    if (!isLoggedIn) {
      err("Sign in to upload resume, or continue as guest with server default resume");
      setStep(4);
      return;
    }
    setLoading(true);
    setStatus("Uploading resume…");
    try {
      await uploadResumePdf(token, resumeFile);
      setResumeUploaded(true);
      setStatus("Resume saved.");
      setStep(4);
    } catch (e) {
      err(String(e.message));
    } finally {
      setLoading(false);
    }
  }

  async function runAnalyze() {
    setLoading(true);
    setStatus("Analyzing… (20–90s on free LLM)");
    setReport(null);
    const t0 = performance.now();
    try {
      const body = {
        jd_text: jdText,
        company: company || null,
        title: title || null,
        job_url: jobUrl || null,
      };
      const data = await analyzeJob(body, token);
      setReport(data);
      setStatus(`Done in ${((performance.now() - t0) / 1000).toFixed(1)}s`);
    } catch (e) {
      err(String(e.message));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <span className="brand">JobLens</span>
          <span className="tagline">See a company before you apply</span>
        </div>
        {isLoggedIn ? (
          <button type="button" className="btn" onClick={logout}>
            {email} · Sign out
          </button>
        ) : null}
      </header>

      <main className="main">
        <div className="steps">
          {STEPS.map((s, i) => (
            <span
              key={s}
              className={`step-pill ${i === step ? "active" : ""} ${i < step ? "done" : ""}`}
            >
              {i + 1}. {s}
            </span>
          ))}
        </div>

        <div className="card">
          {step === 0 && (
            <>
              <h2>Account</h2>
              <p className="sub">Save your job preferences and resume across sessions.</p>
              <label>
                Email
                <input
                  type="email"
                  value={authEmail}
                  onChange={(e) => setAuthEmail(e.target.value)}
                  autoComplete="email"
                />
              </label>
              <label>
                Password
                <input
                  type="password"
                  value={authPassword}
                  onChange={(e) => setAuthPassword(e.target.value)}
                  autoComplete="new-password"
                />
              </label>
              <div className="btn-row">
                <button type="button" className="btn btn-primary" onClick={handleRegister}>
                  Create account
                </button>
                <button type="button" className="btn" onClick={handleLogin}>
                  Sign in
                </button>
                <button type="button" className="btn" onClick={continueAsGuest}>
                  Continue as guest
                </button>
              </div>
            </>
          )}

          {step === 1 && (
            <>
              <h2>Job preferences</h2>
              <p className="sub">What roles and locations are you targeting?</p>
              <label>Tracks you want</label>
              <div className="chip-grid">
                {TRACK_OPTIONS.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    className={`chip ${selectedTracks.includes(t.id) ? "selected" : ""}`}
                    onClick={() =>
                      setSelectedTracks((prev) =>
                        prev.includes(t.id) ? prev.filter((x) => x !== t.id) : [...prev, t.id]
                      )
                    }
                  >
                    {t.label}
                  </button>
                ))}
              </div>
              <label>
                Locations (summary)
                <input
                  value={locations}
                  onChange={(e) => setLocations(e.target.value)}
                  placeholder="e.g. Chicago, remote OK"
                />
              </label>
              <label>
                Dealbreakers (one per line)
                <textarea
                  rows={3}
                  value={dealbreakers}
                  onChange={(e) => setDealbreakers(e.target.value)}
                  placeholder="e.g. no sponsorship, onsite only Bay Area"
                />
              </label>
              <div className="btn-row">
                <button type="button" className="btn" onClick={() => setStep(0)}>
                  Back
                </button>
                <button type="button" className="btn btn-primary" onClick={savePreferences}>
                  Continue
                </button>
              </div>
            </>
          )}

          {step === 2 && (
            <>
              <h2>Job posting</h2>
              <p className="sub">Paste the job URL — we fetch title, company, and description.</p>
              <label>
                Job URL
                <input
                  type="url"
                  value={jobUrl}
                  onChange={(e) => setJobUrl(e.target.value)}
                  placeholder="https://boards.greenhouse.io/…"
                />
              </label>
              <p className="sub" style={{ marginTop: 0 }}>
                LinkedIn URLs often fail server-side — use the Chrome extension on LinkedIn, or
                paste JD below.
              </p>
              <label>
                Or paste JD manually
                <textarea
                  rows={6}
                  value={jdText}
                  onChange={(e) => setJdText(e.target.value)}
                  placeholder="Full job description…"
                />
              </label>
              <div className="btn-row">
                <button type="button" className="btn" onClick={() => setStep(1)}>
                  Back
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={loading}
                  onClick={() => {
                    if (jdText.trim().length >= 80) {
                      setStep(3);
                      setStatus("");
                    } else if (jobUrl.trim()) {
                      fetchJob();
                    } else {
                      err("Enter a job URL or paste the JD");
                    }
                  }}
                >
                  {loading ? "Fetching…" : "Continue"}
                </button>
              </div>
            </>
          )}

          {step === 3 && (
            <>
              <h2>Resume</h2>
              <p className="sub">Upload PDF for personalized fit analysis.</p>
              <div className="file-zone">
                <input
                  type="file"
                  accept="application/pdf"
                  onChange={(e) => setResumeFile(e.target.files?.[0] || null)}
                />
                {resumeFile ? <p>{resumeFile.name}</p> : <p>PDF only, max 5MB</p>}
              </div>
              {!isLoggedIn && (
                <p className="sub">Guests use the server default resume. Sign in to use your PDF.</p>
              )}
              <div className="btn-row">
                <button type="button" className="btn" onClick={() => setStep(2)}>
                  Back
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={loading}
                  onClick={() => {
                    if (isLoggedIn && resumeFile) uploadResume();
                    else {
                      setStep(4);
                      setStatus(isLoggedIn ? "" : "Using default resume");
                    }
                  }}
                >
                  {loading ? "Uploading…" : "Continue"}
                </button>
              </div>
            </>
          )}

          {step === 4 && (
            <>
              <h2>Analysis</h2>
              <p className="sub">
                {company || "—"} · {title || "—"}
              </p>
              {!report && (
                <div className="btn-row">
                  <button type="button" className="btn" onClick={() => setStep(3)}>
                    Back
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={loading}
                    onClick={runAnalyze}
                  >
                    {loading ? "Analyzing…" : "Run analysis"}
                  </button>
                </div>
              )}
              {report && (
                <div className="result-block">
                  <span
                    className={`verdict ${verdictClass(report.recommendation?.decision)}`}
                  >
                    {report.recommendation?.decision || "—"}
                  </span>
                  <p>{report.recommendation?.reasoning}</p>
                  {report.sponsorship && (
                    <div className="result-block">
                      <h3>H-1B</h3>
                      <p>
                        {report.sponsorship.matched
                          ? `${report.sponsorship.company?.name || company} · ${report.sponsorship.total_lca_count || 0} LCAs`
                          : report.sponsorship.reason}
                      </p>
                    </div>
                  )}
                  {report.resume_fit?.available && (
                    <div className="result-block">
                      <h3>Resume</h3>
                      <p>
                        {report.resume_fit.strong_matches?.length || 0} strong ·{" "}
                        {report.resume_fit.partial_matches?.length || 0} partial ·{" "}
                        {report.resume_fit.missing?.length || 0} gaps
                      </p>
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          <p className={`status ${status.startsWith("Error") ? "err" : ""}`}>{status}</p>
        </div>
      </main>

      <footer className="footer">API: {API}</footer>
    </div>
  );
}
