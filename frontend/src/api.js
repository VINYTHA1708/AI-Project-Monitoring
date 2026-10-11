const API_TARGET_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");
const API_BASE_URL = import.meta.env.DEV ? "/api" : API_TARGET_URL;
let accessToken = null;

export function setAccessToken(token) {
  accessToken = token;
}

export function getAccessToken() {
  return accessToken;
}

async function request(path, { signal, method = "GET", body } = {}) {
  let response;
  const headers = { Accept: "application/json" };
  let requestBody = undefined;

  if (body instanceof FormData) {
    // When sending FormData, the browser automatically sets Content-Type with the boundary
    requestBody = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    requestBody = JSON.stringify(body);
  }

  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: requestBody,
      signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error(
      `Could not connect to the backend at ${API_TARGET_URL}. Check that the API is running and CORS permits this frontend.`,
    );
  }

  if (!response.ok) {
    if (response.status === 401 && accessToken) {
      accessToken = null;
      window.dispatchEvent(new Event("auth:unauthorized"));
    }
    let detail = "";
    try {
      const errorData = await response.json();
      detail = Array.isArray(errorData.detail)
        ? errorData.detail.map((item) => item.msg).join("; ")
        : errorData.detail || errorData.message || "";
    } catch {
      // The response may not contain JSON.
    }
    throw new Error(
      detail || `The backend request failed (${response.status}).`,
    );
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

export const api = {
  // Authentication
  login(credentials) {
    return request("/auth/login", { method: "POST", body: credentials });
  },
  registerFaculty(details) {
    return request("/auth/register/faculty", { method: "POST", body: details });
  },
  registerStudent(details) {
    return request("/auth/register/student", { method: "POST", body: details });
  },
  verifyOtp(details) {
    return request("/auth/otp/verify", { method: "POST", body: details });
  },
  resendOtp(details) {
    return request("/auth/otp/resend", { method: "POST", body: details });
  },
  getMe() {
    return request("/auth/me");
  },

  // Projects
  getProjects(signal) {
    return request("/projects/", { signal });
  },
  getProject(projectId, signal) {
    return request(`/projects/${encodeURIComponent(projectId)}`, { signal });
  },
  createProject(details) {
    return request("/projects/", { method: "POST", body: details });
  },
  updateProject(projectId, details) {
    return request(`/projects/${encodeURIComponent(projectId)}`, {
      method: "PUT",
      body: details,
    });
  },
  deleteProject(projectId) {
    return request(`/projects/${encodeURIComponent(projectId)}`, {
      method: "DELETE",
    });
  },

  // Milestones
  getMilestones(projectId, signal) {
    return request(`/projects/${encodeURIComponent(projectId)}/milestones/`, { signal });
  },
  createMilestone(projectId, details) {
    return request(`/projects/${encodeURIComponent(projectId)}/milestones/`, {
      method: "POST",
      body: details,
    });
  },
  updateMilestone(projectId, milestoneId, details) {
    return request(
      `/projects/${encodeURIComponent(projectId)}/milestones/${encodeURIComponent(milestoneId)}`,
      { method: "PUT", body: details },
    );
  },
  deleteMilestone(projectId, milestoneId) {
    return request(
      `/projects/${encodeURIComponent(projectId)}/milestones/${encodeURIComponent(milestoneId)}`,
      { method: "DELETE" },
    );
  },

  // Project Members
  getMembers(projectId, signal) {
    return request(`/projects/${encodeURIComponent(projectId)}/members/`, { signal });
  },
  addMember(projectId, details) {
    return request(`/projects/${encodeURIComponent(projectId)}/members/`, {
      method: "POST",
      body: details,
    });
  },
  removeMember(projectId, studentId) {
    return request(
      `/projects/${encodeURIComponent(projectId)}/members/${encodeURIComponent(studentId)}`,
      { method: "DELETE" },
    );
  },

  // Students (Faculty only)
  getStudents(signal) {
    return request("/students/", { signal });
  },

  // Submissions
  getSubmissions(projectId, signal) {
    return request(`/projects/${encodeURIComponent(projectId)}/submissions/`, { signal });
  },
  uploadSubmission(projectId, formData) {
    return request(`/projects/${encodeURIComponent(projectId)}/submissions/upload`, {
      method: "POST",
      body: formData,
    });
  },
  deleteSubmission(projectId, submissionId) {
    return request(
      `/projects/${encodeURIComponent(projectId)}/submissions/${encodeURIComponent(submissionId)}`,
      { method: "DELETE" },
    );
  },

  // Progress & Analysis
  getProjectProgress(projectId, signal) {
    return request(`/projects/${encodeURIComponent(projectId)}/progress`, { signal });
  },
  getSubmissionAnalyses(projectId, submissionId, signal) {
    return request(
      `/projects/${encodeURIComponent(projectId)}/submissions/${encodeURIComponent(submissionId)}/analysis`,
      { signal },
    );
  },
  analyzeDocument(projectId, submissionId, documentType) {
    return request(
      `/projects/${encodeURIComponent(projectId)}/submissions/${encodeURIComponent(submissionId)}/analyze`,
      {
        method: "POST",
        body: { document_type: documentType },
      },
    );
  },
  getAnalysisDownloadUrl(projectId, submissionId, documentType) {
    return `${API_BASE_URL}/projects/${encodeURIComponent(projectId)}/submissions/${encodeURIComponent(submissionId)}/analysis/${encodeURIComponent(documentType)}/download`;
  },

  // Faculty Reviews & Scoring
  getSubmissionReviews(projectId, submissionId, signal) {
    return request(
      `/projects/${encodeURIComponent(projectId)}/submissions/${encodeURIComponent(submissionId)}/reviews/`,
      { signal },
    );
  },
  createReview(projectId, submissionId, details) {
    return request(
      `/projects/${encodeURIComponent(projectId)}/submissions/${encodeURIComponent(submissionId)}/reviews/`,
      {
        method: "POST",
        body: details,
      },
    );
  },
  updateReview(projectId, submissionId, reviewId, details) {
    return request(
      `/projects/${encodeURIComponent(projectId)}/submissions/${encodeURIComponent(submissionId)}/reviews/${encodeURIComponent(reviewId)}`,
      {
        method: "PUT",
        body: details,
      },
    );
  },
  deleteReview(projectId, submissionId, reviewId) {
    return request(
      `/projects/${encodeURIComponent(projectId)}/submissions/${encodeURIComponent(submissionId)}/reviews/${encodeURIComponent(reviewId)}`,
      { method: "DELETE" },
    );
  },

  // GitHub Analysis
  getGitHubAnalysis(projectId, signal) {
    return request(`/projects/${encodeURIComponent(projectId)}/github/analysis`, { signal });
  },
  analyzeGitHub(projectId) {
    return request(`/projects/${encodeURIComponent(projectId)}/github/analyze`, { method: "POST" });
  },

  // LLM Project Summaries
  getAISummary(projectId, signal) {
    return request(`/projects/${encodeURIComponent(projectId)}/ai-summary/`, { signal });
  },
  generateAISummary(projectId) {
    return request(`/projects/${encodeURIComponent(projectId)}/ai-summary/generate`, { method: "POST" });
  },
};

export { API_BASE_URL };

