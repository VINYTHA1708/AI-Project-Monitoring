import { useCallback, useEffect, useMemo, useState } from "react";
import { api, setAccessToken } from "./api.js";

const NAV_ITEMS = [
  { label: "Dashboard", href: "#dashboard", icon: "grid" },
  { label: "Projects", href: "#projects", icon: "folder" },
  { label: "Submissions", href: "#submissions", icon: "file" },
  { label: "Document Analysis", href: "#document-analysis", icon: "scan" },
];

const PAGE_DETAILS = {
  dashboard: {
    title: "Dashboard",
    description: "A clear view of project progress, submissions, and document readiness.",
  },
  projects: {
    title: "Projects",
    description: "Browse projects available to the faculty workspace and select one to review.",
  },
  submissions: {
    title: "Submissions",
    description: "Review submission weeks, status, and missing project documents.",
  },
  "document-analysis": {
    title: "Document Analysis",
    description: "Review report and SRS extraction outcomes and section completeness.",
  },
};

function pageFromHash() {
  const page = window.location.hash.replace(/^#/, "");
  return Object.hasOwn(PAGE_DETAILS, page) ? page : "dashboard";
}

function Icon({ name, size = 18 }) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": true,
  };
  const paths = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
    folder: <><path d="M3 7.5A1.5 1.5 0 0 1 4.5 6H10l2 2h7.5A1.5 1.5 0 0 1 21 9.5v8a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5z" /><path d="M3 10h18" /></>,
    file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6M8 13h8M8 17h8" /></>,
    scan: <><path d="M4 7V5a1 1 0 0 1 1-1h2M17 4h2a1 1 0 0 1 1 1v2M20 17v2a1 1 0 0 1-1 1h-2M7 20H5a1 1 0 0 1-1-1v-2" /><path d="M4 12h16M8 9h8M8 15h5" /></>,
    refresh: <><path d="M20 7v5h-5" /><path d="M4 17v-5h5" /><path d="M5.6 9A7 7 0 0 1 18 6.3L20 12M4 12l2 5.7A7 7 0 0 0 18.4 15" /></>,
    chevron: <path d="m9 18 6-6-6-6" />,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    alert: <><path d="M10.3 3.9 2.7 17a2 2 0 0 0 1.7 3h15.2a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4M12 17h.01" /></>,
  };
  return <svg {...common}>{paths[name]}</svg>;
}

function StatusBadge({ status }) {
  const key = (status || "unknown").toLowerCase().replaceAll(" ", "_");
  const labels = {
    complete: "Complete",
    incomplete: "Incomplete",
    failed: "Failed",
    not_analyzed: "Not analyzed",
    no_text_found: "No text found",
    pending: "Pending",
    submitted: "Submitted",
    active: "Active",
    completed: "Completed",
    at_risk: "At risk",
    in_progress: "In progress",
    not_started: "Not started",
  };
  return (
    <span className={`badge badge-${key}`}>
      <span className="badge-dot" />
      {labels[key] || status || "Unknown"}
    </span>
  );
}

function MetricCard({ label, value, detail, icon, accent }) {
  return (
    <article className={`metric-card metric-${accent}`}>
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
  if (value === null || value === undefined) {
    return <span className="score-unavailable">Score unavailable</span>;
  }
  return (
    <span className="score-value">
      <span className="score-track"><span style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></span>
      {value}%
    </span>
  );
}

function DocumentCard({ document }) {
  const status = document.status || document.analysis_status || "not_analyzed";
  return (
    <article className="document-card">
      <div className="document-card-head">
        <div className="document-name">
          <span className="document-icon"><Icon name="file" size={17} /></span>
          <div>
            <h4>{document.document_type === "srs" ? "SRS" : "Project report"}</h4>
            <p>Submission #{document.submission_id}</p>
          </div>
        </div>
        <StatusBadge status={status} />
      </div>
      <div className="document-score">
        <span>Completeness</span>
        <Completeness value={document.completeness_percentage} />
      </div>
      {document.missing_sections?.length > 0 && (
        <div className="document-section-group">
          <span className="section-label">Missing sections</span>
          <div className="tag-list">
            {document.missing_sections.map((section) => <span className="tag tag-missing" key={section}>{section}</span>)}
          </div>
        </div>
      )}
      {document.detected_sections?.length > 0 && (
        <div className="document-section-group">
          <span className="section-label">Detected sections</span>
          <div className="tag-list">
            {document.detected_sections.map((section) => <span className="tag" key={section}>{section}</span>)}
          </div>
        </div>
      )}
      {document.warnings?.length > 0 && (
        <div className="document-message warning-message">
          <Icon name="alert" size={15} />
          <span>{document.warnings.join(" ")}</span>
        </div>
      )}
      {document.extraction_errors?.length > 0 && (
        <div className="document-message error-message">
          <Icon name="alert" size={15} />
          <span>{document.extraction_errors.join(" ")}</span>
        </div>
      )}
      {status === "not_analyzed" && (
        <p className="not-analyzed-note">Run document analysis in the backend to see section results.</p>
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

function AuthScreen({ onAuthenticated }) {
  const [stage, setStage] = useState("login");
  const [form, setForm] = useState({
    name: "",
    faculty_id: "",
    email: "",
    department: "",
    password: "",
    code: "",
  });
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);

  const update = (event) => {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
  };
  const activePurpose = stage === "registration-otp" ? "registration" : "login";

  async function submit(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    setLoading(true);
    try {
      if (stage === "login") {
        await api.login({ email: form.email, password: form.password });
        setForm((current) => ({ ...current, password: "", code: "" }));
        setStage("login-otp");
        setNotice("Enter the sign-in code sent to your institutional email.");
      } else if (stage === "register") {
        await api.registerFaculty({
          name: form.name,
          faculty_id: form.faculty_id,
          email: form.email,
          department: form.department || null,
          password: form.password,
        });
        setForm((current) => ({ ...current, password: "", code: "" }));
        setStage("registration-otp");
        setNotice("Enter the verification code sent to your email.");
      } else {
        const result = await api.verifyOtp({
          email: form.email,
          code: form.code,
          purpose: activePurpose,
        });
        setForm((current) => ({ ...current, code: "" }));
        if (activePurpose === "registration") {
          setStage("login");
          setNotice(result.message || "Email verified. You can now sign in.");
        } else if (result.account?.role !== "faculty") {
          setStage("login");
          setNotice("This dashboard is available to faculty accounts only.");
        } else {
          setAccessToken(result.access_token);
          onAuthenticated(result.account);
        }
      }
    } catch (requestError) {
      if (requestError.name !== "AbortError") setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  async function resendCode() {
    setError("");
    setNotice("");
    setLoading(true);
    try {
      const result = await api.resendOtp({
        email: form.email,
        purpose: activePurpose,
      });
      setNotice(result.message || "If eligible, a new code has been sent.");
    } catch (requestError) {
      if (requestError.name !== "AbortError") setError(requestError.message);
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
          <span className="brand-copy"><strong>Project<span>Scope</span></strong><small>FACULTY PORTAL</small></span>
        </a>
        <div className="eyebrow">SECURE WORKSPACE <span className="eyebrow-line" /></div>
        <h1 id="auth-title">
          {stage === "register" ? "Create faculty account" : otpStage ? "Verify your email" : "Welcome back"}
        </h1>
        <p className="auth-description">
          {stage === "register"
            ? "Faculty accounts require an approved institutional email."
            : otpStage
              ? `Enter the one-time code sent to ${form.email}.`
              : "Sign in to review assigned student projects."}
        </p>
        {error && <div className="auth-message auth-error" role="alert">{error}</div>}
        {notice && <div className="auth-message auth-notice" role="status">{notice}</div>}
        <form className="auth-form" onSubmit={submit}>
          {stage === "register" && (
            <>
              <label>Full name<input name="name" value={form.name} onChange={update} required maxLength={150} autoComplete="name" /></label>
              <label>Faculty ID<input name="faculty_id" value={form.faculty_id} onChange={update} required maxLength={50} /></label>
              <label>Department <span className="optional-label">optional</span><input name="department" value={form.department} onChange={update} maxLength={150} /></label>
            </>
          )}
          {!otpStage && (
            <>
              <label>Institutional email<input name="email" value={form.email} onChange={update} type="email" required autoComplete="email" /></label>
              <label>Password<input name="password" value={form.password} onChange={update} type="password" required minLength={12} maxLength={128} autoComplete={stage === "register" ? "new-password" : "current-password"} /></label>
            </>
          )}
          {otpStage && <label>Six-digit verification code<input name="code" value={form.code} onChange={update} inputMode="numeric" pattern="[0-9]{6}" maxLength={6} required autoComplete="one-time-code" /></label>}
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
            {stage === "register" ? "Already registered?" : "Need a faculty account?"}{" "}
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

function App() {
  const [account, setAccount] = useState(null);
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("");
  const [progress, setProgress] = useState(null);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [progressLoading, setProgressLoading] = useState(false);
  const [error, setError] = useState("");
  const [analysisDetailWarning, setAnalysisDetailWarning] = useState("");
  const [activePage, setActivePage] = useState(pageFromHash);

  const clearAuthentication = useCallback(() => {
    setAccessToken(null);
    setAccount(null);
    setProjects([]);
    setProgress(null);
    setProjectId("");
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
    } catch (loadError) {
      if (loadError.name !== "AbortError") setError(loadError.message);
      setProjects([]);
      setProjectId("");
    } finally {
      if (!signal?.aborted) setProjectsLoading(false);
    }
  }, []);

  const loadProgress = useCallback(async (id, signal) => {
    if (!id) {
      setProgress(null);
      setProgressLoading(false);
      return;
    }
    setProgressLoading(true);
    setError("");
    setAnalysisDetailWarning("");
    try {
      const progressData = await api.getProjectProgress(id, signal);
      const submissions = progressData.submissions?.details || [];
      const analysisResponses = await Promise.all(submissions.map(async (submission) => {
        try {
          return {
            submissionId: submission.submission_id,
            records: await api.getSubmissionAnalyses(
              id,
              submission.submission_id,
              signal,
            ),
          };
        } catch (analysisError) {
          if (analysisError.name === "AbortError") throw analysisError;
          return { submissionId: submission.submission_id, error: analysisError.message };
        }
      }));

      const recordsBySubmission = new Map(
        analysisResponses.map((result) => [
          result.submissionId,
          new Map((result.records || []).map((record) => [record.document_type, record])),
        ]),
      );
      const detailFailures = analysisResponses.filter((result) => result.error);
      const enrichedProgress = {
        ...progressData,
        submissions: {
          ...progressData.submissions,
          details: submissions.map((submission) => {
            const savedRecords = recordsBySubmission.get(submission.submission_id);
            return {
              ...submission,
              document_analyses: (submission.document_analyses || []).map((document) => {
                const savedRecord = savedRecords?.get(document.document_type);
                return savedRecord
                  ? { ...document, detected_sections: savedRecord.detected_sections || [] }
                  : document;
              }),
            };
          }),
        },
      };
      setProgress(enrichedProgress);
      if (detailFailures.length) {
        setAnalysisDetailWarning(
          `Section details could not be loaded for ${detailFailures.length} ${detailFailures.length === 1 ? "submission" : "submissions"}.`,
        );
      }
    } catch (loadError) {
      if (loadError.name !== "AbortError") {
        setProgress(null);
        setError(loadError.message);
      }
    } finally {
      if (!signal?.aborted) setProgressLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!account) return undefined;
    const controller = new AbortController();
    loadProjects(controller.signal);
    return () => controller.abort();
  }, [account, loadProjects]);

  useEffect(() => {
    const syncPageWithHash = () => {
      const page = pageFromHash();
      setActivePage(page);
      if (!Object.hasOwn(PAGE_DETAILS, window.location.hash.replace(/^#/, ""))) {
        window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#dashboard`);
      }
    };
    window.addEventListener("hashchange", syncPageWithHash);
    syncPageWithHash();
    return () => window.removeEventListener("hashchange", syncPageWithHash);
  }, []);

  useEffect(() => {
    if (!account || !projectId) return undefined;
    const controller = new AbortController();
    loadProgress(projectId, controller.signal);
    return () => controller.abort();
  }, [account, projectId, loadProgress]);

  const selectedProject = useMemo(
    () => projects.find((project) => String(project.id) === String(projectId)),
    [projects, projectId],
  );
  const details = progress?.submissions?.details || [];
  const documents = details.flatMap((submission) => submission.document_analyses || []);
  const projectStatus = progress?.overall_status || selectedProject?.status;
  const milestoneData = progress?.milestones || {};
  const submissionWeeks = progress?.submissions?.weeks_submitted || [];
  const pendingDocuments = documents.filter((document) => document.status === "not_analyzed").length;
  const analyzedDocuments = documents.filter((document) => document.status !== "not_analyzed").length;

  const refresh = () => {
    if (!projectId) {
      loadProjects();
      return;
    }
    loadProgress(projectId);
  };

  const signOut = clearAuthentication;
  if (!account) return <AuthScreen onAuthenticated={setAccount} />;

  const currentPage = PAGE_DETAILS[activePage];
  const needsProgress = activePage !== "projects";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#dashboard">
          <span className="brand-mark"><Icon name="grid" size={20} /></span>
          <span className="brand-copy"><strong>Project<span>Scope</span></strong><small>FACULTY PORTAL</small></span>
        </a>
        <div className="nav-caption">WORKSPACE</div>
        <nav className="side-nav" aria-label="Main navigation">
          {NAV_ITEMS.map((item) => (
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
            <span className="note-icon"><Icon name="scan" size={17} /></span>
            <strong>Review workspace</strong>
            <p>Track project milestones and document readiness in one place.</p>
          </div>
          <div className="faculty-profile">
            <div className="profile-avatar">F</div>
            <div><strong>{account.name || "Faculty view"}</strong><span>Project monitoring</span></div>
          </div>
        </div>
      </aside>

      <main className="main-content" id="dashboard">
        <header className="topbar">
          <div className="breadcrumb"><span>Workspace</span><Icon name="chevron" size={14} /><strong>{currentPage.title}</strong></div>
          <div className="topbar-actions">
            <span className="api-indicator"><span />Live API</span>
            <button className="refresh-button" onClick={refresh} disabled={projectsLoading || progressLoading} aria-label="Refresh dashboard">
              <Icon name="refresh" size={16} /> <span>Refresh</span>
            </button>
            <button className="refresh-button" onClick={signOut}>Sign out</button>
          </div>
        </header>

        <div className="page-wrap">
          <section className="page-heading">
            <div>
              <div className="eyebrow">FACULTY WORKSPACE <span className="eyebrow-line" /></div>
              <h1>{currentPage.title}</h1>
              <p className="heading-subtitle">{currentPage.description}</p>
            </div>
            <label className="project-select-wrap">
              <span>Selected project</span>
              <select
                value={projectId}
                onChange={(event) => {
                  setProgress(null);
                  setProjectId(event.target.value);
                }}
                disabled={projectsLoading || projects.length === 0}
                aria-label="Select a project"
              >
                {projects.length === 0 && <option value="">No projects available</option>}
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>#{project.id} · {project.title}</option>
                ))}
              </select>
            </label>
          </section>

          {error && (
            <div className="error-banner" role="alert">
              <Icon name="alert" size={18} />
              <div><strong>Dashboard data could not be loaded</strong><p>{error}</p></div>
              <button onClick={refresh}>Try again</button>
            </div>
          )}
          {analysisDetailWarning && activePage === "document-analysis" && (
            <div className="detail-warning" role="status">
              <Icon name="alert" size={16} />
              <span>{analysisDetailWarning} Status and completeness data are still shown from project progress.</span>
            </div>
          )}

          {(projectsLoading || (needsProgress && progressLoading && !progress)) && <LoadingScreen />}

          {!projectsLoading && !error && projects.length === 0 && (
            <div className="state-panel empty-state">
              <span className="empty-icon"><Icon name="folder" size={23} /></span>
              <div><strong>No projects yet</strong><p>Projects will appear here when they are available through the backend.</p></div>
            </div>
          )}

          {needsProgress && progressLoading && progress && <div className="updating-line"><span className="spinner spinner-small" /> Refreshing project data…</div>}

          {activePage === "projects" && !projectsLoading && projects.length > 0 && (
            <section className="projects-grid" aria-label="Available projects">
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
                    <button
                      className={`project-select-button ${selected ? "selected" : ""}`}
                      onClick={() => {
                        setProgress(null);
                        setProjectId(String(project.id));
                      }}
                      disabled={selected}
                    >
                      {selected ? "Currently selected" : "View this project"}
                      {!selected && <Icon name="chevron" size={15} />}
                    </button>
                  </article>
                );
              })}
            </section>
          )}

          {needsProgress && !progressLoading && !progress && !error && projects.length > 0 && (
            <div className="state-panel"><div><strong>Project progress unavailable</strong><p>Select a project or refresh to load its progress details.</p></div></div>
          )}

          {activePage === "dashboard" && progress && (
            <>
              <section className="project-banner">
                <div className="project-banner-main">
                  <div className="project-symbol"><Icon name="folder" size={22} /></div>
                  <div>
                    <div className="project-overline">CURRENT PROJECT <span>·</span> ID #{progress.project_id}</div>
                    <h2>{progress.project_title}</h2>
                    <div className="project-meta"><StatusBadge status={projectStatus} /><span className="meta-divider" /><span><Icon name="calendar" size={14} /> {progress.submissions?.total || 0} recorded submissions</span></div>
                  </div>
                </div>
                <div className="banner-progress">
                  <div className="banner-progress-copy"><span>Milestone completion</span><strong>{milestoneData.completion_percentage ?? 0}%</strong></div>
                  <div className="progress-track"><span style={{ width: `${Math.max(0, Math.min(100, milestoneData.completion_percentage || 0))}%` }} /></div>
                  <small>{milestoneData.completed || 0} of {milestoneData.total || 0} milestones completed</small>
                </div>
              </section>
              <section className="metrics-grid" aria-label="Project summary">
                <MetricCard label="Total milestones" value={milestoneData.total ?? 0} detail="Planned project checkpoints" icon="grid" accent="blue" />
                <MetricCard label="Completed" value={milestoneData.completed ?? 0} detail="Milestones marked complete" icon="check" accent="green" />
                <MetricCard label="Pending" value={milestoneData.pending ?? 0} detail={milestoneData.overdue?.length ? `${milestoneData.overdue.length} overdue` : "Awaiting completion"} icon="calendar" accent="amber" />
                <MetricCard label="Submissions" value={progress.submissions?.total ?? 0} detail={submissionWeeks.length ? `Weeks ${submissionWeeks.join(", ")}` : "No submission weeks"} icon="file" accent="violet" />
              </section>
              {milestoneData.overdue?.length > 0 && (
                <section className="overdue-panel">
                  <div className="overdue-title"><Icon name="alert" size={17} /><strong>Overdue milestones</strong></div>
                  <div className="overdue-list">{milestoneData.overdue.map((milestone) => <span key={milestone.id}>{milestone.title}<small>Due {milestone.due_date}</small></span>)}</div>
                </section>
              )}
              <section className="dashboard-summaries">
                <article className="dashboard-summary-card">
                  <div className="summary-card-heading"><span className="summary-icon summary-icon-blue"><Icon name="file" size={18} /></span><h2>Submission activity</h2></div>
                  <strong className="summary-number">{details.length}</strong>
                  <p>{submissionWeeks.length ? `Submitted in weeks ${submissionWeeks.join(", ")}` : "No submission weeks recorded."}</p>
                  <a href="#submissions">Review submissions <Icon name="chevron" size={14} /></a>
                </article>
                <article className="dashboard-summary-card">
                  <div className="summary-card-heading"><span className="summary-icon summary-icon-violet"><Icon name="scan" size={18} /></span><h2>Document readiness</h2></div>
                  <strong className="summary-number">{analyzedDocuments}<small> analyzed</small></strong>
                  <p>{pendingDocuments} uploaded {pendingDocuments === 1 ? "document is" : "documents are"} not analyzed yet.</p>
                  <a href="#document-analysis">Review document analysis <Icon name="chevron" size={14} /></a>
                </article>
              </section>
            </>
          )}

          {activePage === "submissions" && progress && (
            details.length === 0 ? (
              <div className="table-empty"><span className="empty-icon"><Icon name="file" size={20} /></span><strong>No submissions recorded</strong><p>Submission details will appear here once available.</p></div>
            ) : (
              <section className="content-section">
                <div className="section-heading"><div><div className="eyebrow">WEEKLY ACTIVITY</div><h2>Project submissions</h2><p>Uploaded materials and submission status by week.</p></div><span className="section-count">{details.length} {details.length === 1 ? "submission" : "submissions"}</span></div>
                <div className="table-shell">
                  <table>
                    <thead><tr><th>Submission</th><th>Week</th><th>Status</th><th>Missing documents</th><th>Submitted</th></tr></thead>
                    <tbody>{details.map((submission) => (
                      <tr key={submission.submission_id}>
                        <td><span className="submission-id">SUB-{String(submission.submission_id).padStart(3, "0")}</span><small>ID #{submission.submission_id}</small></td>
                        <td><span className="week-chip">Week {submission.week_number}</span></td>
                        <td><StatusBadge status={submission.status} /></td>
                        <td>{submission.missing_documents?.length ? <div className="tag-list">{submission.missing_documents.map((doc) => <span className="tag tag-missing" key={doc}>{doc}</span>)}</div> : <span className="all-present"><Icon name="check" size={14} /> None</span>}</td>
                        <td className="date-cell">{submission.submitted_at ? new Date(submission.submitted_at).toLocaleDateString() : "—"}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              </section>
            )
          )}

          {activePage === "document-analysis" && progress && (
            <section className="content-section analysis-section">
              <div className="section-heading"><div><div className="eyebrow">DOCUMENT REVIEW</div><h2>Report and SRS analysis</h2><p>Section coverage and extraction outcomes for uploaded reports and SRS files.</p></div><div className="analysis-summary">{analyzedDocuments} analyzed <span /> {pendingDocuments} not analyzed</div></div>
              {documents.length === 0 ? (
                <div className="table-empty"><span className="empty-icon"><Icon name="scan" size={20} /></span><strong>No document analyses available</strong><p>Reports and SRS analyses will appear when those documents are uploaded and analyzed.</p></div>
              ) : (
                <div className="document-grid">{documents.map((document) => <DocumentCard key={`${document.submission_id}-${document.document_type}`} document={document} />)}</div>
              )}
            </section>
          )}

          <footer className="page-footer"><span>ProjectScope Faculty Dashboard</span><span>Data is supplied by the project monitoring API.</span></footer>
        </div>
      </main>
    </div>
  );
}

export default App;
