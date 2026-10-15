import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App.jsx";

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Faculty Document Repository and Download Integration", () => {
  let fetchMock;

  beforeEach(() => {
    window.location.hash = "#submissions";
  });

  afterEach(() => {
    cleanup();
    window.location.hash = "";
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  async function loginAsFaculty() {
    render(<App />);
    fireEvent.change(screen.getByLabelText("Institutional email"), {
      target: { value: "supervisor@university.edu" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "password123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue to verification" }));
    await screen.findByLabelText("Six-digit verification code");
    fireEvent.change(screen.getByLabelText("Six-digit verification code"), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify email" }));
  }

  const sampleProject = {
    id: 1,
    title: "AI-Based Student Project Monitoring and Review Automation",
    description: "System for monitoring student project progress and milestone tracking.",
    status: "ACTIVE",
  };

  const sampleSubmissions = [
    {
      submission_id: 1,
      week_number: 2,
      status: "submitted",
      submitted_at: "2026-10-10T12:00:00Z",
      missing_documents: [],
      document_analyses: [],
    },
    {
      submission_id: 2,
      week_number: 4,
      status: "submitted",
      submitted_at: "2026-10-14T12:00:00Z",
      missing_documents: ["presentation"],
      document_analyses: [],
    },
  ];

  const sampleDocuments = [
    {
      submission_id: 1,
      week_number: 2,
      document_type: "report",
      document_id: "report",
      original_filename: "Sprint 2 Architecture Report.pdf",
      file_type: "pdf",
      file_size: 2048500,
      size_formatted: "2.0 MB",
      analysis_status: "complete",
      student_name: "Alice Smith & Bob Jones",
      submitted_at: "2026-10-10T12:00:00Z",
      download_url: "/api/projects/1/submissions/1/documents/report/download",
      preview_url: "/api/projects/1/submissions/1/documents/report/preview",
    },
    {
      submission_id: 1,
      week_number: 2,
      document_type: "presentation",
      document_id: "presentation",
      original_filename: "Midterm Evaluation Slides.pptx",
      file_type: "pptx",
      file_size: 4500000,
      size_formatted: "4.3 MB",
      analysis_status: "not_analyzed",
      student_name: "Alice Smith & Bob Jones",
      submitted_at: "2026-10-10T12:00:00Z",
      download_url: "/api/projects/1/submissions/1/documents/presentation/download",
      preview_url: "/api/projects/1/submissions/1/documents/presentation/preview",
    },
    {
      submission_id: 2,
      week_number: 4,
      document_type: "srs",
      document_id: "srs",
      original_filename: "Software Requirements Specification.docx",
      file_type: "docx",
      file_size: 1024000,
      size_formatted: "1.0 MB",
      analysis_status: "complete",
      student_name: "Alice Smith & Bob Jones",
      submitted_at: "2026-10-14T12:00:00Z",
      download_url: "/api/projects/1/submissions/2/documents/srs/download",
      preview_url: "/api/projects/1/submissions/2/documents/srs/preview",
    },
  ];

  it("renders the Submitted Documents repository with original filenames, sizes, badges, and actions", async () => {
    fetchMock = vi.fn(async (url) => {
      if (url === "/api/auth/login") return jsonResponse({ message: "Login code sent." }, 202);
      if (url === "/api/auth/otp/verify") {
        return jsonResponse({
          access_token: "faculty-jwt-token",
          account: { id: 1, role: "faculty", name: "Dr. Supervisor", email: "supervisor@university.edu" },
        });
      }
      if (url === "/api/projects/") return jsonResponse([sampleProject]);
      if (url === "/api/projects/1/progress") {
        return jsonResponse({
          project_id: 1,
          submissions: { total: 2, details: sampleSubmissions },
        });
      }
      if (url === "/api/projects/1/milestones") return jsonResponse([]);
      if (url === "/api/projects/1/members") return jsonResponse([]);
      if (url === "/api/projects/1/github/analysis") return jsonResponse(null);
      if (url === "/api/projects/1/ai-summary") return jsonResponse(null);
      if (url.startsWith("/api/projects/1/documents")) return jsonResponse(sampleDocuments);
      if (url.includes("/reviews")) return jsonResponse([]);
      if (url.includes("/document-analysis/")) return jsonResponse([]);
      if (url === "/api/students/") return jsonResponse([]);
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    await loginAsFaculty();

    // Verify Submitted Documents section is rendered
    expect(await screen.findByText("Submitted Documents")).toBeTruthy();
    expect(screen.getByTestId("submitted-docs-table")).toBeTruthy();

    // Verify all original filenames are rendered
    expect(screen.getByText("Sprint 2 Architecture Report.pdf")).toBeTruthy();
    expect(screen.getByText("Midterm Evaluation Slides.pptx")).toBeTruthy();
    expect(screen.getByText("Software Requirements Specification.docx")).toBeTruthy();

    // Verify formatted file sizes are rendered
    expect(screen.getByText("2.0 MB")).toBeTruthy();
    expect(screen.getByText("4.3 MB")).toBeTruthy();
    expect(screen.getByText("1.0 MB")).toBeTruthy();

    // Verify team members are rendered
    expect(screen.getAllByText("Alice Smith & Bob Jones").length).toBeGreaterThan(0);
  });

  it("filters documents by selected submission", async () => {
    fetchMock = vi.fn(async (url) => {
      if (url === "/api/auth/login") return jsonResponse({ message: "Login code sent." }, 202);
      if (url === "/api/auth/otp/verify") {
        return jsonResponse({
          access_token: "faculty-jwt-token",
          account: { id: 1, role: "faculty", name: "Dr. Supervisor", email: "supervisor@university.edu" },
        });
      }
      if (url === "/api/projects/") return jsonResponse([sampleProject]);
      if (url === "/api/projects/1/progress") {
        return jsonResponse({
          project_id: 1,
          submissions: { total: 2, details: sampleSubmissions },
        });
      }
      if (url.startsWith("/api/projects/1/documents")) return jsonResponse(sampleDocuments);
      if (url === "/api/students/") return jsonResponse([]);
      return jsonResponse([]);
    });
    vi.stubGlobal("fetch", fetchMock);

    await loginAsFaculty();
    await screen.findByText("Sprint 2 Architecture Report.pdf");

    // Change filter to Submission #2
    const filterSelect = screen.getByLabelText("Filter Submission:");
    fireEvent.change(filterSelect, { target: { value: "2" } });

    // Submission 2 only has the DOCX document
    expect(screen.getByText("Software Requirements Specification.docx")).toBeTruthy();
    expect(screen.queryByText("Sprint 2 Architecture Report.pdf")).toBeNull();
    expect(screen.queryByText("Midterm Evaluation Slides.pptx")).toBeNull();
  });

  it("handles preview for non-PDF files by displaying friendly browser preview unavailable message", async () => {
    fetchMock = vi.fn(async (url) => {
      if (url === "/api/auth/login") return jsonResponse({ message: "Login code sent." }, 202);
      if (url === "/api/auth/otp/verify") {
        return jsonResponse({
          access_token: "faculty-jwt-token",
          account: { id: 1, role: "faculty", name: "Dr. Supervisor", email: "supervisor@university.edu" },
        });
      }
      if (url === "/api/projects/") return jsonResponse([sampleProject]);
      if (url === "/api/projects/1/progress") {
        return jsonResponse({
          project_id: 1,
          submissions: { total: 2, details: sampleSubmissions },
        });
      }
      if (url.startsWith("/api/projects/1/documents")) return jsonResponse(sampleDocuments);
      if (url === "/api/students/") return jsonResponse([]);
      return jsonResponse([]);
    });
    vi.stubGlobal("fetch", fetchMock);

    await loginAsFaculty();
    await screen.findByText("Midterm Evaluation Slides.pptx");

    // Find row for PPTX and click View
    const pptxRow = screen.getByTestId("doc-row-1-presentation");
    const viewBtn = pptxRow.querySelector("button");
    fireEvent.click(viewBtn);

    // Modal pops up with clear unsupported message
    expect(await screen.findByTestId("preview-unsupported-message")).toBeTruthy();
    expect(screen.getByText("Browser Preview Unavailable")).toBeTruthy();
    expect(screen.getByText(/Preview unavailable for this file type\. Download to open the original document\./)).toBeTruthy();
  });

  it("shows empty state when no files exist for a project or submission", async () => {
    fetchMock = vi.fn(async (url) => {
      if (url === "/api/auth/login") return jsonResponse({ message: "Login code sent." }, 202);
      if (url === "/api/auth/otp/verify") {
        return jsonResponse({
          access_token: "faculty-jwt-token",
          account: { id: 1, role: "faculty", name: "Dr. Supervisor", email: "supervisor@university.edu" },
        });
      }
      if (url === "/api/projects/") return jsonResponse([sampleProject]);
      if (url === "/api/projects/1/progress") {
        return jsonResponse({
          project_id: 1,
          submissions: { total: 0, details: [] },
        });
      }
      if (url.startsWith("/api/projects/1/documents")) return jsonResponse([]);
      if (url === "/api/students/") return jsonResponse([]);
      return jsonResponse([]);
    });
    vi.stubGlobal("fetch", fetchMock);

    await loginAsFaculty();

    expect(await screen.findByTestId("submitted-docs-empty")).toBeTruthy();
    expect(screen.getByText("No submitted files available")).toBeTruthy();
  });
});
