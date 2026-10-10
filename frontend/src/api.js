const API_TARGET_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");
const API_BASE_URL = import.meta.env.DEV ? "/api" : API_TARGET_URL;
let accessToken = null;

export function setAccessToken(token) {
  accessToken = token;
}

async function request(path, { signal, method = "GET", body } = {}) {
  let response;
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
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
      const body = await response.json();
      detail = Array.isArray(body.detail)
        ? body.detail.map((item) => item.msg).join("; ")
        : body.detail || body.message || "";
    } catch {
      // The response may not contain JSON.
    }
    throw new Error(
      detail || `The backend request failed (${response.status}).`,
    );
  }

  return response.json();
}

export const api = {
  getProjects(signal) {
    return request("/projects/", { signal });
  },
  getProjectProgress(projectId, signal) {
    return request(`/projects/${encodeURIComponent(projectId)}/progress`, { signal });
  },
  getSubmissionAnalyses(projectId, submissionId, signal) {
    return request(
      `/projects/${encodeURIComponent(projectId)}/submissions/${encodeURIComponent(submissionId)}/analysis`,
      { signal },
    );
  },
  login(credentials) {
    return request("/auth/login", { method: "POST", body: credentials });
  },
  registerFaculty(details) {
    return request("/auth/register/faculty", { method: "POST", body: details });
  },
  verifyOtp(details) {
    return request("/auth/otp/verify", { method: "POST", body: details });
  },
  resendOtp(details) {
    return request("/auth/otp/resend", { method: "POST", body: details });
  },
};

export { API_BASE_URL };
