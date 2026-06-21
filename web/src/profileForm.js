/** Turn newline-separated text into a trimmed string array. */
export function linesToList(text) {
  return String(text || "")
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function listToLines(arr) {
  return (arr || []).join("\n");
}

export function emptyProfile() {
  return {
    tracks: [],
    avoid_tracks: [],
    locations: {
      summary: "",
      tier_1: [],
      tier_2: [],
      tier_3: [],
      remote_ok: true,
      relocation_ok: true,
    },
    dealbreakers: [],
    preferences: [],
    technical_penalties: [],
    alumni_schools: [],
    constraints: { needs_sponsorship: true },
  };
}

export function profileNeedsOnboarding(profile) {
  return !profile?.tracks?.length;
}

export function newTrack() {
  return {
    id: `track_${Date.now()}`,
    label: "",
    priority: 2,
    titlesText: "",
  };
}

export function newAvoidTrack() {
  return { id: `avoid_${Date.now()}`, label: "", titlesText: "" };
}

/** Build API-ready profile from onboarding form state. */
export function buildProfileFromForm(form) {
  return {
    tracks: form.tracks.map((t) => ({
      id: t.id.trim() || `track_${Date.now()}`,
      label: t.label.trim() || "Untitled track",
      priority: Math.max(1, Math.min(3, Number(t.priority) || 2)),
      example_titles: linesToList(t.titlesText),
    })),
    avoid_tracks: form.avoidTracks.map((t) => ({
      id: t.id.trim() || `avoid_${Date.now()}`,
      label: t.label.trim() || "Avoid",
      example_titles: linesToList(t.titlesText),
    })),
    locations: {
      summary: form.locSummary.trim(),
      tier_1: linesToList(form.locTier1),
      tier_2: linesToList(form.locTier2),
      tier_3: linesToList(form.locTier3),
      remote_ok: form.remoteOk,
      relocation_ok: form.relocationOk,
    },
    dealbreakers: linesToList(form.dealbreakers),
    preferences: linesToList(form.preferences),
    technical_penalties: linesToList(form.technicalPenalties),
    alumni_schools: linesToList(form.alumniSchools),
    constraints: { needs_sponsorship: form.needsSponsorship },
  };
}

export function formFromProfile(profile) {
  const p = profile || emptyProfile();
  const tracks = (p.tracks || []).map((t) => ({
      id: t.id,
      label: t.label,
      priority: t.priority,
      titlesText: listToLines(t.example_titles),
    }));
  return {
    tracks: tracks.length ? tracks : [newTrack()],
    avoidTracks: (p.avoid_tracks || []).map((t) => ({
      id: t.id,
      label: t.label,
      titlesText: listToLines(t.example_titles),
    })),
    locSummary: p.locations?.summary || "",
    locTier1: listToLines(p.locations?.tier_1),
    locTier2: listToLines(p.locations?.tier_2),
    locTier3: listToLines(p.locations?.tier_3),
    remoteOk: p.locations?.remote_ok !== false,
    relocationOk: p.locations?.relocation_ok !== false,
    dealbreakers: listToLines(p.dealbreakers),
    preferences: listToLines(p.preferences),
    technicalPenalties: listToLines(p.technical_penalties),
    alumniSchools: listToLines(p.alumni_schools),
    needsSponsorship: p.constraints?.needs_sponsorship !== false,
  };
}
