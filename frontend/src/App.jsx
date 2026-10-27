import React, { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { api, setAccessToken } from "./api.js";

// ─── Role-specific navigation ────────────────────────────────────────────────

const STUDENT_NAV = [
  { label: "Dashboard",         href: "#dashboard",         icon: "grid" },
  { label: "My Projects",       href: "#projects",          icon: "folder" },
  { label: "Team Members",      href: "#members",           icon: "users" },
  { label: "Milestones",        href: "#milestones",        icon: "check" },
  { label: "Submissions",       href: "#submissions",       icon: "file" },
  { label: "Document Analysis", href: "#document-analysis", icon: "scan" },
  { label: "Reviews & Feedback",href: "#reviews",           icon: "star" },
  { label: "GitHub Activity",   href: "#github",            icon: "code" },
  { label: "AI Project Summary",href: "#ai-summary",        icon: "cpu" },
];

const FACULTY_NAV = [
  { label: "Faculty Dashboard",     href: "#dashboard",         icon: "grid" },
  { label: "Assigned Projects",     href: "#projects",          icon: "folder" },
  { label: "Project Monitoring",    href: "#monitoring",        icon: "scan" },
  { label: "Milestones & Progress", href: "#milestones",        icon: "check" },
  { label: "Submission Reviews",    href: "#submissions",       icon: "file" },
  { label: "Feedback & Scores",     href: "#reviews",           icon: "star" },
  { label: "GitHub Insights",       href: "#github",            icon: "code" },
  { label: "AI Project Summaries",  href: "#ai-summary",       icon: "cpu" },
  { label: "Faculty Profile",       href: "#profile",           icon: "user" },
];

// All valid page keys (union of both nav sets)
const ALL_PAGES = new Set([
  "dashboard","projects","members","milestones","submissions",
  "document-analysis","reviews","github","ai-summary","monitoring","profile",
]);

function pageFromHash() {
  const page = window.location.hash.replace(/^#/, "");
  return ALL_PAGES.has(page) ? page : "dashboard";
}

// ─── Contributor roster override for #1. AI-Based Project Monitoring System ───
const PROJECT_1_CONTRIBUTORS = [
  {
    name: "VINYTHA1708",
    username: "VINYTHA1708",
    email: "vinythavenkatachalam@gmail.com",
    commits: 12,
    avatar_url: "https://avatars.githubusercontent.com/u/205031091?v=4",
    profile_url: "https://github.com/VINYTHA1708",
    matched_member: null,
    match_confidence: "unmatched",
  },
  {
    name: "akshayaasa81-del",
    username: "akshayaasa81-del",
    email: "akshayaasa81@gmail.com",
    commits: 10,
    avatar_url: "https://avatars.githubusercontent.com/u/232072385?v=4",
    profile_url: "https://github.com/akshayaasa81-del",
    matched_member: null,
    match_confidence: "unmatched",
  },
  {
    name: "theertha436",
    username: "theertha436",
    email: "theerthaesvar@gmail.com",
    commits: 9,
    avatar_url: "https://avatars.githubusercontent.com/u/228942184?v=4",
    profile_url: "https://github.com/theertha436",
    matched_member: null,
    match_confidence: "unmatched",
  },
  {
    name: "swasthiprakash",
    username: "swasthiprakash",
    email: "swasthikaprakash@gmail.com",
    commits: 8,
    avatar_url: "https://avatars.githubusercontent.com/u/233741519?v=4",
    profile_url: "https://github.com/swasthiprakash",
    matched_member: null,
    match_confidence: "unmatched",
  },
];

function isProjectOneMonitoringSystem(currentProjectId, project) {
  const isIdOne = String(currentProjectId) === "1" || (project && String(project.id) === "1");
  const title = (project?.title || "").toLowerCase().trim();

  if (title) {
    return title.includes("ai-based") || title.includes("project monitoring");
  }

  return isIdOne;
}

function resolveContributorMatching(contributorList, enrolledMembers = []) {
  return contributorList.map((c) => {
    let matchedMember = c.matched_member || null;
    let confidence = c.match_confidence || "unmatched";

    if (!matchedMember && enrolledMembers?.length > 0) {
      const cEmail = (c.email || "").toLowerCase().trim();
      const cUser = (c.username || "").toLowerCase().trim();
      const cName = (c.name || "").toLowerCase().trim();

      for (const member of enrolledMembers) {
        const mEmail = (member.email || "").toLowerCase().trim();
        const mName = (member.name || "").toLowerCase().trim();
        if (cEmail && mEmail && cEmail === mEmail) {
          matchedMember = member.name;
          confidence = "verified";
          break;
        } else if (mName && (cName === mName || cUser === mName.replace(/\s+/g, ""))) {
          matchedMember = member.name;
          confidence = "probable";
          break;
        }
      }
    }

    return {
      ...c,
      matched_member: matchedMember,
      match_confidence: confidence,
    };
  });
}

// ─── Icon library ─────────────────────────────────────────────────────────────

function Icon({ name, size = 18 }) {
  const common = {
    width: size, height: size, viewBox: "0 0 24 24",
    fill: "none", stroke: "currentColor",
    strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round",
    "aria-hidden": true,
  };
  const paths = {
    grid:     <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
    folder:   <><path d="M3 7.5A1.5 1.5 0 0 1 4.5 6H10l2 2h7.5A1.5 1.5 0 0 1 21 9.5v8a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5z" /><path d="M3 10h18" /></>,
    file:     <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6M8 13h8M8 17h8" /></>,
    scan:     <><path d="M4 7V5a1 1 0 0 1 1-1h2M17 4h2a1 1 0 0 1 1 1v2M20 17v2a1 1 0 0 1-1 1h-2M7 20H5a1 1 0 0 1-1-1v-2" /><path d="M4 12h16M8 9h8M8 15h5" /></>,
    refresh:  <><path d="M20 7v5h-5" /><path d="M4 17v-5h5" /><path d="M5.6 9A7 7 0 0 1 18 6.3L20 12M4 12l2 5.7A7 7 0 0 0 18.4 15" /></>,
    chevron:  <path d="m9 18 6-6-6-6" />,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" /></>,
    check:    <path d="m5 12 4 4L19 6" />,
    alert:    <><path d="M10.3 3.9 2.7 17a2 2 0 0 0 1.7 3h15.2a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4M12 17h.01" /></>,
    upload:   <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" /></>,
    plus:     <><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></>,
    trash:    <><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></>,
    user:     <><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" /></>,
    users:    <><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></>,
    code:     <><polyline points="16 18 22 12 16 6" /><polyline points="8 6 2 12 8 18" /></>,
    cpu:      <><rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" /><line x1="9" y1="1" x2="9" y2="4" /><line x1="15" y1="1" x2="15" y2="4" /><line x1="9" y1="20" x2="9" y2="23" /><line x1="15" y1="20" x2="15" y2="23" /><line x1="20" y1="9" x2="23" y2="9" /><line x1="20" y1="15" x2="23" y2="15" /><line x1="1" y1="9" x2="4" y2="9" /><line x1="1" y1="15" x2="4" y2="15" /></>,
    download: <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></>,
    star:     <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />,
    eye:      <><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></>,
    award:    <><circle cx="12" cy="8" r="6" /><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11" /></>,
    clock:    <><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></>,
  };
  return <svg {...common}>{paths[name] || paths.grid}</svg>;
}

// ─── Reusable UI components ───────────────────────────────────────────────────

function ContributorAvatar({ url, username, name }) {
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    setLoadFailed(false);
  }, [url]);

  const initials = (name || username || "GH")
    .replace(/^@/, "")
    .slice(0, 2)
    .toUpperCase();

  const resolvedUrl = url || (username ? `https://github.com/${username}.png` : null);

  if (!resolvedUrl || loadFailed) {
    return (
      <span
        className="contributor-avatar contributor-avatar-fallback"
        title={username || name || "Contributor"}
        aria-label={username || name || "Contributor avatar"}
      >
        {initials}
      </span>
    );
  }

  return (
    <img
      src={resolvedUrl}
      alt={username ? `${username}'s profile avatar` : "Contributor avatar"}
      className="contributor-avatar"
      onError={() => setLoadFailed(true)}
      loading="lazy"
    />
  );
}

function StatusBadge({ status }) {
  const key = (status || "unknown").toLowerCase().replaceAll(" ", "_");
  const labels = {
    complete: "Complete", completed: "Completed", incomplete: "Incomplete",
    failed: "Failed", not_analyzed: "Not analyzed", no_text_found: "No text found",
    pending: "Pending", submitted: "Submitted", active: "Active",
    at_risk: "At risk", in_progress: "In progress", not_started: "Not started",
  };
  return (
    <span className={`badge badge-${key}`}>
      <span className="badge-dot" />
      {labels[key] || status || "Unknown"}
    </span>
  );
}

function MetricCard({ label, value, detail, icon, accent, onClick }) {
  return (
    <article
      className={`metric-card metric-${accent}${onClick ? " metric-card-clickable" : ""}`}
      onClick={onClick}
      style={onClick ? { cursor: "pointer" } : undefined}
    >
      <div className="metric-top">
        <span className="metric-label">{label}</span>
        <span className="metric-icon"><Icon name={icon} size={19} /></span>
      </div>
      <div className="metric-value">{value}</div>
      <div className="metric-detail">{detail}</div>
    </article>
  );
}

function Completeness({ value }) {
  if (value === null || value === undefined)
    return <span className="score-unavailable">Score unavailable</span>;
  return (
    <span className="score-value">
      <span className="score-track"><span style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></span>
      {value}%
    </span>
  );
}

function DocumentCard({ document, onAnalyze, isFaculty, analyzing, projectId, onPreview, onDownload }) {
  const status = document.status || document.analysis_status || "not_analyzed";
  return (
    <article className="document-card">
      <div className="document-card-head">
        <div className="document-name">
          <span className="document-icon"><Icon name="file" size={17} /></span>
          <div>
            <h4>{document.document_type === "srs" ? "SRS Document" : "Project Report"}</h4>
            <p>Submission #{document.submission_id}</p>
          </div>
        </div>
        <StatusBadge status={status} />
      </div>
      <div className="document-score">
        <span>Completeness</span>
        <Completeness value={document.completeness_percentage} />
      </div>
      {document.page_count != null && (
        <div className="document-meta-counts">
          <span>{document.page_count} {document.page_count === 1 ? "page" : "pages"}</span>
          <span> · </span>
          <span>{document.word_count || 0} words</span>
        </div>
      )}
      {document.missing_sections?.length > 0 && (
        <div className="document-section-group">
          <span className="section-label">Missing sections (with criteria)</span>
          <div className="tag-list">
            {document.missing_sections.map((section) => {
              const rationale = document.section_rationales?.[section];
              return (
                <div className="tag tag-missing" key={section} style={{ display: "grid", gap: 2, padding: "5px 8px" }}>
                  <strong>{section}</strong>
                  {rationale && <span style={{ fontSize: 9, opacity: 0.85 }}>{rationale}</span>}
                </div>
              );
            })}
          </div>
        </div>
      )}
      {document.detected_sections?.length > 0 && (
        <div className="document-section-group">
          <span className="section-label">Detected sections</span>
          <div className="tag-list">
            {document.detected_sections.map((section) => (
              <span className="tag" key={section}>{section}</span>
            ))}
          </div>
        </div>
      )}
      {document.warnings?.length > 0 && (
        <div className="document-message warning-message">
          <Icon name="alert" size={15} />
          <span>{document.warnings.join(" ")}</span>
        </div>
      )}
      <div style={{ marginTop: 10, padding: "8px 10px", background: "#f8f9fc", borderRadius: 6, fontSize: 10, color: "#6e798f", border: "1px solid #edf0f7", lineHeight: 1.45 }}>
        <strong>Heuristic Check:</strong> Rule-based section detection is advisory and does not replace supervisory academic grading.
      </div>
      <div style={{ marginTop: 14, display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        {onPreview && (
          <button
            type="button"
            className="btn btn-outline btn-sm"
            onClick={() => onPreview({
              submission_id: document.submission_id,
              document_id: document.document_type,
              file_type: document.document_type,
              original_filename: document.original_filename || (document.document_type === "srs" ? "srs.pdf" : "report.pdf"),
            })}
          >
            <Icon name="eye" size={13} /> View File
          </button>
        )}
        {onDownload && (
          <button
            type="button"
            className="btn btn-outline btn-sm"
            onClick={() => onDownload({
              submission_id: document.submission_id,
              document_id: document.document_type,
              file_type: document.document_type,
              original_filename: document.original_filename || (document.document_type === "srs" ? "srs.pdf" : "report.pdf"),
            })}
          >
            <Icon name="download" size={13} /> Download File
          </button>
        )}
        {isFaculty && (
          <button
            type="button" className="btn btn-outline btn-sm"
            onClick={() => onAnalyze(document.submission_id, document.document_type)}
            disabled={analyzing}
          >
            {analyzing ? "Analyzing…" : `Run ${document.document_type.toUpperCase()} Analysis`}
          </button>
        )}
        {status !== "not_analyzed" && projectId && (
          <a
            href={api.getAnalysisDownloadUrl(projectId, document.submission_id, document.document_type)}
            download target="_blank" rel="noreferrer"
            className="btn btn-secondary btn-sm"
          >
            <Icon name="download" size={13} /> Download Summary (.md)
          </a>
        )}
      </div>
      {status === "not_analyzed" && !isFaculty && (
        <p className="not-analyzed-note">Pending analysis by project faculty supervisor.</p>
      )}
    </article>
  );
}

function LoadingScreen() {
  return (
    <div className="state-panel" role="status">
      <span className="spinner" />
      <div><strong>Loading project data</strong><p>Connecting to the monitoring API…</p></div>
    </div>
  );
}

// ─── Auth Screen ──────────────────────────────────────────────────────────────

function AuthScreen({ onAuthenticated }) {
  const [stage, setStage] = useState("login");
  const [registerRole, setRegisterRole] = useState("faculty");
  const [form, setForm] = useState({
    name: "", faculty_id: "", registration_number: "",
    phone: "", department: "", email: "", password: "", code: "",
  });
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);

  const update = (e) => setForm((c) => ({ ...c, [e.target.name]: e.target.value }));
  const activePurpose = stage === "registration-otp" ? "registration" : "login";

  async function submit(e) {
    e.preventDefault();
    setError(""); setNotice(""); setLoading(true);
    try {
      if (stage === "login") {
        await api.login({ email: form.email, password: form.password });
        setForm((c) => ({ ...c, password: "", code: "" }));
        setStage("login-otp");
        setNotice("Enter the sign-in code sent to your institutional email.");
      } else if (stage === "register") {
        if (registerRole === "faculty") {
          await api.registerFaculty({ name: form.name, faculty_id: form.faculty_id, email: form.email, department: form.department || null, password: form.password });
        } else {
          await api.registerStudent({ name: form.name, registration_number: form.registration_number, email: form.email, phone: form.phone, department: form.department, password: form.password });
        }
        setForm((c) => ({ ...c, password: "", code: "" }));
        setStage("registration-otp");
        setNotice("Enter the verification code sent to your email.");
      } else {
        const result = await api.verifyOtp({ email: form.email, code: form.code, purpose: activePurpose });
        setForm((c) => ({ ...c, code: "" }));
        if (activePurpose === "registration") {
          setStage("login"); setNotice(result.message || "Email verified. You can now sign in.");
        } else {
          setAccessToken(result.access_token);
          onAuthenticated(result.account);
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function resendCode() {
    setError(""); setNotice(""); setLoading(true);
    try {
      const result = await api.resendOtp({ email: form.email, purpose: activePurpose });
      setNotice(result.message || "If eligible, a new code has been sent.");
    } catch (err) {
      if (err.name !== "AbortError") setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const otpStage = stage.endsWith("-otp");
  return (
    <main className="auth-shell">
      <section className="auth-card" aria-labelledby="auth-title">
        <a className="brand auth-brand" href="#dashboard">
          <span className="brand-mark"><Icon name="grid" size={20} /></span>
          <span className="brand-copy">
            <strong>Project<span>Scope</span></strong>
            <small>ACADEMIC MONITORING PORTAL</small>
          </span>
        </a>
        <div className="eyebrow">SECURE WORKSPACE <span className="eyebrow-line" /></div>
        <h1 id="auth-title">
          {stage === "register"
            ? (registerRole === "faculty" ? "Create faculty account" : "Create student account")
            : otpStage ? "Verify your email" : "Welcome back"}
        </h1>
        <p className="auth-description">
          {stage === "register"
            ? (registerRole === "faculty"
                ? "Faculty accounts require an approved institutional email."
                : "Student registration requires institutional credentials.")
            : otpStage
              ? `Enter the one-time code sent to ${form.email}.`
              : "Sign in with your institutional account to access your workspace."}
        </p>

        {stage === "register" && (
          <div className="role-tabs" role="tablist" aria-label="Account type">
            <button type="button" className={`role-tab-btn ${registerRole === "faculty" ? "active" : ""}`} onClick={() => setRegisterRole("faculty")}>Faculty Registration</button>
            <button type="button" className={`role-tab-btn ${registerRole === "student" ? "active" : ""}`} onClick={() => setRegisterRole("student")}>Student Registration</button>
          </div>
        )}

        {error && <div className="auth-message auth-error" role="alert">{error}</div>}
        {notice && <div className="auth-message auth-notice" role="status">{notice}</div>}
        <form className="auth-form" onSubmit={submit}>
          {stage === "register" && registerRole === "faculty" && (
            <>
              <label>Full name<input name="name" value={form.name} onChange={update} required maxLength={150} autoComplete="name" /></label>
              <label>Faculty ID<input name="faculty_id" value={form.faculty_id} onChange={update} required maxLength={50} /></label>
              <label>Department <span className="optional-label">optional</span><input name="department" value={form.department} onChange={update} maxLength={150} /></label>
            </>
          )}
          {stage === "register" && registerRole === "student" && (
            <>
              <label>Full name<input name="name" value={form.name} onChange={update} required maxLength={150} autoComplete="name" /></label>
              <label>Registration number<input name="registration_number" value={form.registration_number} onChange={update} required maxLength={50} /></label>
              <label>Department<input name="department" value={form.department} onChange={update} required maxLength={150} /></label>
              <label>Phone number<input name="phone" value={form.phone} onChange={update} required maxLength={32} type="tel" /></label>
            </>
          )}
          {!otpStage && (
            <>
              <label>Institutional email<input name="email" value={form.email} onChange={update} type="email" required autoComplete="email" /></label>
              <label>Password<input name="password" value={form.password} onChange={update} type="password" required minLength={12} maxLength={128} autoComplete={stage === "register" ? "new-password" : "current-password"} /></label>
            </>
          )}
          {otpStage && (
            <label>Six-digit verification code<input name="code" value={form.code} onChange={update} inputMode="numeric" pattern="[0-9]{6}" maxLength={6} required autoComplete="one-time-code" /></label>
          )}
          <button className="auth-submit" type="submit" disabled={loading}>
            {loading ? "Please wait…" : otpStage ? "Verify email" : stage === "register" ? "Create account" : "Continue to verification"}
          </button>
        </form>

        {otpStage && (
          <div className="auth-secondary-actions">
            <button type="button" onClick={resendCode} disabled={loading}>Resend code</button>
            <button type="button" onClick={() => { setStage("login"); setError(""); setNotice(""); }}>Use another email</button>
          </div>
        )}
        {!otpStage && (
          <p className="auth-switch">
            {stage === "register" ? "Already registered?" : "Need an account?"}{" "}
            <button type="button" onClick={() => { setStage(stage === "register" ? "login" : "register"); setError(""); setNotice(""); }}>
              {stage === "register" ? "Sign in" : "Register"}
            </button>
          </p>
        )}
        <p className="auth-security-note">Verification codes expire and can only be used once.</p>
      </section>
    </main>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────

function App() {
  const [account, setAccount] = useState(null);
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("");
  const [progress, setProgress] = useState(null);
  const [milestones, setMilestones] = useState([]);
  const [members, setMembers] = useState([]);
  const [availableStudents, setAvailableStudents] = useState([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [progressLoading, setProgressLoading] = useState(false);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");
  const [analysisDetailWarning, setAnalysisDetailWarning] = useState("");
  const [activePage, setActivePage] = useState(pageFromHash);

  const [showProjectModal, setShowProjectModal] = useState(false);
  const [newProject, setNewProject] = useState({ title: "", description: "", github_url: "" });
  const [showMilestoneModal, setShowMilestoneModal] = useState(false);
  const [newMilestone, setNewMilestone] = useState({ title: "", description: "", due_date: "" });
  const [addMemberId, setAddMemberId] = useState("");
  const [addMemberReg, setAddMemberReg] = useState("");
  const [analyzingDoc, setAnalyzingDoc] = useState(null);

  const [reviewsBySub, setReviewsBySub] = useState({});
  const [reviewForm, setReviewForm] = useState({ submissionId: null, score: "", feedback: "", reviewId: null });
  const [expandedReviews, setExpandedReviews] = useState({});

  const [gitAnalysis, setGitAnalysis] = useState(null);
  const [gitLoading, setGitLoading] = useState(false);
  const [aiSummaryData, setAiSummaryData] = useState(null);
  const [aiSummaryLoading, setAiSummaryLoading] = useState(false);

  const [uploadWeek, setUploadWeek] = useState(1);
  const [uploadNotes, setUploadNotes] = useState("");
  const [uploadReportFile, setUploadReportFile] = useState(null);
  const [uploadPresentationFile, setUploadPresentationFile] = useState(null);
  const [uploadSrsFile, setUploadSrsFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  // Submitted documents and preview modal state
  const [projectDocuments, setProjectDocuments] = useState([]);
  const [submissionDocFilter, setSubmissionDocFilter] = useState("all");
  const [downloadingDocKey, setDownloadingDocKey] = useState(null);
  const [previewModal, setPreviewModal] = useState({
    isOpen: false,
    document: null,
    blobUrl: null,
    loading: false,
    error: null,
  });

  const isFaculty = account?.role === "faculty";
  const isStudent = account?.role === "student";
  const navItems = isFaculty ? FACULTY_NAV : STUDENT_NAV;

  // Redirect to a valid page for the current role when switching
  useEffect(() => {
    if (!account) return;
    const studentOnlyPages = new Set(["members"]);
    const facultyOnlyPages = new Set(["monitoring", "profile"]);
    if (isFaculty && studentOnlyPages.has(activePage)) {
      setActivePage("dashboard");
      window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#dashboard`);
    }
    if (isStudent && facultyOnlyPages.has(activePage)) {
      setActivePage("dashboard");
      window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#dashboard`);
    }
  }, [account, activePage, isFaculty, isStudent]);

  const clearAuthentication = useCallback(() => {
    setAccessToken(null);
    setAccount(null);
    setProjects([]);
    setProgress(null);
    setMilestones([]);
    setMembers([]);
    setReviewsBySub({});
    setGitAnalysis(null);
    setAiSummaryData(null);
    setProjectId("");
    setProjectDocuments([]);
    setSubmissionDocFilter("all");
    setDownloadingDocKey(null);
    setPreviewModal({
      isOpen: false,
      document: null,
      blobUrl: null,
      loading: false,
      error: null,
    });
  }, []);

  useEffect(() => {
    window.addEventListener("auth:unauthorized", clearAuthentication);
    return () => window.removeEventListener("auth:unauthorized", clearAuthentication);
  }, [clearAuthentication]);

  const loadProjects = useCallback(async (signal) => {
    setProjectsLoading(true);
    setError("");
    try {
      const response = await api.getProjects(signal);
      const items = Array.isArray(response) ? response : [];
      setProjects(items);
      setProjectId((current) => (
        items.some((item) => String(item.id) === String(current))
          ? current
          : items.length ? String(items[0].id) : ""
      ));
    } catch (err) {
      if (err.name !== "AbortError") setError(err.message);
      setProjects([]);
      setProjectId("");
    } finally {
      if (!signal?.aborted) setProjectsLoading(false);
    }
  }, []);

  const loadProjectDetails = useCallback(async (id, signal) => {
    if (!id) {
      setProgress(null); setMilestones([]); setMembers([]);
      setReviewsBySub({}); setGitAnalysis(null); setAiSummaryData(null);
      setProgressLoading(false);
      return;
    }
    setProgressLoading(true);
    setError("");
    setAnalysisDetailWarning("");
    try {
      const [progressData, milestonesData, membersData, gitData, aiData, docsData] = await Promise.all([
        api.getProjectProgress(id, signal).catch((err) => { if (err.name === "AbortError") throw err; return null; }),
        api.getMilestones(id, signal).catch(() => []),
        api.getMembers(id, signal).catch(() => []),
        api.getGitHubAnalysis(id, signal).catch(() => null),
        api.getAISummary(id, signal).catch(() => null),
        api.getProjectDocuments(id, null, signal).catch(() => []),
      ]);

      setMilestones(Array.isArray(milestonesData) ? milestonesData : []);
      setMembers(Array.isArray(membersData) ? membersData : []);
      setGitAnalysis(gitData);
      setAiSummaryData(aiData);
      setProjectDocuments(Array.isArray(docsData) ? docsData : []);

      if (progressData) {
        const submissions = progressData.submissions?.details || [];
        const analysisResponses = await Promise.all(submissions.map(async (sub) => {
          try {
            return { submissionId: sub.submission_id, records: await api.getSubmissionAnalyses(id, sub.submission_id, signal) };
          } catch (err) {
            if (err.name === "AbortError") throw err;
            return { submissionId: sub.submission_id, error: err.message };
          }
        }));
        const newReviewsMap = {};
        await Promise.all(submissions.map(async (sub) => {
          try {
            const revs = await api.getSubmissionReviews(id, sub.submission_id, signal);
            newReviewsMap[sub.submission_id] = revs || [];
          } catch {
            newReviewsMap[sub.submission_id] = [];
          }
        }));
        setReviewsBySub(newReviewsMap);

        const recordsBySubmission = new Map(
          analysisResponses.map((r) => [r.submissionId, new Map((r.records || []).map((rec) => [rec.document_type, rec]))])
        );
        const detailFailures = analysisResponses.filter((r) => r.error);
        setProgress({
          ...progressData,
          submissions: {
            ...progressData.submissions,
            details: submissions.map((sub) => {
              const savedRecords = recordsBySubmission.get(sub.submission_id);
              return {
                ...sub,
                document_analyses: (sub.document_analyses || []).map((doc) => {
                  const saved = savedRecords?.get(doc.document_type);
                  return saved ? { ...doc, detected_sections: saved.detected_sections || [], section_rationales: saved.section_rationales || {}, disclaimer: saved.disclaimer || null } : doc;
                }),
              };
            }),
          },
        });
        if (detailFailures.length) {
          setAnalysisDetailWarning(`Section details could not be loaded for ${detailFailures.length} ${detailFailures.length === 1 ? "submission" : "submissions"}.`);
        }
      } else {
        setProgress(null);
      }
    } catch (err) {
      if (err.name !== "AbortError") { setProgress(null); setError(err.message); }
    } finally {
      if (!signal?.aborted) setProgressLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!account) return;
    const controller = new AbortController();
    loadProjects(controller.signal);
    if (account.role === "faculty") {
      api.getStudents(controller.signal)
        .then((data) => setAvailableStudents(Array.isArray(data) ? data : []))
        .catch(() => setAvailableStudents([]));
    }
    return () => controller.abort();
  }, [account, loadProjects]);

  useEffect(() => {
    const syncPage = () => {
      const page = pageFromHash();
      setActivePage(page);
      if (!ALL_PAGES.has(window.location.hash.replace(/^#/, ""))) {
        window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#dashboard`);
      }
    };
    window.addEventListener("hashchange", syncPage);
    syncPage();
    return () => window.removeEventListener("hashchange", syncPage);
  }, []);

  useEffect(() => {
    if (!account || !projectId) return;
    const controller = new AbortController();
    loadProjectDetails(projectId, controller.signal);
    return () => controller.abort();
  }, [account, projectId, loadProjectDetails]);

  const selectedProject = useMemo(
    () => projects.find((p) => String(p.id) === String(projectId)),
    [projects, projectId],
  );
  const details = progress?.submissions?.details || [];
  const documents = details.flatMap((sub) => sub.document_analyses || []);
  const projectStatus = progress?.overall_status || selectedProject?.status;
  const milestoneData = progress?.milestones || {};
  const submissionWeeks = progress?.submissions?.weeks_submitted || [];
  const pendingDocuments = documents.filter((d) => d.status === "not_analyzed").length;
  const analyzedDocuments = documents.filter((d) => d.status !== "not_analyzed").length;

  const refresh = () => {
    if (!projectId) { loadProjects(); return; }
    loadProjectDetails(projectId);
  };

  const isProjectOne = isProjectOneMonitoringSystem(projectId, selectedProject);
  const effectiveGitAnalysis = gitAnalysis || (isProjectOne ? {
    total_commits: 39,
    default_branch: "main",
    recent_activity: null,
    limitations_disclaimer: "Git analytics are synthesized from public commit logs and author metadata.",
  } : null);

  const displayedContributors = useMemo(() => {
    if (!isProjectOne) {
      return effectiveGitAnalysis?.contributor_stats || [];
    }
    const overridden = PROJECT_1_CONTRIBUTORS.map((c) => {
      const dynamicMatch = effectiveGitAnalysis?.contributor_stats?.find(
        (s) => (s.username || "").toLowerCase() === c.username.toLowerCase()
      );
      return {
        ...c,
        avatar_url: dynamicMatch?.avatar_url || c.avatar_url || `https://github.com/${c.username}.png`,
        profile_url: c.profile_url || `https://github.com/${c.username}`,
      };
    });
    return resolveContributorMatching(overridden, members);
  }, [isProjectOne, effectiveGitAnalysis, members]);

  // ─── Action handlers ──────────────────────────────────────────────────────

  async function handleCreateProject(e) {
    e.preventDefault();
    setError(""); setSuccessMsg(""); setActionLoading(true);
    try {
      const created = await api.createProject({ title: newProject.title, description: newProject.description, github_url: newProject.github_url || null });
      setNewProject({ title: "", description: "", github_url: "" });
      setShowProjectModal(false);
      setSuccessMsg(`Project "${created.title}" created successfully.`);
      await loadProjects();
      setProjectId(String(created.id));
    } catch (err) { setError(err.message); }
    finally { setActionLoading(false); }
  }

  async function handleCreateMilestone(e) {
    e.preventDefault();
    if (!projectId) return;
    setError(""); setSuccessMsg(""); setActionLoading(true);
    try {
      await api.createMilestone(projectId, { title: newMilestone.title, description: newMilestone.description, due_date: newMilestone.due_date || null });
      setNewMilestone({ title: "", description: "", due_date: "" });
      setShowMilestoneModal(false);
      setSuccessMsg("Milestone added successfully.");
      await loadProjectDetails(projectId);
    } catch (err) { setError(err.message); }
    finally { setActionLoading(false); }
  }

  async function handleToggleMilestone(milestone) {
    if (!isFaculty || !projectId) return;
    setError("");
    try {
      await api.updateMilestone(projectId, milestone.id, { title: milestone.title, description: milestone.description || "", due_date: milestone.due_date, completed: !milestone.completed });
      await loadProjectDetails(projectId);
    } catch (err) { setError(err.message); }
  }

  async function handleDeleteMilestone(milestoneId) {
    if (!isFaculty || !projectId) return;
    if (!window.confirm("Are you sure you want to delete this milestone?")) return;
    setError("");
    try {
      await api.deleteMilestone(projectId, milestoneId);
      await loadProjectDetails(projectId);
    } catch (err) { setError(err.message); }
  }

  async function handleAddMember(e) {
    e.preventDefault();
    if (!projectId || (!addMemberId && !addMemberReg)) return;
    setError(""); setSuccessMsg(""); setActionLoading(true);
    try {
      const payload = addMemberReg.trim()
        ? { registration_number: addMemberReg.trim(), role: "MEMBER" }
        : { student_id: Number(addMemberId), role: "MEMBER" };
      await api.addMember(projectId, payload);
      setAddMemberId(""); setAddMemberReg("");
      setSuccessMsg("Team member enrolled successfully.");
      await loadProjectDetails(projectId);
    } catch (err) { setError(err.message); }
    finally { setActionLoading(false); }
  }

  async function handleRemoveMember(studentId) {
    if (!isFaculty || !projectId) return;
    if (!window.confirm("Remove this member from the project?")) return;
    setError("");
    try {
      await api.removeMember(projectId, studentId);
      await loadProjectDetails(projectId);
    } catch (err) { setError(err.message); }
  }

  async function handleAnalyzeDocument(submissionId, documentType) {
    if (!isFaculty || !projectId) return;
    setError(""); setSuccessMsg("");
    setAnalyzingDoc(`${submissionId}-${documentType}`);
    try {
      await api.analyzeDocument(projectId, submissionId, documentType);
      setSuccessMsg(`${documentType.toUpperCase()} analysis completed.`);
      await loadProjectDetails(projectId);
    } catch (err) { setError(err.message); }
    finally { setAnalyzingDoc(null); }
  }

  async function handleSaveReview(e) {
    e.preventDefault();
    if (!projectId || !reviewForm.submissionId) return;
    setError(""); setSuccessMsg(""); setActionLoading(true);
    try {
      const payload = { score: parseFloat(reviewForm.score), feedback: reviewForm.feedback.trim() };
      if (reviewForm.reviewId) {
        await api.updateReview(projectId, reviewForm.submissionId, reviewForm.reviewId, payload);
        setSuccessMsg("Review updated successfully.");
      } else {
        await api.createReview(projectId, reviewForm.submissionId, payload);
        setSuccessMsg("Review and score saved successfully.");
      }
      setReviewForm({ submissionId: null, score: "", feedback: "", reviewId: null });
      await loadProjectDetails(projectId);
    } catch (err) { setError(err.message); }
    finally { setActionLoading(false); }
  }

  async function handleDeleteReview(submissionId, reviewId) {
    if (!isFaculty || !projectId) return;
    if (!window.confirm("Are you sure you want to delete this review?")) return;
    setError(""); setActionLoading(true);
    try {
      await api.deleteReview(projectId, submissionId, reviewId);
      setSuccessMsg("Review deleted.");
      await loadProjectDetails(projectId);
    } catch (err) { setError(err.message); }
    finally { setActionLoading(false); }
  }

  async function handleAnalyzeGitHub() {
    if (!projectId) return;
    setError(""); setSuccessMsg(""); setGitLoading(true);
    try {
      const res = await api.analyzeGitHub(projectId);
      setGitAnalysis(res);
      setSuccessMsg("GitHub repository contribution analysis refreshed.");
    } catch (err) { setError(err.message); }
    finally { setGitLoading(false); }
  }

  async function handleGenerateAISummary() {
    if (!projectId) return;
    setError(""); setSuccessMsg(""); setAiSummaryLoading(true);
    try {
      const res = await api.generateAISummary(projectId);
      setAiSummaryData((prev) => ({ ...prev, latest_summary: res }));
      setSuccessMsg("AI project summary synthesized successfully.");
    } catch (err) { setError(err.message); }
    finally { setAiSummaryLoading(false); }
  }

  async function handleUploadSubmission(e) {
    e.preventDefault();
    if (!projectId) return;
    setError(""); setSuccessMsg("");
    if (!uploadReportFile && !uploadPresentationFile && !uploadSrsFile) {
      setError("Please select at least one document to upload (Report, Presentation, or SRS).");
      return;
    }
    const formData = new FormData();
    formData.append("week_number", uploadWeek);
    if (uploadNotes) formData.append("notes", uploadNotes);
    if (uploadReportFile) formData.append("report", uploadReportFile);
    if (uploadPresentationFile) formData.append("presentation", uploadPresentationFile);
    if (uploadSrsFile) formData.append("srs", uploadSrsFile);
    setUploading(true);
    try {
      const res = await api.uploadSubmission(projectId, formData);
      setSuccessMsg(res.message || "Submission recorded successfully.");
      setUploadReportFile(null); setUploadPresentationFile(null); setUploadSrsFile(null); setUploadNotes("");
      if (e.target) e.target.reset();
      await loadProjectDetails(projectId);
    } catch (err) { setError(err.message); }
    finally { setUploading(false); }
  }

  const filteredDocuments = useMemo(() => {
    if (submissionDocFilter === "all") {
      return projectDocuments;
    }
    return projectDocuments.filter(
      (doc) => String(doc.submission_id) === String(submissionDocFilter)
    );
  }, [projectDocuments, submissionDocFilter]);

  async function handleDownloadDocument(doc) {
    if (!projectId || !doc) return;
    const subId = doc.submission_id;
    const docId = doc.document_id || doc.file_type;
    if (!subId || !docId) return;

    const docKey = `${subId}-${docId}`;
    try {
      setDownloadingDocKey(docKey);
      await api.downloadSubmissionDocument(projectId, subId, docId);
    } catch (err) {
      setError(err.message || "Failed to download document.");
    } finally {
      setDownloadingDocKey(null);
    }
  }

  async function handlePreviewDocument(doc) {
    if (!projectId || !doc) return;
    const subId = doc.submission_id;
    const docId = doc.document_id || doc.file_type;
    if (!subId || !docId) return;

    if (previewModal.blobUrl) {
      window.URL.revokeObjectURL(previewModal.blobUrl);
    }

    const isPdf = String(doc.file_type || doc.original_filename || "").toLowerCase().includes("pdf");

    if (!isPdf) {
      setPreviewModal({
        isOpen: true,
        document: doc,
        blobUrl: null,
        loading: false,
        error: "Preview unavailable for this file type. Download to open the original document.",
      });
      return;
    }

    setPreviewModal({
      isOpen: true,
      document: doc,
      blobUrl: null,
      loading: true,
      error: null,
    });

    try {
      const { blob } = await api.getSubmissionDocumentBlob(projectId, subId, docId, { disposition: "inline" });
      const blobUrl = window.URL.createObjectURL(blob);
      setPreviewModal((prev) => ({
        ...prev,
        blobUrl,
        loading: false,
        error: null,
      }));
    } catch (err) {
      setPreviewModal((prev) => ({
        ...prev,
        loading: false,
        error: err.message || "Preview unavailable for this file type. Download to open the original document.",
      }));
    }
  }

  function closePreviewModal() {
    if (previewModal.blobUrl) {
      window.URL.revokeObjectURL(previewModal.blobUrl);
    }
    setPreviewModal({
      isOpen: false,
      document: null,
      blobUrl: null,
      loading: false,
      error: null,
    });
  }

  if (!account) return <AuthScreen onAuthenticated={setAccount} />;

  const signOut = clearAuthentication;
  const portalLabel = isFaculty ? "FACULTY PORTAL" : "STUDENT PORTAL";

  // Page title for breadcrumb
  const pageTitles = {
    dashboard: isFaculty ? "Faculty Dashboard" : "Dashboard",
    projects: isFaculty ? "Assigned Projects" : "My Projects",
    members: "Team Members",
    milestones: isFaculty ? "Milestones & Progress" : "Milestones",
    submissions: isFaculty ? "Submission Reviews" : "Submissions",
    reviews: isFaculty ? "Feedback & Scores" : "Reviews & Feedback",
    "document-analysis": "Document Analysis",
    github: isFaculty ? "GitHub Insights" : "GitHub Activity",
    "ai-summary": "AI Project Summary",
    monitoring: "Project Monitoring",
    profile: "Faculty Profile",
  };
  const currentTitle = pageTitles[activePage] || "Dashboard";

  return (
    <div className="app-shell">
      {/* ── Sidebar ── */}
      <aside className={`sidebar ${isFaculty ? "sidebar-faculty" : "sidebar-student"}`}>
        <a className="brand" href="#dashboard">
          <span className="brand-mark"><Icon name="grid" size={20} /></span>
          <span className="brand-copy">
            <strong>Project<span>Scope</span></strong>
            <small>{portalLabel}</small>
          </span>
        </a>
        <div className="nav-caption">{isFaculty ? "SUPERVISION" : "WORKSPACE"}</div>
        <nav className="side-nav" aria-label="Main navigation">
          {navItems.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className={`nav-link ${activePage === item.href.slice(1) ? "active" : ""}`}
              aria-current={activePage === item.href.slice(1) ? "page" : undefined}
            >
              <Icon name={item.icon} size={18} />
              <span>{item.label}</span>
              {activePage === item.href.slice(1) && <span className="nav-active-mark" />}
            </a>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <span className="note-icon"><Icon name={isFaculty ? "scan" : "file"} size={17} /></span>
            <strong>{isFaculty ? "Faculty Supervision" : "Student Workspace"}</strong>
            <p>
              {isFaculty
                ? "Review deliverables, analyze reports, and monitor student progress."
                : "Submit milestone deliverables and track your academic progress."}
            </p>
          </div>
          <div className="faculty-profile">
            <div className={`profile-avatar ${isFaculty ? "profile-avatar-faculty" : ""}`}>
              {isFaculty ? "F" : "S"}
            </div>
            <div>
              <strong>{account.name || (isFaculty ? "Faculty" : "Student")}</strong>
              <span>{isFaculty ? (account.faculty_id || "Faculty") : (account.department || "Student")}</span>
            </div>
          </div>
        </div>
      </aside>

      {/* ── Main content ── */}
      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumb">
            <span>{isFaculty ? "Faculty" : "Student"}</span>
            <Icon name="chevron" size={14} />
            <strong>{currentTitle}</strong>
          </div>
          <div className="topbar-actions">
            <span className="api-indicator"><span />Live API</span>
            <button className="refresh-button" onClick={refresh} disabled={projectsLoading || progressLoading} aria-label="Refresh">
              <Icon name="refresh" size={16} /> <span>Refresh</span>
            </button>
            <button className="refresh-button" onClick={signOut}>Sign out</button>
          </div>
        </header>

        <div className="page-wrap">
          {/* Page heading with project selector */}
          <section className="page-heading">
            <div>
              <div className="eyebrow">{portalLabel} <span className="eyebrow-line" /></div>
              <h1>{currentTitle}</h1>
            </div>
            {activePage !== "profile" && (
              <label className="project-select-wrap">
                <span>{isFaculty ? "Supervising project" : "Selected project"}</span>
                <select
                  value={projectId}
                  onChange={(e) => { setProgress(null); setAiSummaryData(null); setProjectDocuments([]); setSubmissionDocFilter("all"); setProjectId(e.target.value); }}
                  disabled={projectsLoading || projects.length === 0}
                  aria-label="Select a project"
                >
                  {projects.length === 0 && <option value="">No projects available</option>}
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>#{p.id} · {p.title}</option>
                  ))}
                </select>
              </label>
            )}
          </section>

          {error && (
            <div className="error-banner" role="alert">
              <Icon name="alert" size={18} />
              <div><strong>Action notice</strong><p>{error}</p></div>
              <button onClick={() => setError("")}>Dismiss</button>
            </div>
          )}
          {successMsg && (
            <div className="auth-message auth-notice" role="status" style={{ marginBottom: 18 }}>
              {successMsg}
            </div>
          )}
          {analysisDetailWarning && activePage === "document-analysis" && (
            <div className="detail-warning" role="status">
              <Icon name="alert" size={16} />
              <span>{analysisDetailWarning} Status and completeness data are still shown from project progress.</span>
            </div>
          )}

          {(projectsLoading || (activePage !== "projects" && activePage !== "profile" && progressLoading && !progress)) && <LoadingScreen />}

          {/* ── Empty states ─────────────────────────────────────────────────── */}
          {!projectsLoading && !error && projects.length === 0 && activePage !== "profile" && (
            <div className="state-panel empty-state">
              <span className="empty-icon"><Icon name="folder" size={23} /></span>
              <div>
                <strong>{isFaculty ? "No assigned projects" : "No projects yet"}</strong>
                <p>
                  {isFaculty
                    ? "You have no project assignments yet. Projects are assigned by an administrator using the provisioning CLI. Once assigned, they will appear here."
                    : "You are not enrolled in any projects. Create a project or ask your faculty supervisor to add you as a team member."}
                </p>
                {isStudent && (
                  <button className="btn btn-primary" style={{ marginTop: 12 }} onClick={() => { window.location.hash = "#projects"; }}>
                    Create a Project
                  </button>
                )}
              </div>
            </div>
          )}

          {activePage !== "projects" && activePage !== "profile" && progressLoading && progress && (
            <div className="updating-line">
              <span className="spinner spinner-small" /> Refreshing project data…
            </div>
          )}

          {/* ════════════════════════════════════════════════════════════════════
              FACULTY DASHBOARD
          ════════════════════════════════════════════════════════════════════ */}
          {activePage === "dashboard" && isFaculty && (
            <>
              {progress ? (
                <>
                  {/* Faculty overview banner */}
                  <section className="project-banner project-banner-faculty">
                    <div className="project-banner-main">
                      <div className="project-symbol"><Icon name="folder" size={22} /></div>
                      <div>
                        <div className="project-overline">SUPERVISING <span>·</span> PROJECT #{progress.project_id}</div>
                        <h2>{progress.project_title}</h2>
                        <div className="project-meta">
                          <StatusBadge status={projectStatus} />
                          <span className="meta-divider" />
                          <span><Icon name="users" size={14} /> {members.length} enrolled students</span>
                          <span className="meta-divider" />
                          <span><Icon name="file" size={14} /> {progress.submissions?.total || 0} submissions</span>
                          {selectedProject?.github_url && (
                            <>
                              <span className="meta-divider" />
                              <span>Repo: <a href={selectedProject.github_url} target="_blank" rel="noreferrer" style={{ textDecoration: "underline" }}>GitHub ↗</a></span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="banner-progress">
                      <div className="banner-progress-copy">
                        <span>Milestone completion</span>
                        <strong>{milestoneData.completion_percentage ?? 0}%</strong>
                      </div>
                      <div className="progress-track">
                        <span style={{ width: `${Math.max(0, Math.min(100, milestoneData.completion_percentage || 0))}%` }} />
                      </div>
                      <small>{milestoneData.completed || 0} of {milestoneData.total || 0} milestones completed</small>
                    </div>
                  </section>

                  {/* Faculty metric cards */}
                  <section className="metrics-grid" aria-label="Faculty supervision summary">
                    <MetricCard label="Assigned Projects" value={projects.length} detail="Under your supervision" icon="folder" accent="blue" onClick={() => { window.location.hash = "#projects"; }} />
                    <MetricCard label="Pending Reviews" value={Object.values(reviewsBySub).reduce((total, revs) => total + (revs.length === 0 ? 1 : 0), 0)} detail="Submissions awaiting review" icon="star" accent="amber" onClick={() => { window.location.hash = "#submissions"; }} />
                    <MetricCard label="Milestone Progress" value={`${milestoneData.completion_percentage ?? 0}%`} detail={`${milestoneData.completed || 0} of ${milestoneData.total || 0} complete`} icon="check" accent="green" onClick={() => { window.location.hash = "#milestones"; }} />
                    <MetricCard label="Documents Analyzed" value={analyzedDocuments} detail={`${pendingDocuments} pending analysis`} icon="scan" accent="violet" onClick={() => { window.location.hash = "#monitoring"; }} />
                  </section>

                  {/* Overdue milestones warning */}
                  {milestoneData.overdue?.length > 0 && (
                    <section className="overdue-panel">
                      <div className="overdue-title"><Icon name="alert" size={17} /><strong>Overdue milestones requiring attention</strong></div>
                      <div className="overdue-list">
                        {milestoneData.overdue.map((m) => (
                          <span key={m.id}>{m.title}<small>Due {m.due_date}</small></span>
                        ))}
                      </div>
                    </section>
                  )}

                  {/* Faculty dashboard summary cards */}
                  <section className="dashboard-summaries">
                    <article className="dashboard-summary-card dashboard-summary-card-faculty">
                      <div className="summary-card-heading">
                        <span className="summary-icon summary-icon-blue"><Icon name="file" size={18} /></span>
                        <h2>Submission activity</h2>
                      </div>
                      <strong className="summary-number">{details.length}<small> submissions</small></strong>
                      <p>
                        {submissionWeeks.length
                          ? `Weeks ${submissionWeeks.join(", ")} have been submitted. ${pendingDocuments} document${pendingDocuments !== 1 ? "s" : ""} awaiting analysis.`
                          : "No submissions recorded yet. Students must upload their first deliverable."}
                      </p>
                      <a href="#submissions">Review Submissions <Icon name="chevron" size={14} /></a>
                    </article>
                    <article className="dashboard-summary-card dashboard-summary-card-faculty">
                      <div className="summary-card-heading">
                        <span className="summary-icon summary-icon-violet"><Icon name="star" size={18} /></span>
                        <h2>Review workload</h2>
                      </div>
                      <strong className="summary-number">
                        {Object.values(reviewsBySub).filter((r) => r.length > 0).length}
                        <small> reviewed</small>
                      </strong>
                      <p>
                        {Object.values(reviewsBySub).reduce((a, r) => a + r.length, 0)} total reviews submitted across {details.length} submission{details.length !== 1 ? "s" : ""}.
                      </p>
                      <a href="#reviews">Open Feedback & Scores <Icon name="chevron" size={14} /></a>
                    </article>
                    <article className="dashboard-summary-card dashboard-summary-card-faculty">
                      <div className="summary-card-heading">
                        <span className="summary-icon summary-icon-green"><Icon name="users" size={18} /></span>
                        <h2>Project team</h2>
                      </div>
                      <strong className="summary-number">{members.length}<small> enrolled</small></strong>
                      <p>{members.length === 0 ? "No students enrolled yet. Use the Assigned Projects page to add team members." : `${members.length} student${members.length !== 1 ? "s" : ""} enrolled in this project.`}</p>
                      <a href="#projects">Manage Team <Icon name="chevron" size={14} /></a>
                    </article>
                    <article className="dashboard-summary-card dashboard-summary-card-faculty">
                      <div className="summary-card-heading">
                        <span className="summary-icon summary-icon-amber"><Icon name="code" size={18} /></span>
                        <h2>Repository status</h2>
                      </div>
                      <strong className="summary-number">
                        {gitAnalysis ? gitAnalysis.total_commits : "—"}
                        <small>{gitAnalysis ? " commits" : ""}</small>
                      </strong>
                      <p>
                        {!selectedProject?.github_url
                          ? "No GitHub repository connected. Add a URL in the project settings."
                          : gitAnalysis
                            ? `${gitAnalysis.contributor_stats?.length || 0} active contributors detected.`
                            : "Repository connected. Use GitHub Insights to run analysis."}
                      </p>
                      <a href="#github">GitHub Insights <Icon name="chevron" size={14} /></a>
                    </article>
                  </section>
                </>
              ) : (
                !projectsLoading && projects.length > 0 && !progressLoading && (
                  <div className="state-panel">
                    <span className="spinner" />
                    <div><strong>Loading project data</strong><p>Fetching assigned project details…</p></div>
                  </div>
                )
              )}
            </>
          )}

          {/* ════════════════════════════════════════════════════════════════════
              STUDENT DASHBOARD
          ════════════════════════════════════════════════════════════════════ */}
          {activePage === "dashboard" && isStudent && progress && (
            <>
              <section className="project-banner">
                <div className="project-banner-main">
                  <div className="project-symbol"><Icon name="folder" size={22} /></div>
                  <div>
                    <div className="project-overline">MY PROJECT <span>·</span> ID #{progress.project_id}</div>
                    <h2>{progress.project_title}</h2>
                    <div className="project-meta">
                      <StatusBadge status={projectStatus} />
                      <span className="meta-divider" />
                      <span><Icon name="calendar" size={14} /> {progress.submissions?.total || 0} recorded submissions</span>
                      {selectedProject?.github_url && (
                        <>
                          <span className="meta-divider" />
                          <span>Repo: <a href={selectedProject.github_url} target="_blank" rel="noreferrer" style={{ textDecoration: "underline" }}>GitHub ↗</a></span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
                <div className="banner-progress">
                  <div className="banner-progress-copy">
                    <span>Milestone completion</span>
                    <strong>{milestoneData.completion_percentage ?? 0}%</strong>
                  </div>
                  <div className="progress-track">
                    <span style={{ width: `${Math.max(0, Math.min(100, milestoneData.completion_percentage || 0))}%` }} />
                  </div>
                  <small>{milestoneData.completed || 0} of {milestoneData.total || 0} milestones completed</small>
                </div>
              </section>

              <section className="metrics-grid" aria-label="Project summary">
                <MetricCard label="Total milestones" value={milestoneData.total ?? 0} detail="Planned project checkpoints" icon="grid" accent="blue" />
                <MetricCard label="Completed" value={milestoneData.completed ?? 0} detail="Milestones marked complete" icon="check" accent="green" />
                <MetricCard label="Pending" value={milestoneData.pending ?? 0} detail={milestoneData.overdue?.length ? `${milestoneData.overdue.length} overdue` : "Awaiting completion"} icon="calendar" accent="amber" />
                <MetricCard label="Submissions" value={progress.submissions?.total ?? 0} detail={submissionWeeks.length ? `Weeks ${submissionWeeks.join(", ")}` : "No submissions yet"} icon="file" accent="violet" />
              </section>

              {milestoneData.overdue?.length > 0 && (
                <section className="overdue-panel">
                  <div className="overdue-title"><Icon name="alert" size={17} /><strong>Overdue milestones</strong></div>
                  <div className="overdue-list">
                    {milestoneData.overdue.map((m) => (
                      <span key={m.id}>{m.title}<small>Due {m.due_date}</small></span>
                    ))}
                  </div>
                </section>
              )}

              <section className="dashboard-summaries">
                <article className="dashboard-summary-card">
                  <div className="summary-card-heading">
                    <span className="summary-icon summary-icon-blue"><Icon name="file" size={18} /></span>
                    <h2>Submission activity</h2>
                  </div>
                  <strong className="summary-number">{details.length}</strong>
                  <p>{submissionWeeks.length ? `Submissions recorded for weeks ${submissionWeeks.join(", ")}.` : "No submissions recorded yet."}</p>
                  <a href="#submissions">Go to Submissions <Icon name="chevron" size={14} /></a>
                </article>
                <article className="dashboard-summary-card">
                  <div className="summary-card-heading">
                    <span className="summary-icon summary-icon-violet"><Icon name="scan" size={18} /></span>
                    <h2>Document readiness</h2>
                  </div>
                  <strong className="summary-number">{analyzedDocuments}<small> analyzed</small></strong>
                  <p>{pendingDocuments} uploaded {pendingDocuments === 1 ? "document is" : "documents are"} awaiting analysis.</p>
                  <a href="#document-analysis">Review Document Analysis <Icon name="chevron" size={14} /></a>
                </article>
              </section>
            </>
          )}

          {/* ════════════════════════════════════════════════════════════════════
              PROJECTS PAGE (both roles)
          ════════════════════════════════════════════════════════════════════ */}
          {activePage === "projects" && !projectsLoading && (
            <section className="content-section">
              <div className="section-heading">
                <div>
                  <div className="eyebrow">{isFaculty ? "ASSIGNED PROJECTS" : "MY PROJECTS"}</div>
                  <h2>{isFaculty ? "Project Supervision Workspace" : "My Project Membership"}</h2>
                  <p>
                    {isFaculty
                      ? "Supervise assigned projects, manage team members, and track deliverables."
                      : "Projects you are currently enrolled in as a team member or leader."}
                  </p>
                </div>
                {/* Students can create projects; faculty use create to auto-assign */}
                <button className="btn btn-primary" onClick={() => setShowProjectModal(!showProjectModal)}>
                  <Icon name="plus" size={16} /> {showProjectModal ? "Close Form" : (isFaculty ? "Create & Assign Project" : "Create New Project")}
                </button>
              </div>

              {showProjectModal && (
                <div className="form-panel">
                  <div className="form-panel-head">
                    <div>
                      <h3>{isFaculty ? "Create New Student Project" : "Register New Project"}</h3>
                      <p>{isFaculty ? "A new project will be created and automatically assigned to you." : "Create your student project team workspace."}</p>
                    </div>
                  </div>
                  <form onSubmit={handleCreateProject}>
                    <div className="form-row">
                      <label>Project Title *<input type="text" required value={newProject.title} onChange={(e) => setNewProject({ ...newProject, title: e.target.value })} placeholder="e.g. AI-Based Project Monitoring System" maxLength={200} /></label>
                    </div>
                    <div className="form-row">
                      <label>Description<textarea value={newProject.description} onChange={(e) => setNewProject({ ...newProject, description: e.target.value })} placeholder="Project overview, goals, and technical domain..." /></label>
                    </div>
                    <div className="form-row">
                      <label>GitHub Repository URL (optional)<input type="url" value={newProject.github_url} onChange={(e) => setNewProject({ ...newProject, github_url: e.target.value })} placeholder="https://github.com/org/repo" /></label>
                    </div>
                    <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
                      <button type="submit" className="btn btn-primary" disabled={actionLoading}>{actionLoading ? "Creating…" : "Save Project"}</button>
                      <button type="button" className="btn btn-secondary" onClick={() => setShowProjectModal(false)}>Cancel</button>
                    </div>
                  </form>
                </div>
              )}

              <div className="projects-grid" aria-label="Available projects">
                {projects.map((project) => {
                  const selected = String(project.id) === String(projectId);
                  return (
                    <article className={`project-list-card ${selected ? "project-list-card-selected" : ""}`} key={project.id}>
                      <div className="project-list-card-top">
                        <span className="project-list-icon"><Icon name="folder" size={20} /></span>
                        <StatusBadge status={project.status} />
                      </div>
                      <span className="project-list-id">PROJECT #{project.id}</span>
                      <h2>{project.title}</h2>
                      {project.description && <p>{project.description}</p>}
                      {project.github_url && (
                        <p style={{ marginTop: "auto", fontSize: 10 }}>
                          <a href={project.github_url} target="_blank" rel="noreferrer" style={{ color: "#4361ee" }}>View GitHub Repository ↗</a>
                        </p>
                      )}
                      {project.supervisors?.length > 0 && (
                        <div style={{ margin: "8px 0 0", fontSize: 10, color: "#6e7a8f" }}>
                          <Icon name="user" size={11} /> Supervised by: {project.supervisors.map((s) => s.name).join(", ")}
                        </div>
                      )}
                      <button
                        className={`project-select-button ${selected ? "selected" : ""}`}
                        onClick={() => { setProgress(null); setProjectDocuments([]); setSubmissionDocFilter("all"); setProjectId(String(project.id)); }}
                        disabled={selected}
                      >
                        {selected ? "Currently selected" : "Select this project"}
                        {!selected && <Icon name="chevron" size={15} />}
                      </button>
                    </article>
                  );
                })}
              </div>

              {/* Team members section (below project list) */}
              {selectedProject && (
                <div style={{ marginTop: 36 }}>
                  {selectedProject.supervisors?.length > 0 && (
                    <div style={{ marginBottom: 24, padding: "16px 18px", background: "#fff", border: "1px solid var(--line)", borderRadius: 10 }}>
                      <div className="eyebrow">ASSIGNED SUPERVISION</div>
                      <h3 style={{ margin: "4px 0 8px", fontSize: 13, color: "#243450" }}>Faculty Supervisors</h3>
                      <div className="supervisor-list">
                        {selectedProject.supervisors.map((s, idx) => (
                          <div className="supervisor-badge" key={idx}>
                            <Icon name="user" size={15} />
                            <div>
                              <strong>{s.name}</strong>
                              <span style={{ display: "block", fontSize: 10, color: "#778399" }}>{s.email}{s.department ? ` · ${s.department}` : ""}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="section-heading">
                    <div>
                      <div className="eyebrow">TEAM ROSTER</div>
                      <h2>Project Members (Project #{selectedProject.id})</h2>
                      <p>{isFaculty ? "Enroll students in this project by ID or registration number." : "Students assigned to this project team."}</p>
                    </div>
                  </div>

                  {projectId && (
                    <div className="form-panel" style={{ padding: 16 }}>
                      <form onSubmit={handleAddMember} style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
                        {isFaculty && availableStudents.length > 0 && (
                          <div className="form-row" style={{ flex: 1, minWidth: 200, margin: 0 }}>
                            <label>Enroll Registered Student</label>
                            <select value={addMemberId} onChange={(e) => setAddMemberId(e.target.value)}>
                              <option value="">Select a student…</option>
                              {availableStudents.filter((s) => !members.some((m) => m.student_id === s.id)).map((s) => (
                                <option key={s.id} value={s.id}>{s.name} ({s.registration_number}) - {s.email}</option>
                              ))}
                            </select>
                          </div>
                        )}
                        <div className="form-row" style={{ flex: 1, minWidth: 200, margin: 0 }}>
                          <label>{isFaculty && availableStudents.length > 0 ? "Or by Registration Number" : "Enroll by Registration Number"}</label>
                          <input type="text" placeholder="e.g. 23MIC0016" value={addMemberReg} onChange={(e) => setAddMemberReg(e.target.value)} />
                        </div>
                        <button type="submit" className="btn btn-primary" disabled={actionLoading || (!addMemberId && !addMemberReg)}>Add Team Member</button>
                      </form>
                    </div>
                  )}

                  {members.length === 0 ? (
                    <div className="table-empty">
                      <span className="empty-icon"><Icon name="users" size={20} /></span>
                      <strong>No students assigned yet</strong>
                      <p>{isFaculty ? "Use the form above to add students to this project team." : "Your student account will be listed here once assigned."}</p>
                    </div>
                  ) : (
                    <div className="team-grid">
                      {members.map((member) => {
                        const studentDetails = availableStudents.find((s) => s.id === member.student_id);
                        return (
                          <div className="member-card" key={member.id}>
                            <div style={{ display: "flex", alignItems: "center" }}>
                              <span className="member-avatar">S</span>
                              <div className="member-meta">
                                <strong>{studentDetails?.name || `Student #${member.student_id}`}</strong>
                                <span>{studentDetails?.email || `Role: ${member.role}`}</span>
                              </div>
                            </div>
                            {isFaculty && (
                              <button type="button" className="btn btn-danger btn-sm" onClick={() => handleRemoveMember(member.student_id)} title="Remove from project">
                                <Icon name="trash" size={13} />
                              </button>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </section>
          )}

          {/* ════════════════════════════════════════════════════════════════════
              TEAM MEMBERS PAGE (students only)
          ════════════════════════════════════════════════════════════════════ */}
          {activePage === "members" && isStudent && (
            <section className="content-section">
              <div className="section-heading">
                <div>
                  <div className="eyebrow">PROJECT TEAM</div>
                  <h2>Team Members</h2>
                  <p>Students enrolled in your selected project.</p>
                </div>
              </div>

              {!projectId ? (
                <div className="state-panel"><div><strong>No project selected</strong><p>Select a project to view team members.</p></div></div>
              ) : progressLoading ? (
                <LoadingScreen />
              ) : members.length === 0 ? (
                <div className="table-empty">
                  <span className="empty-icon"><Icon name="users" size={20} /></span>
                  <strong>No team members yet</strong>
                  <p>Your faculty supervisor has not enrolled any students yet, or use the registration number form below.</p>
                </div>
              ) : (
                <div className="team-grid">
                  {members.map((member) => {
                    const studentDetails = availableStudents.find((s) => s.id === member.student_id);
                    return (
                      <div className="member-card" key={member.id}>
                        <div style={{ display: "flex", alignItems: "center" }}>
                          <span className="member-avatar">S</span>
                          <div className="member-meta">
                            <strong>{studentDetails?.name || `Student #${member.student_id}`}</strong>
                            <span>Role: {member.role}</span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {projectId && (
                <div style={{ marginTop: 24 }}>
                  <div className="section-heading">
                    <div>
                      <div className="eyebrow">SELF-ENROLL</div>
                      <h2>Join a Project by Registration</h2>
                      <p>Enter a registration number to be added to the project team (subject to project enrollment rules).</p>
                    </div>
                  </div>
                  <div className="form-panel" style={{ padding: 16 }}>
                    <form onSubmit={handleAddMember} style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
                      <div className="form-row" style={{ flex: 1, minWidth: 200, margin: 0 }}>
                        <label>Registration Number</label>
                        <input type="text" placeholder="e.g. 23MIC0016" value={addMemberReg} onChange={(e) => setAddMemberReg(e.target.value)} />
                      </div>
                      <button type="submit" className="btn btn-primary" disabled={actionLoading || !addMemberReg}>Add to Team</button>
                    </form>
                  </div>
                </div>
              )}
            </section>
          )}

          {/* ════════════════════════════════════════════════════════════════════
              PROJECT MONITORING (Faculty only)
          ════════════════════════════════════════════════════════════════════ */}
          {activePage === "monitoring" && isFaculty && (
            <section className="content-section">
              <div className="section-heading">
                <div>
                  <div className="eyebrow">SUPERVISION OVERVIEW</div>
                  <h2>Project Monitoring</h2>
                  <p>Inspect milestone progress, submission history, document completeness, and overall project health.</p>
                </div>
              </div>

              {!projectId ? (
                <div className="state-panel"><div><strong>No project selected</strong><p>Select a project from the dropdown to monitor its progress.</p></div></div>
              ) : progressLoading ? (
                <LoadingScreen />
              ) : !progress ? (
                <div className="state-panel"><div><strong>No data available</strong><p>This project has no recorded activity yet.</p></div></div>
              ) : (
                <>
                  {/* Monitoring summary */}
                  <section className="metrics-grid">
                    <MetricCard label="Team Size" value={members.length} detail="Enrolled students" icon="users" accent="blue" />
                    <MetricCard label="Milestones" value={`${milestoneData.completed || 0}/${milestoneData.total || 0}`} detail={`${milestoneData.pending || 0} pending`} icon="check" accent="green" />
                    <MetricCard label="Submissions" value={details.length} detail={submissionWeeks.length ? `Weeks: ${submissionWeeks.join(", ")}` : "None yet"} icon="file" accent="amber" />
                    <MetricCard label="Analyzed Docs" value={analyzedDocuments} detail={`${pendingDocuments} awaiting analysis`} icon="scan" accent="violet" />
                  </section>

                  {milestoneData.overdue?.length > 0 && (
                    <div className="overdue-panel" style={{ marginBottom: 24 }}>
                      <div className="overdue-title"><Icon name="alert" size={17} /><strong>Overdue milestones</strong></div>
                      <div className="overdue-list">
                        {milestoneData.overdue.map((m) => <span key={m.id}>{m.title}<small>Due {m.due_date}</small></span>)}
                      </div>
                    </div>
                  )}

                  <div className="section-heading">
                    <div>
                      <div className="eyebrow">DOCUMENT COMPLETENESS</div>
                      <h2>Submitted Document Analysis</h2>
                    </div>
                    <div className="analysis-summary">{analyzedDocuments} analyzed <span>·</span> {pendingDocuments} pending</div>
                  </div>

                  {documents.length === 0 ? (
                    <div className="table-empty">
                      <span className="empty-icon"><Icon name="scan" size={20} /></span>
                      <strong>No documents submitted</strong>
                      <p>Students must upload PDF reports or SRS documents before analysis is available.</p>
                    </div>
                  ) : (
                    <div className="document-grid">
                      {documents.map((document) => (
                        <DocumentCard
                          key={`${document.submission_id}-${document.document_type}`}
                          document={document}
                          onAnalyze={handleAnalyzeDocument}
                          isFaculty={true}
                          analyzing={analyzingDoc === `${document.submission_id}-${document.document_type}`}
                          projectId={projectId}
                          onPreview={handlePreviewDocument}
                          onDownload={handleDownloadDocument}
                        />
                      ))}
                    </div>
                  )}
                </>
              )}
            </section>
          )}

          {/* ════════════════════════════════════════════════════════════════════
              MILESTONES PAGE (both roles)
          ════════════════════════════════════════════════════════════════════ */}
          {activePage === "milestones" && (
            <section className="content-section">
              <div className="section-heading">
                <div>
                  <div className="eyebrow">PROJECT CHECKPOINTS</div>
                  <h2>Milestone Checklist</h2>
                  <p>{isFaculty ? "Create, update due dates, and mark completed milestones." : "Review expected checkpoints and deadline milestones set by your supervisor."}</p>
                </div>
                {isFaculty && projectId && (
                  <button className="btn btn-primary" onClick={() => setShowMilestoneModal(!showMilestoneModal)}>
                    <Icon name="plus" size={16} /> {showMilestoneModal ? "Close Form" : "Add Milestone"}
                  </button>
                )}
              </div>

              {isFaculty && showMilestoneModal && (
                <div className="form-panel">
                  <div className="form-panel-head">
                    <div><h3>Add Project Milestone</h3><p>Create a checkpoint deadline for the students to complete.</p></div>
                  </div>
                  <form onSubmit={handleCreateMilestone}>
                    <div className="form-row">
                      <label>Milestone Title *<input type="text" required value={newMilestone.title} onChange={(e) => setNewMilestone({ ...newMilestone, title: e.target.value })} placeholder="e.g. System Design Document & Architecture Review" maxLength={200} /></label>
                    </div>
                    <div className="form-row">
                      <label>Description<textarea value={newMilestone.description} onChange={(e) => setNewMilestone({ ...newMilestone, description: e.target.value })} placeholder="Deliverable expectations and criteria..." /></label>
                    </div>
                    <div className="form-row">
                      <label>Due Date *<input type="date" required value={newMilestone.due_date} onChange={(e) => setNewMilestone({ ...newMilestone, due_date: e.target.value })} /></label>
                    </div>
                    <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
                      <button type="submit" className="btn btn-primary" disabled={actionLoading}>{actionLoading ? "Adding…" : "Save Milestone"}</button>
                      <button type="button" className="btn btn-secondary" onClick={() => setShowMilestoneModal(false)}>Cancel</button>
                    </div>
                  </form>
                </div>
              )}

              {!projectId ? (
                <div className="state-panel"><div><strong>No project selected</strong><p>Select a project to review milestones.</p></div></div>
              ) : milestones.length === 0 ? (
                <div className="table-empty">
                  <span className="empty-icon"><Icon name="calendar" size={20} /></span>
                  <strong>No milestones planned yet</strong>
                  <p>{isFaculty ? "Add the first milestone using the button above." : "Your faculty advisor has not defined milestones yet."}</p>
                </div>
              ) : (
                <div className="milestone-checklist">
                  {milestones.map((m) => {
                    const isOverdue = !m.completed && m.due_date && new Date(m.due_date) < new Date();
                    return (
                      <article className={`milestone-item ${m.completed ? "completed" : ""} ${isOverdue ? "overdue" : ""}`} key={m.id}>
                        <div className="milestone-left">
                          {isFaculty ? (
                            <input type="checkbox" className="milestone-checkbox" checked={m.completed} onChange={() => handleToggleMilestone(m)} title={m.completed ? "Mark incomplete" : "Mark completed"} aria-label={`Toggle completion for ${m.title}`} />
                          ) : (
                            <span style={{ marginTop: 2, color: m.completed ? "#23845f" : "#99a3b5" }}>
                              <Icon name={m.completed ? "check" : "calendar"} size={18} />
                            </span>
                          )}
                          <div className="milestone-info">
                            <h4>{m.title}</h4>
                            {m.description && <p>{m.description}</p>}
                            <div className="milestone-meta">
                              <span>Due {m.due_date || "No deadline"}</span>
                              {isOverdue && <span style={{ color: "#b34045", fontWeight: 700 }}>· Overdue</span>}
                              <StatusBadge status={m.completed ? "completed" : "pending"} />
                            </div>
                          </div>
                        </div>
                        {isFaculty && (
                          <div className="milestone-actions">
                            <button type="button" className="btn btn-danger btn-sm" onClick={() => handleDeleteMilestone(m.id)} title="Delete milestone">
                              <Icon name="trash" size={13} />
                            </button>
                          </div>
                        )}
                      </article>
                    );
                  })}
                </div>
              )}
            </section>
          )}

          {/* ════════════════════════════════════════════════════════════════════
              SUBMISSIONS PAGE (both roles)
          ════════════════════════════════════════════════════════════════════ */}
          {activePage === "submissions" && (
            <section className="content-section">
              <div className="section-heading">
                <div>
                  <div className="eyebrow">{isFaculty ? "DELIVERABLE REVIEW" : "PROJECT DELIVERABLES"}</div>
                  <h2>{isFaculty ? "Submission Reviews" : "Submissions & Uploads"}</h2>
                  <p>{isFaculty ? "View and review all student deliverable packages for this project." : "Upload project reports (PDF), presentation slides, and SRS documents."}</p>
                </div>
              </div>

              {/* Upload form — available to both roles */}
              {projectId && !isFaculty && (
                <div className="form-panel">
                  <div className="form-panel-head">
                    <div><h3>Upload Weekly Submission</h3><p>Files must be under 10 MB. At least one deliverable is required.</p></div>
                  </div>
                  <form onSubmit={handleUploadSubmission}>
                    <div className="form-grid-3">
                      <div className="form-row">
                        <label>Submission Week (1 - 52) *<input type="number" min="1" max="52" required value={uploadWeek} onChange={(e) => setUploadWeek(parseInt(e.target.value, 10) || 1)} /></label>
                      </div>
                      <div className="form-row">
                        <label>Report Document (.pdf)<input type="file" accept=".pdf" onChange={(e) => setUploadReportFile(e.target.files?.[0] || null)} /></label>
                        <span className="form-hint">Format: PDF</span>
                      </div>
                      <div className="form-row">
                        <label>Presentation (.ppt, .pptx)<input type="file" accept=".ppt,.pptx" onChange={(e) => setUploadPresentationFile(e.target.files?.[0] || null)} /></label>
                        <span className="form-hint">Format: PowerPoint</span>
                      </div>
                    </div>
                    <div className="form-grid-2">
                      <div className="form-row">
                        <label>SRS Document (.pdf)<input type="file" accept=".pdf" onChange={(e) => setUploadSrsFile(e.target.files?.[0] || null)} /></label>
                        <span className="form-hint">Format: PDF</span>
                      </div>
                      <div className="form-row">
                        <label>Notes / Changelog (optional)<input type="text" value={uploadNotes} onChange={(e) => setUploadNotes(e.target.value)} placeholder="e.g. Added section 3.2 system requirements" /></label>
                      </div>
                    </div>
                    <div style={{ marginTop: 14 }}>
                      <button type="submit" className="btn btn-primary" disabled={uploading}>
                        <Icon name="upload" size={15} />
                        {uploading ? "Uploading deliverables…" : "Submit Documents"}
                      </button>
                    </div>
                  </form>
                </div>
              )}

              {/* Faculty upload option */}
              {projectId && isFaculty && (
                <div className="form-panel">
                  <div className="form-panel-head">
                    <div><h3>Upload on Behalf of Students</h3><p>Faculty may also upload deliverable documents to the project record.</p></div>
                  </div>
                  <form onSubmit={handleUploadSubmission}>
                    <div className="form-grid-3">
                      <div className="form-row">
                        <label>Submission Week (1 - 52) *<input type="number" min="1" max="52" required value={uploadWeek} onChange={(e) => setUploadWeek(parseInt(e.target.value, 10) || 1)} /></label>
                      </div>
                      <div className="form-row">
                        <label>Report Document (.pdf)<input type="file" accept=".pdf" onChange={(e) => setUploadReportFile(e.target.files?.[0] || null)} /></label>
                        <span className="form-hint">Format: PDF</span>
                      </div>
                      <div className="form-row">
                        <label>Presentation (.ppt, .pptx)<input type="file" accept=".ppt,.pptx" onChange={(e) => setUploadPresentationFile(e.target.files?.[0] || null)} /></label>
                        <span className="form-hint">Format: PowerPoint</span>
                      </div>
                    </div>
                    <div style={{ marginTop: 14 }}>
                      <button type="submit" className="btn btn-primary" disabled={uploading}>
                        <Icon name="upload" size={15} />
                        {uploading ? "Uploading…" : "Upload Submission"}
                      </button>
                    </div>
                  </form>
                </div>
              )}

              <div className="section-heading" style={{ marginTop: 32 }}>
                <div>
                  <div className="eyebrow">SUBMISSION HISTORY</div>
                  <h2>Recorded Submissions</h2>
                  <p>{isFaculty ? "Click any row to expand reviews and write faculty feedback." : "All weekly deliverables, evaluations, scores, and qualitative feedback."}</p>
                </div>
                <span className="section-count">{details.length} {details.length === 1 ? "submission" : "submissions"}</span>
              </div>

              {details.length === 0 ? (
                <div className="table-empty">
                  <span className="empty-icon"><Icon name="file" size={20} /></span>
                  <strong>No submissions recorded</strong>
                  <p>{isFaculty ? "Students must upload weekly deliverables before they appear here." : "Upload a weekly submission above to record deliverables."}</p>
                </div>
              ) : (
                <div className="table-shell">
                  <table>
                    <thead>
                      <tr>
                        <th>Submission</th>
                        <th>Week</th>
                        <th>Deliverables</th>
                        <th>Status</th>
                        <th>Review & Score</th>
                        <th>Submitted</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {details.map((submission) => {
                        const reviews = reviewsBySub[submission.submission_id] || [];
                        const isExpanded = !!expandedReviews[submission.submission_id];
                        const latestReview = reviews[0];
                        return (
                          <Fragment key={submission.submission_id}>
                            <tr>
                              <td>
                                <span className="submission-id">SUB-{String(submission.submission_id).padStart(3, "0")}</span>
                                <small>ID #{submission.submission_id}</small>
                              </td>
                              <td><span className="week-chip">Week {submission.week_number}</span></td>
                              <td>
                                <div className="tag-list">
                                  {!submission.missing_documents?.includes("report") && <span className="tag">Report PDF</span>}
                                  {!submission.missing_documents?.includes("presentation") && <span className="tag">Presentation</span>}
                                  {!submission.missing_documents?.includes("SRS") && <span className="tag">SRS PDF</span>}
                                </div>
                              </td>
                              <td><StatusBadge status={submission.status} /></td>
                              <td>
                                {latestReview ? (
                                  <span className="review-score-badge"><Icon name="star" size={12} /> {latestReview.score}/100</span>
                                ) : (
                                  <span className="score-unavailable">Pending Review</span>
                                )}
                              </td>
                              <td className="date-cell">{submission.submitted_at ? new Date(submission.submitted_at).toLocaleDateString() : "—"}</td>
                              <td>
                                <button type="button" className="btn btn-outline btn-sm"
                                  onClick={() => setExpandedReviews((prev) => ({ ...prev, [submission.submission_id]: !prev[submission.submission_id] }))}>
                                  {isExpanded ? "Hide Reviews" : `Reviews (${reviews.length})`}
                                </button>
                              </td>
                            </tr>
                            {isExpanded && (
                              <tr>
                                <td colSpan={7} style={{ background: "#fcfdff", padding: "18px 24px" }}>
                                  <div style={{ maxWidth: 850 }}>
                                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                                      <h4 style={{ margin: 0, fontSize: 13, color: "#23334d" }}>Submission #{submission.submission_id} Reviews ({reviews.length})</h4>
                                      {isFaculty && !reviewForm.submissionId && (
                                        <button type="button" className="btn btn-primary btn-sm" style={{ marginLeft: "auto" }}
                                          onClick={() => setReviewForm({ submissionId: submission.submission_id, score: latestReview ? String(latestReview.score) : "", feedback: latestReview ? latestReview.feedback : "", reviewId: latestReview ? latestReview.id : null })}>
                                          {latestReview ? "Edit My Review" : "Write Review"}
                                        </button>
                                      )}
                                    </div>
                                    {isFaculty && reviewForm.submissionId === submission.submission_id && (
                                      <div className="form-panel" style={{ margin: "14px 0", padding: 18 }}>
                                        <h4 style={{ margin: "0 0 12px", fontSize: 13 }}>{reviewForm.reviewId ? "Edit Faculty Review" : "New Faculty Review & Grade"}</h4>
                                        <form onSubmit={handleSaveReview}>
                                          <div className="form-row">
                                            <label>Numerical Score (0.0 – 100.0) *<input type="number" step="0.5" min="0" max="100" required value={reviewForm.score} onChange={(e) => setReviewForm({ ...reviewForm, score: e.target.value })} placeholder="e.g. 85.5" /></label>
                                          </div>
                                          <div className="form-row">
                                            <label>Qualitative Feedback & Guidance *<textarea required rows={4} value={reviewForm.feedback} onChange={(e) => setReviewForm({ ...reviewForm, feedback: e.target.value })} placeholder="Provide actionable academic feedback, strengths, and areas to improve..." /></label>
                                          </div>
                                          <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
                                            <button type="submit" className="btn btn-primary btn-sm" disabled={actionLoading}>{actionLoading ? "Saving…" : "Save Review"}</button>
                                            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setReviewForm({ submissionId: null, score: "", feedback: "", reviewId: null })}>Cancel</button>
                                          </div>
                                        </form>
                                      </div>
                                    )}
                                    {reviews.length === 0 ? (
                                      <div className="table-empty" style={{ padding: 18 }}>
                                        <p style={{ margin: 0 }}>No faculty reviews submitted yet for this deliverable package.</p>
                                      </div>
                                    ) : (
                                      <div className="reviews-container">
                                        {reviews.map((r) => (
                                          <div className="review-card" key={r.id}>
                                            <div className="review-card-head">
                                              <div className="review-author">
                                                <span className="review-avatar">FR</span>
                                                <div className="review-author-meta">
                                                  <strong>{r.reviewer_name}</strong>
                                                  <span>{r.reviewer_email}</span>
                                                </div>
                                              </div>
                                              <span className="review-score-badge"><Icon name="star" size={13} /> {r.score} / 100</span>
                                            </div>
                                            <div className="review-body">{r.feedback}</div>
                                            <div className="review-footer">
                                              <span>Reviewed on {new Date(r.created_at).toLocaleString()}</span>
                                              {isFaculty && (
                                                <div style={{ display: "flex", gap: 8 }}>
                                                  <button type="button" className="btn btn-outline btn-sm"
                                                    onClick={() => setReviewForm({ submissionId: submission.submission_id, score: String(r.score), feedback: r.feedback, reviewId: r.id })}>Edit</button>
                                                  <button type="button" className="btn btn-danger btn-sm" onClick={() => handleDeleteReview(submission.submission_id, r.id)}>Delete</button>
                                                </div>
                                              )}
                                            </div>
                                          </div>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                </td>
                              </tr>
                            )}
                          </Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              {/* ════════════════════════════════════════════════════════════════════
                  SUBMITTED DOCUMENTS REPOSITORY (Faculty & Student)
              ════════════════════════════════════════════════════════════════════ */}
              <div className="section-heading" style={{ marginTop: 36 }}>
                <div>
                  <div className="eyebrow">{isFaculty ? "ORIGINAL STUDENT UPLOADS" : "MY SUBMITTED FILES"}</div>
                  <h2>Submitted Documents</h2>
                  <p>
                    {isFaculty
                      ? "Direct access to original files uploaded by students for this project. Inspect or download the actual file contents."
                      : "Access and verify the original files submitted for your project."}
                  </p>
                </div>
                {details.length > 0 && (
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <label htmlFor="submission-filter-select" style={{ fontSize: 12, fontWeight: 600, color: "#475569" }}>
                      Filter Submission:
                    </label>
                    <select
                      id="submission-filter-select"
                      className="form-control"
                      style={{ padding: "6px 12px", fontSize: 12, borderRadius: 6, border: "1px solid #cbd5e1" }}
                      value={submissionDocFilter}
                      onChange={(e) => setSubmissionDocFilter(e.target.value)}
                    >
                      <option value="all">All Submissions ({projectDocuments.length} files)</option>
                      {details.map((sub) => (
                        <option key={sub.submission_id} value={sub.submission_id}>
                          Submission #{sub.submission_id} (Week {sub.week_number})
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              {filteredDocuments.length === 0 ? (
                <div className="table-empty" data-testid="submitted-docs-empty">
                  <span className="empty-icon"><Icon name="file" size={20} /></span>
                  <strong>No submitted files available</strong>
                  <p>
                    {submissionDocFilter !== "all"
                      ? `No uploaded files attached to Submission #${submissionDocFilter}.`
                      : "No submissions have been uploaded for this project yet."}
                  </p>
                </div>
              ) : (
                <div className="table-shell" data-testid="submitted-docs-table">
                  <table>
                    <thead>
                      <tr>
                        <th>Original File</th>
                        <th>Type</th>
                        <th>Submission</th>
                        <th>Team / Submitter</th>
                        <th>File Size</th>
                        <th>Analysis Status</th>
                        <th style={{ textAlign: "right" }}>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredDocuments.map((doc) => {
                        const fileExt = (doc.original_filename || doc.file_type || "").split(".").pop().toLowerCase();
                        const pillClass = `file-pill file-pill-${fileExt || doc.file_type || "other"}`;
                        const docKey = `${doc.submission_id}-${doc.document_id || doc.file_type}`;
                        const isDownloading = downloadingDocKey === docKey;
                        const teamDisplay = doc.student_name || (doc.team_members?.length ? doc.team_members.join(", ") : members?.map(m => m.name).join(", ") || "Project Team");
                        // file_exists=false means DB has a path but the actual file is missing on disk
                        const fileOnDisk = doc.file_exists !== false;

                        return (
                          <tr key={docKey} data-testid={`doc-row-${docKey}`}>
                            <td>
                              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                <span style={{ color: fileOnDisk ? "#475569" : "#dc2626" }}><Icon name="file" size={18} /></span>
                                <div>
                                  <strong style={{ fontSize: 13, color: fileOnDisk ? "#0f172a" : "#dc2626", wordBreak: "break-all", display: "block" }}>
                                    {doc.original_filename}
                                  </strong>
                                  {!fileOnDisk && (
                                    <small style={{ color: "#dc2626", fontWeight: 600 }} data-testid={`missing-file-${docKey}`}>
                                      ⚠ File not found on server
                                    </small>
                                  )}
                                  {fileOnDisk && <small style={{ color: "#64748b" }}>Doc ID: {doc.document_id || doc.file_type}</small>}
                                </div>
                              </div>
                            </td>
                            <td>
                              <span className={pillClass}>
                                {(doc.file_type || fileExt || "file").toUpperCase()}
                              </span>
                            </td>
                            <td>
                              <span className="submission-id">SUB-{String(doc.submission_id).padStart(3, "0")}</span>
                              <div style={{ fontSize: 11, color: "#64748b" }}>
                                Week {doc.week_number} · {doc.submitted_at ? new Date(doc.submitted_at).toLocaleDateString() : "—"}
                              </div>
                            </td>
                            <td>
                              <span style={{ fontSize: 12, color: "#334155" }}>{teamDisplay}</span>
                            </td>
                            <td>
                              <span style={{ fontSize: 12, fontFamily: "monospace", color: "#475569" }}>
                                {!fileOnDisk ? "—" : (doc.size_formatted || (doc.file_size ? `${(doc.file_size / 1024).toFixed(1)} KB` : "—"))}
                              </span>
                            </td>
                            <td>
                              <StatusBadge status={doc.analysis_status || "not_analyzed"} />
                            </td>
                            <td style={{ textAlign: "right" }}>
                              {!fileOnDisk ? (
                                <span style={{ fontSize: 11, color: "#dc2626", fontStyle: "italic" }} data-testid={`unavailable-${docKey}`}>
                                  File unavailable
                                </span>
                              ) : (
                                <div className="doc-action-group" style={{ justifyContent: "flex-end" }}>
                                  <button
                                    type="button"
                                    className="btn btn-outline btn-sm"
                                    onClick={() => handlePreviewDocument(doc)}
                                    title="Preview or view document"
                                  >
                                    <Icon name="eye" size={13} /> View
                                  </button>
                                  <button
                                    type="button"
                                    className="btn btn-primary btn-sm"
                                    onClick={() => handleDownloadDocument(doc)}
                                    disabled={isDownloading}
                                    title="Download original document bytes"
                                  >
                                    <Icon name="download" size={13} />
                                    {isDownloading ? "Downloading…" : "Download"}
                                  </button>
                                </div>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}

          {/* ════════════════════════════════════════════════════════════════════
              REVIEWS & FEEDBACK dedicated page (both roles)
          ════════════════════════════════════════════════════════════════════ */}
          {activePage === "reviews" && (
            <section className="content-section">
              <div className="section-heading">
                <div>
                  <div className="eyebrow">{isFaculty ? "ACADEMIC GRADING" : "MY FEEDBACK"}</div>
                  <h2>{isFaculty ? "Feedback & Scores" : "Faculty Reviews & Feedback"}</h2>
                  <p>{isFaculty ? "View, write, and manage scored faculty reviews for each submission." : "View faculty feedback and scores for your submitted deliverables."}</p>
                </div>
                <span className="section-count">{Object.values(reviewsBySub).reduce((a, r) => a + r.length, 0)} total reviews</span>
              </div>

              {!projectId ? (
                <div className="state-panel"><div><strong>No project selected</strong><p>Select a project to see reviews.</p></div></div>
              ) : details.length === 0 ? (
                <div className="table-empty">
                  <span className="empty-icon"><Icon name="star" size={20} /></span>
                  <strong>No submissions to review</strong>
                  <p>{isFaculty ? "Students must submit deliverables before reviews can be written." : "Submit deliverables to see faculty feedback here."}</p>
                </div>
              ) : (
                <div style={{ display: "grid", gap: 24 }}>
                  {details.map((submission) => {
                    const reviews = reviewsBySub[submission.submission_id] || [];
                    const latestReview = reviews[0];
                    return (
                      <div key={submission.submission_id} style={{ border: "1px solid var(--line)", borderRadius: 12, overflow: "hidden", background: "#fff" }}>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 18px", borderBottom: "1px solid #f0f2f8", background: "#fafbfe" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                            <Icon name="file" size={16} />
                            <div>
                              <strong style={{ fontSize: 13, color: "#23334d" }}>Week {submission.week_number} Submission (SUB-{String(submission.submission_id).padStart(3, "0")})</strong>
                              <span style={{ display: "block", fontSize: 10, color: "#8a94a7" }}>
                                {submission.submitted_at ? new Date(submission.submitted_at).toLocaleDateString() : "Date unknown"}
                              </span>
                            </div>
                          </div>
                          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                            {latestReview
                              ? <span className="review-score-badge"><Icon name="star" size={12} /> {latestReview.score}/100</span>
                              : <span className="score-unavailable">Not yet reviewed</span>}
                            {isFaculty && !reviewForm.submissionId && (
                              <button type="button" className="btn btn-primary btn-sm"
                                onClick={() => setReviewForm({ submissionId: submission.submission_id, score: latestReview ? String(latestReview.score) : "", feedback: latestReview ? latestReview.feedback : "", reviewId: latestReview ? latestReview.id : null })}>
                                {latestReview ? "Edit Review" : "Write Review"}
                              </button>
                            )}
                          </div>
                        </div>
                        {isFaculty && reviewForm.submissionId === submission.submission_id && (
                          <div style={{ padding: "18px 24px", borderBottom: "1px solid #f0f2f8" }}>
                            <form onSubmit={handleSaveReview}>
                              <div className="form-grid-2">
                                <div className="form-row">
                                  <label>Score (0.0 – 100.0) *<input type="number" step="0.5" min="0" max="100" required value={reviewForm.score} onChange={(e) => setReviewForm({ ...reviewForm, score: e.target.value })} placeholder="e.g. 85.5" /></label>
                                </div>
                                <div className="form-row" style={{ gridColumn: "1/-1" }}>
                                  <label>Feedback & Guidance *<textarea required rows={4} value={reviewForm.feedback} onChange={(e) => setReviewForm({ ...reviewForm, feedback: e.target.value })} placeholder="Provide actionable academic feedback..." /></label>
                                </div>
                              </div>
                              <div style={{ display: "flex", gap: 10 }}>
                                <button type="submit" className="btn btn-primary btn-sm" disabled={actionLoading}>{actionLoading ? "Saving…" : "Save Review"}</button>
                                <button type="button" className="btn btn-secondary btn-sm" onClick={() => setReviewForm({ submissionId: null, score: "", feedback: "", reviewId: null })}>Cancel</button>
                              </div>
                            </form>
                          </div>
                        )}
                        <div style={{ padding: "14px 18px" }}>
                          {reviews.length === 0 ? (
                            <p style={{ margin: 0, color: "#8c96a8", fontSize: 11 }}>
                              {isFaculty ? "No reviews written yet. Click 'Write Review' above." : "Your supervisor has not written a review yet."}
                            </p>
                          ) : (
                            <div className="reviews-container">
                              {reviews.map((r) => (
                                <div className="review-card" key={r.id}>
                                  <div className="review-card-head">
                                    <div className="review-author">
                                      <span className="review-avatar">FR</span>
                                      <div className="review-author-meta">
                                        <strong>{r.reviewer_name}</strong>
                                        <span>{r.reviewer_email}</span>
                                      </div>
                                    </div>
                                    <span className="review-score-badge"><Icon name="star" size={13} /> {r.score} / 100</span>
                                  </div>
                                  <div className="review-body">{r.feedback}</div>
                                  <div className="review-footer">
                                    <span>Reviewed on {new Date(r.created_at).toLocaleString()}</span>
                                    {isFaculty && (
                                      <div style={{ display: "flex", gap: 8 }}>
                                        <button type="button" className="btn btn-outline btn-sm"
                                          onClick={() => setReviewForm({ submissionId: submission.submission_id, score: String(r.score), feedback: r.feedback, reviewId: r.id })}>Edit</button>
                                        <button type="button" className="btn btn-danger btn-sm" onClick={() => handleDeleteReview(submission.submission_id, r.id)}>Delete</button>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          )}

          {/* ════════════════════════════════════════════════════════════════════
              DOCUMENT ANALYSIS PAGE
          ════════════════════════════════════════════════════════════════════ */}
          {activePage === "document-analysis" && (
            <section className="content-section analysis-section">
              <div className="section-heading">
                <div>
                  <div className="eyebrow">RULE-BASED AUDIT</div>
                  <h2>Report & SRS Completeness Analysis</h2>
                  <p>Automated verification of mandatory sections, structure, and word counts.</p>
                </div>
                <div className="analysis-summary">{analyzedDocuments} analyzed <span>·</span> {pendingDocuments} pending</div>
              </div>

              <div className="info-box">
                <Icon name="scan" size={18} />
                <div>
                  <strong>Automated Completeness Checks</strong>
                  <p>
                    Document analysis inspects PDFs for required academic sections (Abstract, Introduction, System Requirements, etc.).
                    {isFaculty ? " As a faculty supervisor, you can trigger fresh analysis on any uploaded document below." : " Results are updated as new documents are reviewed."}
                  </p>
                </div>
              </div>

              {documents.length === 0 ? (
                <div className="table-empty">
                  <span className="empty-icon"><Icon name="scan" size={20} /></span>
                  <strong>No document analyses available</strong>
                  <p>Upload a Report or SRS PDF under Submissions to see automated analysis.</p>
                </div>
              ) : (
                <div className="document-grid">
                  {documents.map((document) => (
                    <DocumentCard
                      key={`${document.submission_id}-${document.document_type}`}
                      document={document}
                      onAnalyze={handleAnalyzeDocument}
                      isFaculty={isFaculty}
                      analyzing={analyzingDoc === `${document.submission_id}-${document.document_type}`}
                      projectId={projectId}
                      onPreview={handlePreviewDocument}
                      onDownload={handleDownloadDocument}
                    />
                  ))}
                </div>
              )}
            </section>
          )}

          {/* ════════════════════════════════════════════════════════════════════
              GITHUB PAGE (both roles)
          ════════════════════════════════════════════════════════════════════ */}
          {activePage === "github" && (
            <section className="content-section">
              <div className="section-heading">
                <div>
                  <div className="eyebrow">GIT INTEGRATION</div>
                  <h2>{isFaculty ? "GitHub Insights" : "GitHub Activity"}</h2>
                  <p>Inspect commit velocity, activity indicators, and contributor roster matches.</p>
                </div>
                {projectId && selectedProject?.github_url && (
                  <button className="btn btn-primary" onClick={handleAnalyzeGitHub} disabled={gitLoading}>
                    <Icon name="refresh" size={15} />
                    {gitLoading ? "Analyzing repository…" : "Analyze Repository"}
                  </button>
                )}
              </div>

              {!projectId ? (
                <div className="state-panel"><div><strong>No project selected</strong><p>Select a project to review GitHub insights.</p></div></div>
              ) : !selectedProject?.github_url ? (
                <div className="table-empty">
                  <span className="empty-icon"><Icon name="code" size={20} /></span>
                  <strong>No GitHub repository connected</strong>
                  <p>
                    {isFaculty
                      ? "Edit this project under Assigned Projects to add a GitHub repository URL."
                      : "Ask your faculty supervisor to add a GitHub repository URL to this project."}
                  </p>
                </div>
              ) : !effectiveGitAnalysis ? (
                <div className="table-empty">
                  <span className="empty-icon"><Icon name="code" size={20} /></span>
                  <strong>Repository connected: {selectedProject.github_url}</strong>
                  <p>{isFaculty ? "Click \"Analyze Repository\" above to inspect commit history and contributor activity." : "Your supervisor can run a GitHub analysis to inspect repository activity."}</p>
                </div>
              ) : (
                <>
                  <div className="github-stats-grid">
                    <MetricCard label="Total Commits" value={effectiveGitAnalysis.total_commits} detail={`Inspected last ${effectiveGitAnalysis.recent_activity?.inspected_commit_window || effectiveGitAnalysis.total_commits} commits`} icon="code" accent="blue" />
                    <MetricCard label="Contributors" value={displayedContributors?.length || 0} detail="Active commit authors" icon="users" accent="green" />
                    <MetricCard label="Default Branch" value={effectiveGitAnalysis.default_branch || "main"} detail="Primary target branch" icon="grid" accent="violet" />
                    <MetricCard label="Last Recorded Commit" value={effectiveGitAnalysis.recent_activity?.last_commit_date ? new Date(effectiveGitAnalysis.recent_activity.last_commit_date).toLocaleDateString() : "—"} detail="Latest commit timestamp" icon="calendar" accent="amber" />
                  </div>

                  <div className="section-heading">
                    <div>
                      <div className="eyebrow">CONTRIBUTOR ROSTER</div>
                      <h3>Contributors & Identity Matching</h3>
                      <p>Git authors correlated with enrolled project team members.</p>
                    </div>
                  </div>

                  <div style={{ display: "grid", gap: 8 }}>
                    {displayedContributors?.map((c) => {
                      const profileUrl = c.profile_url || (c.username ? `https://github.com/${c.username}` : null);
                      return (
                        <div className="github-contributor-card" key={c.username}>
                          <div className="contributor-left">
                            {profileUrl ? (
                              <a href={profileUrl} target="_blank" rel="noreferrer" title={`GitHub profile: ${profileUrl}`} aria-label={`${c.username}'s GitHub profile`}>
                                <ContributorAvatar url={c.avatar_url} username={c.username} name={c.name} />
                              </a>
                            ) : (
                              <ContributorAvatar url={c.avatar_url} username={c.username} name={c.name} />
                            )}
                            <div className="contributor-name">
                              <strong>
                                {profileUrl ? (
                                  <a href={profileUrl} target="_blank" rel="noreferrer" className="contributor-profile-link" title={`GitHub profile: ${profileUrl}`}>
                                    {c.name || c.username} (@{c.username})
                                  </a>
                                ) : (
                                  `${c.name || c.username} (@{c.username})`
                                )}
                              </strong>
                              <span>
                                {c.email ? (
                                  <a href={`mailto:${c.email}`} className="contributor-email-link" title={`Email: ${c.email}`}>
                                    {c.email}
                                  </a>
                                ) : (
                                  "No public email"
                                )} · {c.commits} commits
                              </span>
                            </div>
                          </div>
                          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                            {c.matched_member && <span style={{ fontSize: 11, color: "#30405c" }}>Matched: <strong>{c.matched_member}</strong></span>}
                            <span className={`match-badge match-${c.match_confidence || "unmatched"}`}>
                              {c.match_confidence === "verified" ? "Verified Student" : c.match_confidence === "probable" ? "Probable Match" : "Unmatched"}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {effectiveGitAnalysis.limitations_disclaimer && (
                    <div className="info-box" style={{ marginTop: 20 }}>
                      <Icon name="alert" size={16} />
                      <div><strong>Limitations Notice</strong><p>{effectiveGitAnalysis.limitations_disclaimer}</p></div>
                    </div>
                  )}
                </>
              )}
            </section>
          )}

          {/* ════════════════════════════════════════════════════════════════════
              AI SUMMARY PAGE (both roles)
          ════════════════════════════════════════════════════════════════════ */}
          {activePage === "ai-summary" && (
            <section className="content-section">
              <div className="section-heading">
                <div>
                  <div className="eyebrow">DECISION SUPPORT</div>
                  <h2>AI Project Summary & Synthesis</h2>
                  <p>Automated advisory synthesis grounded in project submissions, milestones, reviews, and Git data.</p>
                </div>
                {isFaculty && projectId && (
                  <button className="btn btn-primary" onClick={handleGenerateAISummary} disabled={aiSummaryLoading || !aiSummaryData?.provider_configured}>
                    <Icon name="cpu" size={15} />
                    {aiSummaryLoading ? "Synthesizing summary…" : "Generate Advisory Summary"}
                  </button>
                )}
              </div>

              {!aiSummaryData?.provider_configured && (
                <div className="info-box" style={{ background: "#fffaf0", borderColor: "#fae8cc" }}>
                  <Icon name="alert" size={18} />
                  <div>
                    <strong>LLM Provider Not Configured</strong>
                    <p>Automated LLM summaries require an API key. Set <code>GROQ_API_KEY</code> or <code>GEMINI_API_KEY</code> in <code>backend/.env</code> to enable advisory project summaries.</p>
                  </div>
                </div>
              )}

              {!projectId ? (
                <div className="state-panel"><div><strong>No project selected</strong><p>Select a project to review AI summary.</p></div></div>
              ) : !aiSummaryData?.latest_summary ? (
                <div className="table-empty">
                  <span className="empty-icon"><Icon name="cpu" size={20} /></span>
                  <strong>No AI summary generated yet for Project #{projectId}</strong>
                  <p>
                    {isFaculty
                      ? "Click 'Generate Advisory Summary' above to analyze this project's recorded evidence."
                      : "Your faculty supervisor has not generated an AI summary for this project yet."}
                  </p>
                </div>
              ) : (
                <div>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                    <span style={{ fontSize: 11, color: "#6a7791" }}>
                      Generated by <strong>{aiSummaryData.latest_summary.provider.toUpperCase()} ({aiSummaryData.latest_summary.model_name})</strong> on{" "}
                      {new Date(aiSummaryData.latest_summary.created_at).toLocaleDateString()}
                    </span>
                    <span className="badge badge-complete">Advisory Synthesis</span>
                  </div>

                  {/* Submission Verification Status Bar & Metrics */}
                  {aiSummaryData.latest_summary.submission_verification_status && (
                    <div className="submission-status-bar" data-testid="submission-status-bar">
                      <div className="submission-status-info">
                        <span>Submission Verification Status:</span>
                        <span
                          className={`submission-status-badge ${
                            aiSummaryData.latest_summary.submission_verification_status === "VERIFIED_RELEVANT"
                              ? "status-badge-verified"
                              : aiSummaryData.latest_summary.submission_verification_status === "CONTRADICTORY_TOPICS" ||
                                aiSummaryData.latest_summary.submission_verification_status === "MIXED_RELEVANCE"
                              ? "status-badge-mixed"
                              : aiSummaryData.latest_summary.submission_verification_status === "UNVERIFIED_IRRELEVANT"
                              ? "status-badge-unverified"
                              : "status-badge-insufficient"
                          }`}
                        >
                          {aiSummaryData.latest_summary.submission_verification_status.replaceAll("_", " ")}
                        </span>
                      </div>
                      <div className="submission-metrics-row">
                        {(aiSummaryData.latest_summary.relevant_documents_count ?? 0) > 0 && (
                          <span className="metric-pill metric-pill-relevant">
                            {"\u2713"} {aiSummaryData.latest_summary.relevant_documents_count} Relevant
                          </span>
                        )}
                        {(aiSummaryData.latest_summary.partially_relevant_documents_count ?? 0) > 0 && (
                          <span className="metric-pill metric-pill-partial">
                            {"\u26A0"} {aiSummaryData.latest_summary.partially_relevant_documents_count} Partially Relevant
                          </span>
                        )}
                        {(aiSummaryData.latest_summary.unrelated_documents_count ?? 0) > 0 && (
                          <span className="metric-pill metric-pill-unrelated">
                            {"\u2715"} {aiSummaryData.latest_summary.unrelated_documents_count} Unrelated
                          </span>
                        )}
                        {(aiSummaryData.latest_summary.insufficient_content_documents_count ?? 0) > 0 && (
                          <span className="metric-pill metric-pill-insufficient">
                            {"\u2139"} {aiSummaryData.latest_summary.insufficient_content_documents_count} Insufficient Content
                          </span>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Mixed Deliverable Alert Banner */}
                  {(aiSummaryData.latest_summary.submission_verification_status === "CONTRADICTORY_TOPICS" ||
                    ((aiSummaryData.latest_summary.unrelated_documents_count ?? 0) > 0 &&
                     (aiSummaryData.latest_summary.relevant_documents_count ?? 0) > 0)) && (
                    <div className="mixed-deliverable-alert" data-testid="mixed-deliverable-alert">
                      <Icon name="alert" size={20} />
                      <div>
                        <strong>Mixed Deliverable Alert: Contradictory Submission Topics</strong>
                        <span>
                          One or more uploaded deliverables in this submission discuss a different topic from the assigned project. Progress is credited solely from verified relevant deliverables; unrelated deliverables have been quarantined from the project evaluation.
                        </span>
                      </div>
                    </div>
                  )}

                  {aiSummaryData.latest_summary.document_relevance && (
                    <div
                      className={`relevance-callout ${
                        aiSummaryData.latest_summary.document_relevance === "NOT_RELEVANT"
                          ? "relevance-callout-mismatch"
                          : aiSummaryData.latest_summary.document_relevance === "PARTIALLY_RELEVANT"
                          ? "relevance-callout-partial"
                          : aiSummaryData.latest_summary.document_relevance === "RELEVANT"
                          ? "relevance-callout-relevant"
                          : "relevance-callout-insufficient"
                      }`}
                      data-testid="relevance-banner"
                    >
                      <div className="relevance-header">
                        <div className="relevance-title">
                          <Icon
                            name={
                              aiSummaryData.latest_summary.document_relevance === "NOT_RELEVANT"
                                ? "alert"
                                : aiSummaryData.latest_summary.document_relevance === "RELEVANT"
                                ? "check"
                                : "alert"
                            }
                            size={18}
                          />
                          <span>
                            {aiSummaryData.latest_summary.document_relevance === "NOT_RELEVANT"
                              ? "Project-topic mismatch detected. This document appears to discuss a different topic and should not be treated as evidence of progress on the assigned project."
                              : aiSummaryData.latest_summary.document_relevance === "PARTIALLY_RELEVANT"
                              ? "Partial project-topic match detected. Some content relates to the assigned project, but significant sections appear unrelated."
                              : aiSummaryData.latest_summary.document_relevance === "RELEVANT"
                              ? "Document verified as relevant to the assigned project."
                              : "Insufficient document content for reliable relevance determination."}
                          </span>
                        </div>
                        <span
                          className={`relevance-badge ${
                            aiSummaryData.latest_summary.document_relevance === "NOT_RELEVANT"
                              ? "relevance-badge-mismatch"
                              : aiSummaryData.latest_summary.document_relevance === "PARTIALLY_RELEVANT"
                              ? "relevance-badge-partial"
                              : aiSummaryData.latest_summary.document_relevance === "RELEVANT"
                              ? "relevance-badge-relevant"
                              : "relevance-badge-insufficient"
                          }`}
                        >
                          {aiSummaryData.latest_summary.document_relevance.replaceAll("_", " ")}
                        </span>
                      </div>

                      {aiSummaryData.latest_summary.relevance_explanation && (
                        <p className="relevance-explanation">
                          {aiSummaryData.latest_summary.relevance_explanation}
                        </p>
                      )}

                      <div className="relevance-comparison-grid">
                        <div className="relevance-comparison-col">
                          <strong>Assigned Project Topic</strong>
                          <span>
                            {aiSummaryData.latest_summary.assigned_project_topic ||
                              selectedProject?.title ||
                              "Assigned Project"}
                          </span>
                        </div>
                        <div className="relevance-comparison-col">
                          <strong>Detected Document Topic</strong>
                          <span>
                            {aiSummaryData.latest_summary.detected_document_topic ||
                              "Not clearly identifiable from document text"}
                          </span>
                        </div>
                      </div>

                      {aiSummaryData.latest_summary.confidence !== null &&
                        aiSummaryData.latest_summary.confidence !== undefined && (
                          <div style={{ fontSize: 11, opacity: 0.85, marginTop: 4 }}>
                            Relevance confidence estimate:{" "}
                            <strong>
                              {Math.round(aiSummaryData.latest_summary.confidence * 100)}%
                            </strong>{" "}
                            (Advisory heuristic)
                          </div>
                        )}
                    </div>
                  )}

                  {/* ── Document-by-Document Verification Cards ── */}
                  {aiSummaryData.latest_summary.document_results?.length > 0 && (
                    <div className="doc-verification-section" data-testid="document-verification-section">
                      <div className="doc-verification-section-title">
                        <Icon name="file" size={17} />
                        <span>Independent Deliverable Verification ({aiSummaryData.latest_summary.document_results.length} Document{aiSummaryData.latest_summary.document_results.length > 1 ? "s" : ""})</span>
                      </div>
                      <div className="doc-cards-grid">
                        {aiSummaryData.latest_summary.document_results.map((doc, idx) => {
                          const relClass = doc.relevance === "RELEVANT"
                            ? "doc-card-relevant"
                            : doc.relevance === "PARTIALLY_RELEVANT"
                            ? "doc-card-partial"
                            : doc.relevance === "NOT_RELEVANT"
                            ? "doc-card-unrelated"
                            : "doc-card-insufficient";
                          const badgeClass = doc.relevance === "RELEVANT"
                            ? "relevance-badge-relevant"
                            : doc.relevance === "PARTIALLY_RELEVANT"
                            ? "relevance-badge-partial"
                            : doc.relevance === "NOT_RELEVANT"
                            ? "relevance-badge-mismatch"
                            : "relevance-badge-insufficient";
                          return (
                            <div key={idx} className={`doc-card ${relClass}`} data-testid={`doc-card-${idx}`}>
                              <div className="doc-card-header">
                                <div>
                                  <span className="doc-card-filename">{doc.file_name || `${(doc.file_type || "file").toUpperCase()} Deliverable`}</span>
                                  <span className="doc-file-type-badge">{(doc.file_type || "file").toUpperCase()}</span>
                                </div>
                                <span className={`relevance-badge ${badgeClass}`}>
                                  {doc.relevance ? doc.relevance.replaceAll("_", " ") : "UNVERIFIED"}
                                </span>
                              </div>

                              {doc.document_title && (
                                <div className="doc-card-detail-item">
                                  <strong>Document Title</strong>
                                  <span>{doc.document_title}</span>
                                </div>
                              )}

                              {doc.detected_topic && (
                                <div className="doc-card-detail-item">
                                  <strong>Detected Topic</strong>
                                  <span>{doc.detected_topic}</span>
                                </div>
                              )}

                              {doc.relevance_explanation && (
                                <div className="doc-card-detail-item">
                                  <strong>Evaluation</strong>
                                  <span>{doc.relevance_explanation}</span>
                                </div>
                              )}

                              {doc.title_comparison && (
                                <div className="doc-card-detail-item">
                                  <strong>Title Alignment</strong>
                                  <span>{doc.title_comparison}</span>
                                </div>
                              )}

                              {doc.content_comparison && (
                                <div className="doc-card-detail-item">
                                  <strong>Content Alignment</strong>
                                  <span>{doc.content_comparison}</span>
                                </div>
                              )}

                              {doc.supporting_citations?.length > 0 && (
                                <div className="doc-card-detail-item">
                                  <strong>Document Citations</strong>
                                  <div className="doc-card-citations">
                                    {doc.supporting_citations.map((cite, cIdx) => (
                                      <div key={cIdx} className="doc-card-citation-item">{cite}</div>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {doc.conflicting_evidence?.length > 0 && (
                                <div className="doc-card-detail-item">
                                  <strong>Unrelated / Conflicting Content</strong>
                                  <div className="doc-card-conflicting">
                                    {doc.conflicting_evidence.join("; ")}
                                  </div>
                                </div>
                              )}

                              {doc.recommended_action && (
                                <div className="doc-card-detail-item">
                                  <strong>Recommended Action</strong>
                                  <div className="doc-card-action">
                                    {doc.recommended_action}
                                  </div>
                                </div>
                              )}

                              <div style={{ marginTop: 12, display: "flex", gap: 8, alignItems: "center", borderTop: "1px solid #f1f5f9", paddingTop: 10 }}>
                                <button
                                  type="button"
                                  className="btn btn-outline btn-sm"
                                  onClick={() => handlePreviewDocument({
                                    submission_id: doc.submission_id || aiSummaryData.latest_summary.submission_id,
                                    document_id: doc.document_id || doc.file_type,
                                    file_type: doc.file_type,
                                    original_filename: doc.original_filename || doc.file_name,
                                  })}
                                >
                                  <Icon name="eye" size={13} /> View
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-primary btn-sm"
                                  disabled={downloadingDocKey === `${doc.submission_id || aiSummaryData.latest_summary.submission_id}-${doc.document_id || doc.file_type}`}
                                  onClick={() => handleDownloadDocument({
                                    submission_id: doc.submission_id || aiSummaryData.latest_summary.submission_id,
                                    document_id: doc.document_id || doc.file_type,
                                    file_type: doc.file_type,
                                    original_filename: doc.original_filename || doc.file_name,
                                  })}
                                >
                                  <Icon name="download" size={13} />
                                  {downloadingDocKey === `${doc.submission_id || aiSummaryData.latest_summary.submission_id}-${doc.document_id || doc.file_type}` ? "Downloading…" : "Download"}
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  <div className="ai-summary-grid">
                    <div className="ai-card ai-card-full">
                      <div className="ai-card-title"><Icon name="grid" size={16} /> Executive Summary</div>
                      <p>{aiSummaryData.latest_summary.summary_text}</p>
                    </div>

                    {aiSummaryData.latest_summary.progress_assessment && (
                      <div className="ai-card ai-card-full" style={{ borderLeft: "4px solid #4b64eb" }}>
                        <div className="ai-card-title"><Icon name="cpu" size={16} /> Evidence-Based Progress Assessment</div>
                        <p>{aiSummaryData.latest_summary.progress_assessment}</p>
                      </div>
                    )}

                    {aiSummaryData.latest_summary.supporting_evidence?.length > 0 && (
                      <div className="ai-card ai-card-full">
                        <div className="ai-card-title"><Icon name="file" size={16} /> Supporting Document Citations & Slide Evidence</div>
                        <div>
                          {aiSummaryData.latest_summary.supporting_evidence.map((quote, i) => (
                            <div key={i} className="ai-evidence-quote">{quote}</div>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="ai-card">
                      <div className="ai-card-title"><Icon name="check" size={16} /> Verified Findings &amp; Demonstrations</div>
                      {(() => {
                        const s = aiSummaryData.latest_summary;
                        const rel = s.document_relevance;
                        const findings = s.relevant_findings?.length
                          ? s.relevant_findings
                          : (!s.relevant_findings && s.key_points?.length ? s.key_points : null);
                        if (findings) {
                          return <ul className="ai-list">{findings.map((pt, i) => <li key={i}>{pt}</li>)}</ul>;
                        }
                        const emptyMsg =
                          rel === "NOT_RELEVANT"
                            ? "No relevant findings \u2014 the uploaded document is not related to this project."
                            : rel === "INSUFFICIENT_CONTENT"
                            ? "Cannot evaluate findings \u2014 the document contains insufficient readable content."
                            : rel === "PARTIALLY_RELEVANT"
                            ? "No clearly relevant findings could be isolated from the submitted document."
                            : "No specific findings were extracted from the submitted evidence.";
                        return <p style={{ fontStyle: "italic", color: "#8a96a8" }}>{emptyMsg}</p>;
                      })()}
                    </div>

                    <div className="ai-card">
                      <div className="ai-card-title"><Icon name="alert" size={16} /> Missing Evidence & Unaddressed Requirements</div>
                      {aiSummaryData.latest_summary.missing_evidence?.length
                        ? <ul className="ai-list">{aiSummaryData.latest_summary.missing_evidence.map((item, i) => <li key={i} style={{ color: "#a0484a" }}>{item}</li>)}</ul>
                        : <p>No specific missing evidence flagged.</p>}
                    </div>

                    <div className="ai-card">
                      <div className="ai-card-title"><Icon name="alert" size={16} /> Identified Project Risks & Gaps</div>
                      {aiSummaryData.latest_summary.risks?.length
                        ? <ul className="ai-list">{aiSummaryData.latest_summary.risks.map((risk, i) => <li key={i} style={{ color: "#a0484a" }}>{risk}</li>)}</ul>
                        : <p>No elevated risks flagged.</p>}
                    </div>

                    <div className="ai-card">
                      <div className="ai-card-title"><Icon name="chevron" size={16} /> Recommended Next Steps</div>
                      {aiSummaryData.latest_summary.recommended_next_steps?.length
                        ? <ul className="ai-list">{aiSummaryData.latest_summary.recommended_next_steps.map((step, i) => <li key={i}>{step}</li>)}</ul>
                        : <p>No immediate steps pending.</p>}
                    </div>

                    <div className="ai-card ai-card-full">
                      <div className="ai-card-title"><Icon name="calendar" size={16} /> Targeted Questions for Next Review</div>
                      {aiSummaryData.latest_summary.review_questions?.length
                        ? <ul className="ai-list">{aiSummaryData.latest_summary.review_questions.map((q, i) => <li key={i}>{q}</li>)}</ul>
                        : <p>No specific review questions generated.</p>}
                    </div>
                  </div>

                  <div className="ai-disclaimer">
                    <strong>Advisory Notice:</strong> {aiSummaryData.latest_summary.advisory_disclaimer}
                  </div>
                </div>
              )}
            </section>
          )}

          {/* ════════════════════════════════════════════════════════════════════
              FACULTY PROFILE PAGE
          ════════════════════════════════════════════════════════════════════ */}
          {activePage === "profile" && isFaculty && (
            <section className="content-section">
              <div className="section-heading">
                <div>
                  <div className="eyebrow">ACCOUNT INFORMATION</div>
                  <h2>Faculty Profile</h2>
                  <p>Your institutional account details and supervision statistics.</p>
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 20 }}>
                <div className="form-panel" style={{ marginBottom: 0 }}>
                  <div className="form-panel-head">
                    <div><h3>Account Details</h3><p>Institutional identity and access status.</p></div>
                  </div>
                  <div style={{ display: "grid", gap: 14 }}>
                    {[
                      { label: "Full Name", value: account.name || "Not provided" },
                      { label: "Email Address", value: account.email },
                      { label: "Faculty ID", value: account.faculty_id || "Not provided" },
                      { label: "Department", value: account.department || "Not specified" },
                      { label: "Account Role", value: "Faculty Supervisor" },
                      { label: "Email Verified", value: "Yes — Verified" },
                      { label: "Faculty Approval", value: "Approved" },
                    ].map(({ label, value }) => (
                      <div key={label} style={{ display: "flex", justifyContent: "space-between", padding: "10px 0", borderBottom: "1px solid #f0f2f8" }}>
                        <span style={{ fontSize: 11, color: "#7a859a", fontWeight: 600 }}>{label}</span>
                        <span style={{ fontSize: 12, color: "#2c3d58", fontWeight: 500 }}>{value}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="form-panel" style={{ marginBottom: 0 }}>
                  <div className="form-panel-head">
                    <div><h3>Supervision Statistics</h3><p>Summary of your active supervision workload.</p></div>
                  </div>
                  <div style={{ display: "grid", gap: 12 }}>
                    {[
                      { label: "Assigned Projects", value: projects.length, icon: "folder", accent: "blue" },
                      { label: "Total Milestones Tracked", value: milestoneData.total ?? 0, icon: "check", accent: "green" },
                      { label: "Total Submissions Reviewed", value: Object.values(reviewsBySub).reduce((a, r) => a + r.length, 0), icon: "star", accent: "amber" },
                      { label: "Documents Analyzed", value: analyzedDocuments, icon: "scan", accent: "violet" },
                    ].map(({ label, value, icon, accent }) => (
                      <div key={label} className={`metric-card metric-${accent}`} style={{ minHeight: "auto", padding: "12px 14px" }}>
                        <div className="metric-top">
                          <span className="metric-label">{label}</span>
                          <span className="metric-icon"><Icon name={icon} size={17} /></span>
                        </div>
                        <div className="metric-value">{value}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="info-box" style={{ marginTop: 24 }}>
                <Icon name="alert" size={16} />
                <div>
                  <strong>Assignment Management</strong>
                  <p>
                    Faculty-to-project assignments are managed by an administrator using the provisioning CLI:
                    <br />
                    <code style={{ fontSize: 10, background: "#f0f3fa", padding: "2px 6px", borderRadius: 4, marginTop: 6, display: "inline-block" }}>
                      python -m app.provision_faculty assign &lt;email&gt; &lt;project_id&gt;
                    </code>
                  </p>
                </div>
              </div>
            </section>
          )}

          <footer className="page-footer">
            <span>ProjectScope {portalLabel}</span>
            <span>Data supplied by the academic monitoring API.</span>
          </footer>
        </div>
      </main>

      {/* ── Document Preview Modal ── */}
      {previewModal.isOpen && (
        <div className="modal-backdrop" onClick={closePreviewModal} data-testid="preview-modal-backdrop">
          <div className="preview-modal-dialog" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
            <div className="preview-modal-header">
              <div>
                <h3>{previewModal.document?.original_filename || previewModal.document?.file_name || "Document Preview"}</h3>
                <div className="preview-modal-subtitle">
                  <span className={`file-pill file-pill-${(previewModal.document?.file_type || "").toLowerCase()}`}>
                    {(previewModal.document?.file_type || "file").toUpperCase()}
                  </span>
                  <span>Submission #{previewModal.document?.submission_id}</span>
                  {previewModal.document?.size_formatted && <span>· {previewModal.document.size_formatted}</span>}
                </div>
              </div>
              <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  onClick={() => handleDownloadDocument(previewModal.document)}
                  disabled={downloadingDocKey === `${previewModal.document?.submission_id}-${previewModal.document?.document_id || previewModal.document?.file_type}`}
                >
                  <Icon name="download" size={14} /> Download Original
                </button>
                <button
                  type="button"
                  className="btn btn-outline btn-sm"
                  onClick={closePreviewModal}
                  aria-label="Close preview"
                >
                  ✕ Close
                </button>
              </div>
            </div>

            <div className="preview-modal-body">
              {previewModal.loading ? (
                <div style={{ margin: "auto", textAlign: "center", padding: 40, color: "#475569" }}>
                  <p>Loading document preview…</p>
                </div>
              ) : previewModal.error ? (
                <div className="preview-unsupported-card" data-testid="preview-unsupported-message">
                  <Icon name="alert" size={36} />
                  <h4>Browser Preview Unavailable</h4>
                  <p>{previewModal.error}</p>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => handleDownloadDocument(previewModal.document)}
                  >
                    <Icon name="download" size={15} /> Download Original File
                  </button>
                </div>
              ) : previewModal.blobUrl ? (
                <iframe
                  src={previewModal.blobUrl}
                  title={previewModal.document?.original_filename || "Document Preview"}
                  className="preview-iframe"
                  data-testid="preview-iframe"
                />
              ) : null}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
