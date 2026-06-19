const API = import.meta.env.VITE_API_URL || "http://3.128.164.130:8000";

export async function analyzeJob({ jd_text, company, title, resume_text }) {
  const body = { jd_text, company: company || null, title: title || null };
  if (resume_text?.trim()) body.resume_text = resume_text.trim();

  const res = await fetch(`${API.replace(/\/$/, "")}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  if (!res.ok) throw new Error(text || `HTTP ${res.status}`);
  return JSON.parse(text);
}

export { API };
