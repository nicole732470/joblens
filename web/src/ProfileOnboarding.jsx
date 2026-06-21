import { useEffect, useState } from "react";
import {
  buildProfileFromForm,
  formFromProfile,
  newAvoidTrack,
  newTrack,
} from "./profileForm";

function LineList({ label, hint, value, onChange, rows = 4 }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {hint ? <span className="field-hint">{hint}</span> : null}
      <textarea rows={rows} value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

export default function ProfileOnboarding({ initialProfile, onSave, onCancel, title }) {
  const [form, setForm] = useState(() => formFromProfile(initialProfile));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (initialProfile) setForm(formFromProfile(initialProfile));
  }, [initialProfile]);

  function updateTrack(i, patch) {
    setForm((f) => {
      const tracks = [...f.tracks];
      tracks[i] = { ...tracks[i], ...patch };
      return { ...f, tracks };
    });
  }

  function updateAvoid(i, patch) {
    setForm((f) => {
      const avoidTracks = [...f.avoidTracks];
      avoidTracks[i] = { ...avoidTracks[i], ...patch };
      return { ...f, avoidTracks };
    });
  }

  async function handleSave() {
    if (!form.tracks.length || !form.tracks[0].label.trim()) {
      setError("Add at least one target track with a label.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await onSave(buildProfileFromForm(form));
    } catch (e) {
      setError(String(e.message));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="onboarding">
      <div className="onboarding-inner">
        <h2>{title || "Your job search profile"}</h2>
        <p className="sub">
          One-time setup — same fields as our YAML profile. Add as many tracks and lines as you
          need.
        </p>

        <section className="section-card">
          <h3>Target tracks</h3>
          <p className="hint">Role categories you want. Configure P1–P3; unmatched roles become P4.</p>
          {form.tracks.map((t, i) => (
            <div key={t.id + i} className="repeat-block">
              <div className="row-2">
                <label className="field">
                  <span className="field-label">Label</span>
                  <input
                    value={t.label}
                    onChange={(e) => updateTrack(i, { label: e.target.value })}
                    placeholder="e.g. AI Engineer"
                  />
                </label>
                <label className="field narrow">
                  <span className="field-label">Priority (1–3)</span>
                  <input
                    type="number"
                    min={1}
                    max={3}
                    value={t.priority}
                    onChange={(e) => updateTrack(i, { priority: e.target.value })}
                  />
                </label>
              </div>
              <LineList
                label="Example job titles"
                hint="One per line"
                rows={3}
                value={t.titlesText}
                onChange={(v) => updateTrack(i, { titlesText: v })}
              />
              <button
                type="button"
                className="btn-text danger"
                onClick={() =>
                  setForm((f) => ({ ...f, tracks: f.tracks.filter((_, j) => j !== i) }))
                }
              >
                Remove track
              </button>
            </div>
          ))}
          <button
            type="button"
            className="btn"
            onClick={() => setForm((f) => ({ ...f, tracks: [...f.tracks, newTrack()] }))}
          >
            + Add track
          </button>
        </section>

        <section className="section-card">
          <h3>Avoid tracks</h3>
          <p className="hint">Role types you never want.</p>
          {form.avoidTracks.map((t, i) => (
            <div key={t.id + i} className="repeat-block">
              <label className="field">
                <span className="field-label">Label</span>
                <input
                  value={t.label}
                  onChange={(e) => updateAvoid(i, { label: e.target.value })}
                  placeholder="e.g. pure sales"
                />
              </label>
              <LineList
                label="Example titles to avoid"
                rows={2}
                value={t.titlesText}
                onChange={(v) => updateAvoid(i, { titlesText: v })}
              />
              <button
                type="button"
                className="btn-text danger"
                onClick={() =>
                  setForm((f) => ({
                    ...f,
                    avoidTracks: f.avoidTracks.filter((_, j) => j !== i),
                  }))
                }
              >
                Remove
              </button>
            </div>
          ))}
          <button
            type="button"
            className="btn"
            onClick={() =>
              setForm((f) => ({ ...f, avoidTracks: [...f.avoidTracks, newAvoidTrack()] }))
            }
          >
            + Add avoid track
          </button>
        </section>

        <section className="section-card">
          <h3>Locations</h3>
          <label className="field">
            <span className="field-label">Summary</span>
            <input
              value={form.locSummary}
              onChange={(e) => setForm((f) => ({ ...f, locSummary: e.target.value }))}
              placeholder="e.g. US metros OK; prefer remote"
            />
          </label>
          <LineList
            label="Tier 1 — most want"
            rows={2}
            value={form.locTier1}
            onChange={(v) => setForm((f) => ({ ...f, locTier1: v }))}
          />
          <LineList
            label="Tier 2 — acceptable"
            rows={2}
            value={form.locTier2}
            onChange={(v) => setForm((f) => ({ ...f, locTier2: v }))}
          />
          <LineList
            label="Tier 3 — avoid"
            rows={2}
            value={form.locTier3}
            onChange={(v) => setForm((f) => ({ ...f, locTier3: v }))}
          />
          <div className="checks">
            <label>
              <input
                type="checkbox"
                checked={form.remoteOk}
                onChange={(e) => setForm((f) => ({ ...f, remoteOk: e.target.checked }))}
              />{" "}
              Remote OK
            </label>
            <label>
              <input
                type="checkbox"
                checked={form.relocationOk}
                onChange={(e) => setForm((f) => ({ ...f, relocationOk: e.target.checked }))}
              />{" "}
              Relocation OK
            </label>
          </div>
        </section>

        <section className="section-card">
          <h3>Lists</h3>
          <LineList
            label="Dealbreakers"
            hint="Hard no — one per line"
            value={form.dealbreakers}
            onChange={(v) => setForm((f) => ({ ...f, dealbreakers: v }))}
          />
          <LineList
            label="Preferences"
            hint="Nice-to-haves — one per line"
            value={form.preferences}
            onChange={(v) => setForm((f) => ({ ...f, preferences: v }))}
          />
          <LineList
            label="Technical penalties"
            hint="Domains you cannot do — one per line"
            value={form.technicalPenalties}
            onChange={(v) => setForm((f) => ({ ...f, technicalPenalties: v }))}
          />
          <LineList
            label="Alumni schools"
            hint="For LinkedIn alumni signals — one per line"
            value={form.alumniSchools}
            onChange={(v) => setForm((f) => ({ ...f, alumniSchools: v }))}
          />
          <label className="checks solo">
            <input
              type="checkbox"
              checked={form.needsSponsorship}
              onChange={(e) => setForm((f) => ({ ...f, needsSponsorship: e.target.checked }))}
            />{" "}
            I need visa sponsorship
          </label>
        </section>

        {error ? <p className="status err">{error}</p> : null}
        <div className="btn-row">
          {onCancel ? (
            <button type="button" className="btn" onClick={onCancel}>
              Cancel
            </button>
          ) : null}
          <button type="button" className="btn btn-primary" disabled={saving} onClick={handleSave}>
            {saving ? "Saving…" : "Save profile"}
          </button>
        </div>
      </div>
    </div>
  );
}
