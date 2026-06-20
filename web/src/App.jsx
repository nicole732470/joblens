import { useEffect, useState } from "react";
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
import ProfileOnboarding from "./ProfileOnboarding";
import { profileNeedsOnboarding } from "./profileForm";
import ReportPanel from "./ReportPanel";

function urlLooksLikeJob(url) {
  const u = (url || "").trim().toLowerCase();
  if (!u) return { ok: true, reason: "" };
  if (!u.startsWith("http://") && !u.startsWith("https://")) {
    return { ok: false, reason: "URL must start with http:// or https://" };
  }
  if (/linkedin\.com\/(feed|in\/|company\/|posts\/|pulse\/|learning\/|mynetwork\/)/.test(u)) {
    return { ok: false, reason: "This is not a job posting — use a /jobs/view/… link or paste the JD" };
  }
  if (u.includes("linkedin.com") && !/linkedin\.com\/jobs\/|currentjobid=/.test(u)) {
    return { ok: false, reason: "LinkedIn URL must be a job posting (/jobs/view/…)" };
  }
  if (
    /linkedin\.com\/jobs\/|greenhouse\.io|lever\.co|workday|ashbyhq|careers\/|\/jobs\/|jobvite|icims/.test(
      u
    )
  ) {
    return { ok: true, reason: "" };
  }
  if (/\/(jobs?|careers|positions|openings)\//.test(u)) {
    return { ok: true, reason: "" };
  }
  return { ok: false, reason: "URL does not look like a job posting — paste a careers link or the JD text" };
}

export default function App() {
  const { token, email, isLoggedIn, setSession, logout } = useAuth();

  // null = main app | 'auth' | 'onboarding' | 'settings'
  const [screen, setScreen] = useState(null);
  const [authMode, setAuthMode] = useState("login");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");

  const [jobUrl, setJobUrl] = useState("");
  const [jdText, setJdText] = useState("");
  const [company, setCompany] = useState("");
  const [title, setTitle] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);

  const [resumeFile, setResumeFile] = useState(null);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");

  useEffect(() => {
    if (!isLoggedIn) return;
    getProfile(token)
      .then((p) => {
        if (profileNeedsOnboarding(p)) setScreen("onboarding");
      })
      .catch(() => {});
  }, [isLoggedIn, token]);

  async function handleAuthSubmit(e) {
    e.preventDefault();
    setStatus("");
    try {
      const fn = authMode === "register" ? register : login;
      const data = await fn(authEmail, authPassword);
      setSession(data.token, data.email);
      if (authMode === "register") {
        setScreen("onboarding");
      } else {
        const p = await getProfile(data.token);
        setScreen(profileNeedsOnboarding(p) ? "onboarding" : null);
      }
    } catch (err) {
      setStatus(String(err.message));
    }
  }

  async function runAnalyze() {
    setLoading(true);
    setStatus("");
    setReport(null);
    const t0 = performance.now();
    try {
      if (jobUrl.trim()) {
        const urlCheck = urlLooksLikeJob(jobUrl);
        if (!urlCheck.ok && jdText.trim().length < 80) {
          throw new Error(urlCheck.reason);
        }
      }

      if (jobUrl.trim() && jdText.trim().length < 80) {
        setStatus("Fetching job page…");
        const parsed = await parseJobUrl(jobUrl.trim());
        if (parsed.ok) {
          setJdText(parsed.jd_text || "");
          setCompany(parsed.company || company);
          setTitle(parsed.title || title);
        } else if (!jdText.trim()) {
          throw new Error(parsed.reason || "Could not parse URL");
        }
      }

      const body = {
        jd_text: jdText,
        company: company || null,
        title: title || null,
        job_url: jobUrl || null,
      };

      if (isLoggedIn && resumeFile) {
        await uploadResumePdf(token, resumeFile);
      }

      setStatus("Analyzing…");
      const data = await analyzeJob(body, token);
      setReport(data);
      setStatus(`Done in ${((performance.now() - t0) / 1000).toFixed(1)}s`);
    } catch (err) {
      setStatus(String(err.message));
    } finally {
      setLoading(false);
    }
  }

  if (screen === "onboarding" || screen === "settings") {
    return (
      <Shell
        email={email}
        isLoggedIn={isLoggedIn}
        onLogout={logout}
        onSettings={() => setScreen("settings")}
        onMain={() => setScreen(null)}
      >
        <ProfileScreen
          token={token}
          mode={screen}
          resumeFile={resumeFile}
          setResumeFile={setResumeFile}
          onDone={() => setScreen(null)}
        />
      </Shell>
    );
  }

  return (
    <Shell
      email={email}
      isLoggedIn={isLoggedIn}
      onLogout={() => {
        logout();
        setScreen(null);
      }}
      onSignIn={() => {
        setScreen("auth");
        setAuthMode("login");
      }}
      onSignUp={() => {
        setScreen("auth");
        setAuthMode("register");
      }}
      onSettings={() => setScreen("settings")}
    >
      {screen === "auth" && (
        <div className="modal-backdrop" onClick={() => setScreen(null)}>
          <form className="modal-card" onClick={(e) => e.stopPropagation()} onSubmit={handleAuthSubmit}>
            <h2>{authMode === "register" ? "Create account" : "Sign in"}</h2>
            <p className="sub">
              {authMode === "register"
                ? "Next you’ll customize tracks, locations, and preferences once."
                : "Returning users go straight to job analysis."}
            </p>
            <label className="field">
              <span className="field-label">Email</span>
              <input
                type="email"
                required
                value={authEmail}
                onChange={(e) => setAuthEmail(e.target.value)}
              />
            </label>
            <label className="field">
              <span className="field-label">Password</span>
              <input
                type="password"
                required
                minLength={8}
                value={authPassword}
                onChange={(e) => setAuthPassword(e.target.value)}
              />
            </label>
            <div className="btn-row">
              <button type="submit" className="btn btn-primary">
                {authMode === "register" ? "Continue" : "Sign in"}
              </button>
              <button
                type="button"
                className="btn-text"
                onClick={() => setAuthMode(authMode === "register" ? "login" : "register")}
              >
                {authMode === "register" ? "Already have an account?" : "Create account"}
              </button>
            </div>
            {status ? <p className="status err">{status}</p> : null}
          </form>
        </div>
      )}

      <section className="hero">
        <h1 className="hero-title">Paste a job link</h1>
        <p className="hero-sub">We parse the posting and match it to your profile and resume.</p>
        <div className="hero-input-wrap">
          <input
            className="hero-input"
            type="url"
            placeholder="https://boards.greenhouse.io/company/jobs/123"
            value={jobUrl}
            onChange={(e) => setJobUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !loading && runAnalyze()}
          />
          <button type="button" className="btn btn-primary hero-btn" disabled={loading} onClick={runAnalyze}>
            {loading ? "…" : "Analyze"}
          </button>
        </div>
        <button type="button" className="btn-text" onClick={() => setShowAdvanced(!showAdvanced)}>
          {showAdvanced ? "Hide manual input" : "Paste JD manually instead"}
        </button>
      </section>

      {showAdvanced && (
        <section className="section-card flow-section">
          <label className="field">
            <span className="field-label">Job description</span>
            <textarea rows={8} value={jdText} onChange={(e) => setJdText(e.target.value)} />
          </label>
          <div className="row-2">
            <label className="field">
              <span className="field-label">Company</span>
              <input value={company} onChange={(e) => setCompany(e.target.value)} />
            </label>
            <label className="field">
              <span className="field-label">Title</span>
              <input value={title} onChange={(e) => setTitle(e.target.value)} />
            </label>
          </div>
        </section>
      )}

      {isLoggedIn && (
        <section className="section-card flow-section compact">
          <label className="field">
            <span className="field-label">Resume (PDF)</span>
            <span className="field-hint">Optional — updates your stored resume when you analyze</span>
            <input type="file" accept="application/pdf" onChange={(e) => setResumeFile(e.target.files?.[0] || null)} />
          </label>
        </section>
      )}

      {status && !report ? <p className="status flow-status">{status}</p> : null}

      {report && <ReportPanel report={report} status={status} />}
    </Shell>
  );
}

function ProfileScreen({ token, mode, resumeFile, setResumeFile, onDone }) {
  const [profile, setProfile] = useState(null);
  const [loadErr, setLoadErr] = useState("");

  useEffect(() => {
    getProfile(token)
      .then(setProfile)
      .catch((e) => setLoadErr(String(e.message)));
  }, [token]);

  if (loadErr) return <p className="status err">{loadErr}</p>;
  if (!profile) return <p className="status flow-status">Loading profile…</p>;

  return (
    <>
      {mode === "onboarding" && (
        <section className="section-card flow-section compact">
          <label className="field">
            <span className="field-label">Resume (PDF)</span>
            <span className="field-hint">Optional — upload now or later from the main page</span>
            <input
              type="file"
              accept="application/pdf"
              onChange={(e) => setResumeFile(e.target.files?.[0] || null)}
            />
          </label>
        </section>
      )}
      <ProfileOnboarding
        title={mode === "settings" ? "Edit profile" : "Welcome — set up your profile"}
        initialProfile={profile}
        onCancel={mode === "settings" ? onDone : undefined}
        onSave={async (next) => {
          await saveProfile(token, next);
          if (resumeFile) await uploadResumePdf(token, resumeFile);
          onDone();
        }}
      />
    </>
  );
}

function Shell({
  children,
  email,
  isLoggedIn,
  onLogout,
  onSignIn,
  onSignUp,
  onSettings,
  onMain,
}) {
  return (
    <div className="app-shell">
      <header className="topbar">
        <button type="button" className="brand-btn" onClick={onMain}>
          JobLens
        </button>
        <nav className="nav">
          {isLoggedIn ? (
            <>
              <button type="button" className="btn-text" onClick={onSettings}>
                Profile
              </button>
              <button type="button" className="btn-text" onClick={onLogout}>
                {email} · Out
              </button>
            </>
          ) : (
            <>
              <button type="button" className="btn-text" onClick={onSignIn}>
                Sign in
              </button>
              <button type="button" className="btn" onClick={onSignUp}>
                Sign up
              </button>
            </>
          )}
        </nav>
      </header>
      <main className="main flow-main">{children}</main>
      <footer className="footer">API {API}</footer>
    </div>
  );
}
