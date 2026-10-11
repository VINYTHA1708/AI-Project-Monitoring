import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App.jsx";

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Student and Faculty Portals Core User Flows", () => {
  let fetchMock;

  beforeEach(() => {
    window.location.hash = "#dashboard";
  });

  afterEach(() => {
    cleanup();
    window.location.hash = "";
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("completes student registration, login, and displays student portal workspace", async () => {
    fetchMock = vi.fn(async (url, options) => {
      if (url === "/api/auth/register/student") {
        const body = JSON.parse(options.body);
        expect(body.email).toBe("student@university.edu");
        expect(body.registration_number).toBe("REG-2024");
        return jsonResponse({ message: "Verification sent." }, 202);
      }
      if (url === "/api/auth/otp/verify") {
        const body = JSON.parse(options.body);
        if (body.purpose === "registration") {
          return jsonResponse({ message: "Email verified." }, 200);
        }
        return jsonResponse({
          message: "Authenticated.",
          access_token: "student-token-abc",
          account: {
            id: 2, role: "student", name: "Alice Student",
            email: "student@university.edu", student_id: 10, department: "Computer Science",
          },
        });
      }
      if (url === "/api/auth/login") {
        return jsonResponse({ message: "Login code sent." }, 202);
      }
      if (url === "/api/projects/") {
        expect(options.headers.Authorization).toBe("Bearer student-token-abc");
        return jsonResponse([
          { id: 1, title: "Autonomous Robot", description: "Robotics system", status: "ACTIVE" },
        ]);
      }
      if (url === "/api/projects/1/progress") {
        return jsonResponse({
          project_id: 1, project_title: "Autonomous Robot", overall_status: "ACTIVE",
          milestones: { total: 2, completed: 1, pending: 1, completion_percentage: 50.0, overdue: [] },
          submissions: {
            total: 1, weeks_submitted: [1],
            details: [{ submission_id: 1, week_number: 1, status: "SUBMITTED", missing_documents: [], document_analyses: [{ submission_id: 1, document_type: "report", status: "complete", completeness_percentage: 95.0, missing_sections: [], detected_sections: ["Abstract", "Introduction"], warnings: [], extraction_errors: [] }], submitted_at: "2026-10-10T12:00:00Z" }],
          },
        });
      }
      if (url === "/api/projects/1/milestones/") {
        return jsonResponse([
          { id: 1, project_id: 1, title: "Design Architecture", due_date: "2026-11-01", completed: true, status: "COMPLETED" },
          { id: 2, project_id: 1, title: "Prototype Implementation", due_date: "2026-12-01", completed: false, status: "PENDING" },
        ]);
      }
      if (url === "/api/projects/1/members/") return jsonResponse([{ id: 1, project_id: 1, student_id: 10, role: "MEMBER" }]);
      if (url === "/api/projects/1/submissions/1/analysis") {
        return jsonResponse([{ id: 1, submission_id: 1, document_type: "report", analysis_status: "complete", completeness_percentage: 95.0, detected_sections: ["Abstract", "Introduction"], missing_sections: [], warnings: [], extraction_errors: [], analyzed_at: "2026-10-10T12:05:00Z" }]);
      }
      if (url === "/api/projects/1/submissions/1/reviews/") return jsonResponse([]);
      if (url === "/api/projects/1/github/analysis") return jsonResponse(null, 404);
      if (url === "/api/projects/1/ai-summary/") return jsonResponse({ provider_configured: false });
      throw new Error(`Unexpected request to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    // Switch to Register
    fireEvent.click(screen.getByRole("button", { name: "Register" }));

    // Switch to Student Registration tab
    fireEvent.click(screen.getByRole("button", { name: "Student Registration" }));

    expect(screen.getByRole("heading", { name: "Create student account" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Alice Student" } });
    fireEvent.change(screen.getByLabelText("Registration number"), { target: { value: "REG-2024" } });
    fireEvent.change(screen.getByLabelText("Department"), { target: { value: "Computer Science" } });
    fireEvent.change(screen.getByLabelText("Phone number"), { target: { value: "1234567890" } });
    fireEvent.change(screen.getByLabelText("Institutional email"), { target: { value: "student@university.edu" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "student-secure-password-123" } });

    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    // Registration OTP
    await screen.findByLabelText("Six-digit verification code");
    fireEvent.change(screen.getByLabelText("Six-digit verification code"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify email" }));

    // Sign in
    await screen.findByRole("heading", { name: "Welcome back" });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "student-secure-password-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue to verification" }));

    await screen.findByLabelText("Six-digit verification code");
    fireEvent.change(screen.getByLabelText("Six-digit verification code"), { target: { value: "654321" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify email" }));

    // Verify student portal branding & dashboard
    await screen.findByRole("heading", { name: "Dashboard" });
    // The portal label appears in brand copy (<small>) and page footer
    const portalLabels = screen.getAllByText("STUDENT PORTAL");
    expect(portalLabels.length).toBeGreaterThan(0);
    expect(screen.getByText("Autonomous Robot")).toBeTruthy();
    expect(screen.getByText("50%")).toBeTruthy();
  });

  it("student portal shows role-specific navigation items and not faculty-only items", async () => {
    fetchMock = vi.fn(async (url) => {
      if (url === "/api/auth/login") return jsonResponse({ message: "Login code sent." }, 202);
      if (url === "/api/auth/otp/verify") {
        return jsonResponse({
          access_token: "student-tok",
          account: { id: 2, role: "student", name: "Alice Student", email: "student@university.edu", student_id: 10 },
        });
      }
      if (url === "/api/projects/") return jsonResponse([]);
      throw new Error(`Unexpected: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.change(screen.getByLabelText("Institutional email"), { target: { value: "student@university.edu" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "student-password-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue to verification" }));
    await screen.findByLabelText("Six-digit verification code");
    fireEvent.change(screen.getByLabelText("Six-digit verification code"), { target: { value: "111111" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify email" }));

    // Wait for sidebar nav to appear
    await screen.findByText("My Projects");
    // Student portal should have student-specific nav items
    expect(screen.getByText("Team Members")).toBeTruthy();
    // Should NOT show faculty-only items
    expect(screen.queryByText("Assigned Projects")).toBeNull();
    expect(screen.queryByText("Project Monitoring")).toBeNull();
    expect(screen.queryByText("Faculty Profile")).toBeNull();
  });

  it("faculty portal shows role-specific navigation and not student-only items", async () => {
    fetchMock = vi.fn(async (url) => {
      if (url === "/api/auth/login") return jsonResponse({ message: "Login code sent." }, 202);
      if (url === "/api/auth/otp/verify") {
        return jsonResponse({
          access_token: "faculty-tok",
          account: { id: 1, role: "faculty", name: "Dr. Smith", email: "smith@university.edu", faculty_id: "F001" },
        });
      }
      if (url === "/api/projects/") return jsonResponse([]);
      if (url === "/api/students/") return jsonResponse([]);
      throw new Error(`Unexpected: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.change(screen.getByLabelText("Institutional email"), { target: { value: "smith@university.edu" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "faculty-password-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue to verification" }));
    await screen.findByLabelText("Six-digit verification code");
    fireEvent.change(screen.getByLabelText("Six-digit verification code"), { target: { value: "999999" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify email" }));

    // Wait for faculty-specific nav items
    await screen.findByRole("heading", { name: "Faculty Dashboard", level: 1 });
    expect(screen.getByRole("link", { name: /Assigned Projects/i })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Project Monitoring/i })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Faculty Profile/i })).toBeTruthy();
    // Should NOT show student-only items
    expect(screen.queryByText("Team Members")).toBeNull();
  });

  it("faculty dashboard shows 'no assigned projects' empty state when none assigned", async () => {
    fetchMock = vi.fn(async (url) => {
      if (url === "/api/auth/login") return jsonResponse({ message: "Login code sent." }, 202);
      if (url === "/api/auth/otp/verify") {
        return jsonResponse({
          access_token: "faculty-tok",
          account: { id: 1, role: "faculty", name: "Dr. Smith", email: "smith@university.edu" },
        });
      }
      if (url === "/api/projects/") return jsonResponse([]); // no assignments
      if (url === "/api/students/") return jsonResponse([]);
      throw new Error(`Unexpected: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.change(screen.getByLabelText("Institutional email"), { target: { value: "smith@university.edu" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "faculty-password-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue to verification" }));
    await screen.findByLabelText("Six-digit verification code");
    fireEvent.change(screen.getByLabelText("Six-digit verification code"), { target: { value: "888888" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify email" }));

    // Faculty-specific empty state message for no assignments
    const emptyMsg = await screen.findByText(/No assigned projects/i);
    expect(emptyMsg).toBeTruthy();
    // Should reference the provisioning CLI
    expect(screen.getByText(/provisioning CLI/i)).toBeTruthy();
  });

  it("supports student submission uploading", async () => {
    let uploadFormData = null;
    fetchMock = vi.fn(async (url, options) => {
      if (url === "/api/auth/login") return jsonResponse({ message: "Login code sent." }, 202);
      if (url === "/api/auth/otp/verify") {
        return jsonResponse({
          access_token: "student-token-upload",
          account: { id: 2, role: "student", name: "Alice Student", email: "student@university.edu", student_id: 10 },
        });
      }
      if (url === "/api/projects/") return jsonResponse([{ id: 1, title: "Autonomous Robot", description: "Robotics system", status: "ACTIVE" }]);
      if (url === "/api/projects/1/progress") {
        return jsonResponse({
          project_id: 1, project_title: "Autonomous Robot", overall_status: "ACTIVE",
          milestones: { total: 1, completed: 0, pending: 1, completion_percentage: 0 },
          submissions: { total: 0, weeks_submitted: [], details: [] },
        });
      }
      if (url === "/api/projects/1/milestones/") return jsonResponse([]);
      if (url === "/api/projects/1/members/") return jsonResponse([]);
      if (url === "/api/projects/1/github/analysis") return jsonResponse(null, 404);
      if (url === "/api/projects/1/ai-summary/") return jsonResponse({ provider_configured: false });
      if (url === "/api/projects/1/submissions/upload") {
        expect(options.method).toBe("POST");
        uploadFormData = options.body;
        return jsonResponse({ message: "Submission uploaded and recorded successfully", submission_id: 1, project_id: 1, week_number: 2, report_uploaded: true, status: "SUBMITTED" }, 201);
      }
      throw new Error(`Unexpected request to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    window.location.hash = "#submissions";
    render(<App />);

    fireEvent.change(screen.getByLabelText("Institutional email"), { target: { value: "student@university.edu" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "student-password-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue to verification" }));

    await screen.findByLabelText("Six-digit verification code");
    fireEvent.change(screen.getByLabelText("Six-digit verification code"), { target: { value: "111111" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify email" }));

    await screen.findByRole("heading", { name: "Submissions & Uploads" });

    const weekInput = screen.getByLabelText("Submission Week (1 - 52) *");
    fireEvent.change(weekInput, { target: { value: "2" } });

    const fakePdf = new File(["%PDF-1.4 sample content"], "report.pdf", { type: "application/pdf" });
    const fileInputs = screen.getAllByLabelText(/Report Document/i);
    fireEvent.change(fileInputs[0], { target: { files: [fakePdf] } });

    fireEvent.click(screen.getByRole("button", { name: "Submit Documents" }));

    await waitFor(() => {
      expect(uploadFormData).not.toBeNull();
      expect(uploadFormData instanceof FormData).toBe(true);
    });
  });

  it("supports faculty project creation and milestone creation", async () => {
    let createdProjectPayload = null;
    let createdMilestonePayload = null;

    fetchMock = vi.fn(async (url, options) => {
      if (url === "/api/auth/login") return jsonResponse({ message: "Login code sent." }, 202);
      if (url === "/api/auth/otp/verify") {
        return jsonResponse({
          access_token: "faculty-token-xyz",
          account: { id: 1, role: "faculty", name: "Dr. Smith", email: "smith@university.edu" },
        });
      }
      if (url === "/api/projects/" && options.method === "POST") {
        createdProjectPayload = JSON.parse(options.body);
        return jsonResponse({ id: 5, title: createdProjectPayload.title, status: "ACTIVE" }, 201);
      }
      if (url === "/api/projects/") {
        return jsonResponse(createdProjectPayload ? [{ id: 5, title: createdProjectPayload.title, status: "ACTIVE" }] : []);
      }
      if (url === "/api/students/") return jsonResponse([]);
      if (url === "/api/projects/5/progress") {
        return jsonResponse({
          project_id: 5, project_title: "New AI Project",
          milestones: { total: 0, completed: 0, pending: 0, completion_percentage: 0 },
          submissions: { total: 0, details: [] },
        });
      }
      if (url === "/api/projects/5/milestones/" && options?.method === "POST") {
        createdMilestonePayload = JSON.parse(options.body);
        return jsonResponse({ id: 1, project_id: 5, title: createdMilestonePayload.title, completed: false, status: "PENDING" }, 201);
      }
      if (url === "/api/projects/5/milestones/") {
        return jsonResponse(createdMilestonePayload ? [{ id: 1, project_id: 5, title: createdMilestonePayload.title, due_date: "2026-11-15", completed: false, status: "PENDING" }] : []);
      }
      if (url === "/api/projects/5/members/") return jsonResponse([]);
      if (url === "/api/projects/5/github/analysis") return jsonResponse(null, 404);
      if (url === "/api/projects/5/ai-summary/") return jsonResponse({ provider_configured: false });
      throw new Error(`Unexpected request to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    window.location.hash = "#projects";
    render(<App />);

    fireEvent.change(screen.getByLabelText("Institutional email"), { target: { value: "smith@university.edu" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "faculty-password-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue to verification" }));

    await screen.findByLabelText("Six-digit verification code");
    fireEvent.change(screen.getByLabelText("Six-digit verification code"), { target: { value: "999999" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify email" }));

    await screen.findByRole("heading", { name: "Project Supervision Workspace" });

    // Open project creation form
    fireEvent.click(screen.getByRole("button", { name: /Create & Assign Project/i }));
    fireEvent.change(screen.getByLabelText("Project Title *"), { target: { value: "New AI Project" } });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Supervised AI System" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Project" }));

    await waitFor(() => {
      expect(createdProjectPayload).toEqual(expect.objectContaining({ title: "New AI Project" }));
    });

    // Navigate to Milestones
    window.location.hash = "#milestones";
    window.dispatchEvent(new Event("hashchange"));

    await screen.findByRole("heading", { name: "Milestone Checklist" });
    fireEvent.click(screen.getByRole("button", { name: /Add Milestone/i }));

    fireEvent.change(screen.getByLabelText("Milestone Title *"), { target: { value: "Draft SRS Documentation" } });
    fireEvent.change(screen.getByLabelText("Due Date *"), { target: { value: "2026-11-15" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Milestone" }));

    await waitFor(() => {
      expect(createdMilestonePayload).toEqual(expect.objectContaining({ title: "Draft SRS Documentation" }));
    });
  });
});
