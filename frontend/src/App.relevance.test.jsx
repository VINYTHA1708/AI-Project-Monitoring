import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App.jsx";

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("AI Summary Project-Relevance Frontend Display", () => {
  let fetchMock;

  beforeEach(() => {
    window.location.hash = "#ai-summary";
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

  it("renders NOT_RELEVANT banner with project-topic mismatch warning, comparison grid, and slide citations", async () => {
    fetchMock = vi.fn(async (url) => {
      if (url === "/api/auth/login") return jsonResponse({ message: "Login code sent." }, 202);
      if (url === "/api/auth/otp/verify") {
        return jsonResponse({
          access_token: "faculty-jwt-token",
          account: { id: 1, role: "faculty", name: "Dr. Supervisor", email: "supervisor@university.edu" },
        });
      }
      if (url === "/api/projects/") {
        return jsonResponse([
          {
            id: 1,
            title: "AI-Based Student Project Monitoring and Review Automation",
            description: "System for monitoring student project progress and milestone tracking.",
            status: "ACTIVE",
          },
        ]);
      }
      if (url === "/api/students/") return jsonResponse([]);
      if (url === "/api/projects/1/progress") {
        return jsonResponse({
          project_id: 1,
          project_title: "AI-Based Student Project Monitoring and Review Automation",
          overall_status: "ACTIVE",
          milestones: { total: 2, completed: 0, pending: 2, completion_percentage: 0.0, overdue: [] },
          submissions: { total: 1, weeks_submitted: [1], details: [] },
        });
      }
      if (url === "/api/projects/1/milestones/") return jsonResponse([]);
      if (url === "/api/projects/1/members/") return jsonResponse([]);
      if (url === "/api/projects/1/github/analysis") return jsonResponse(null, 404);
      if (url === "/api/projects/1/ai-summary/") {
        return jsonResponse({
          provider_configured: true,
          latest_summary: {
            id: 101,
            project_id: 1,
            provider: "groq",
            model_name: "llama-3.3-70b-versatile",
            created_at: "2026-10-15T00:00:00Z",
            document_relevance: "NOT_RELEVANT",
            detected_document_topic: "Sensor Data Compression Using Lossless Algorithms",
            assigned_project_topic: "AI-Based Student Project Monitoring and Review Automation",
            relevance_explanation: "The uploaded presentation focuses entirely on IoT sensor data compression techniques and lossless encoding algorithms. It contains no discussion or implementation of project monitoring, milestone evaluation, or student review workflows.",
            progress_assessment: "No verified progress on the assigned project 'AI-Based Student Project Monitoring and Review Automation' can be confirmed from this document.",
            supporting_evidence: [
              "[Slide 1] Sensor Data Compression Using Lossless Algorithms",
              "[Slide 3] Lossless compression benchmarks for embedded IoT sensors",
            ],
            relevant_findings: [],
            missing_evidence: [
              "Zero artifacts or architecture related to project monitoring and review automation.",
            ],
            confidence: 0.98,
            summary_text: "The uploaded presentation covers sensor data compression instead of the assigned project.",
            risks: ["Irrelevant document submitted as progress evidence."],
            recommended_next_steps: ["Require student team to resubmit presentation covering project monitoring."],
            review_questions: ["Why does this presentation discuss sensor data compression instead of project monitoring?"],
            advisory_disclaimer: "Advisory only.",
          },
        });
      }
      throw new Error(`Unexpected request to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    await loginAsFaculty();

    // Verify AI Summary tab heading
    await screen.findByRole("heading", { name: "AI Project Summary & Synthesis", level: 2 });

    // Assert Mismatch Banner is rendered
    const banner = screen.getByTestId("relevance-banner");
    expect(banner).toBeTruthy();
    expect(banner.className).toContain("relevance-callout-mismatch");

    // Assert Mismatch text
    expect(
      screen.getByText(
        "Project-topic mismatch detected. This document appears to discuss a different topic and should not be treated as evidence of progress on the assigned project."
      )
    ).toBeTruthy();

    // Assert Badge
    expect(screen.getByText("NOT RELEVANT")).toBeTruthy();

    // Assert Comparison Grid
    expect(screen.getByText("AI-Based Student Project Monitoring and Review Automation")).toBeTruthy();
    expect(screen.getByText("Sensor Data Compression Using Lossless Algorithms")).toBeTruthy();

    // Assert Citations
    expect(
      screen.getByText("[Slide 1] Sensor Data Compression Using Lossless Algorithms")
    ).toBeTruthy();
    expect(
      screen.getByText("[Slide 3] Lossless compression benchmarks for embedded IoT sensors")
    ).toBeTruthy();

    // Assert Missing Evidence
    expect(
      screen.getByText("Zero artifacts or architecture related to project monitoring and review automation.")
    ).toBeTruthy();

    // Assert Confidence estimate
    expect(screen.getByText(/98%/)).toBeTruthy();
  });

  it("renders RELEVANT banner when document matches assigned project", async () => {
    fetchMock = vi.fn(async (url) => {
      if (url === "/api/auth/login") return jsonResponse({ message: "Login code sent." }, 202);
      if (url === "/api/auth/otp/verify") {
        return jsonResponse({
          access_token: "faculty-jwt-token",
          account: { id: 1, role: "faculty", name: "Dr. Supervisor", email: "supervisor@university.edu" },
        });
      }
      if (url === "/api/projects/") {
        return jsonResponse([
          {
            id: 1,
            title: "AI-Based Student Project Monitoring and Review Automation",
            description: "System for monitoring student project progress and milestone tracking.",
            status: "ACTIVE",
          },
        ]);
      }
      if (url === "/api/students/") return jsonResponse([]);
      if (url === "/api/projects/1/progress") {
        return jsonResponse({
          project_id: 1,
          project_title: "AI-Based Student Project Monitoring and Review Automation",
          overall_status: "ACTIVE",
          milestones: { total: 2, completed: 1, pending: 1, completion_percentage: 50.0, overdue: [] },
          submissions: { total: 1, weeks_submitted: [1], details: [] },
        });
      }
      if (url === "/api/projects/1/milestones/") return jsonResponse([]);
      if (url === "/api/projects/1/members/") return jsonResponse([]);
      if (url === "/api/projects/1/github/analysis") return jsonResponse(null, 404);
      if (url === "/api/projects/1/ai-summary/") {
        return jsonResponse({
          provider_configured: true,
          latest_summary: {
            id: 102,
            project_id: 1,
            provider: "groq",
            model_name: "llama-3.3-70b-versatile",
            created_at: "2026-10-15T00:00:00Z",
            document_relevance: "RELEVANT",
            detected_document_topic: "AI-Based Student Project Monitoring and Review Automation",
            assigned_project_topic: "AI-Based Student Project Monitoring and Review Automation",
            relevance_explanation: "The presentation explicitly details architecture for student project monitoring, milestones, and review automation.",
            progress_assessment: "Demonstrates substantive progress on FastAPI backend and dashboard modules.",
            supporting_evidence: [
              "[Slide 2] Architecture: FastAPI backend and React frontend dashboard for automated review workflows",
            ],
            relevant_findings: [
              "Designed backend schema for milestones, reviews, and document analyses.",
            ],
            missing_evidence: [],
            confidence: 0.95,
            summary_text: "Presentation aligns with the project objectives.",
            risks: [],
            recommended_next_steps: ["Complete end-to-end integration."],
            review_questions: ["What database migrations are pending?"],
            advisory_disclaimer: "Advisory only.",
          },
        });
      }
      throw new Error(`Unexpected request to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    await loginAsFaculty();

    // Verify RELEVANT banner
    const banner = await screen.findByTestId("relevance-banner");
    expect(banner.className).toContain("relevance-callout-relevant");
    expect(screen.getByText("Document verified as relevant to the assigned project.")).toBeTruthy();
    expect(screen.getByText("RELEVANT")).toBeTruthy();
    expect(screen.getByText("Demonstrates substantive progress on FastAPI backend and dashboard modules.")).toBeTruthy();
  });

  it("renders PARTIALLY_RELEVANT banner for partial topic overlap", async () => {
    fetchMock = vi.fn(async (url) => {
      if (url === "/api/auth/login") return jsonResponse({ message: "Login code sent." }, 202);
      if (url === "/api/auth/otp/verify") {
        return jsonResponse({
          access_token: "faculty-jwt-token",
          account: { id: 1, role: "faculty", name: "Dr. Supervisor", email: "supervisor@university.edu" },
        });
      }
      if (url === "/api/projects/") {
        return jsonResponse([
          {
            id: 1,
            title: "AI-Based Student Project Monitoring and Review Automation",
            description: "System for monitoring student project progress.",
            status: "ACTIVE",
          },
        ]);
      }
      if (url === "/api/students/") return jsonResponse([]);
      if (url === "/api/projects/1/progress") {
        return jsonResponse({
          project_id: 1,
          project_title: "AI-Based Student Project Monitoring and Review Automation",
          overall_status: "ACTIVE",
          milestones: { total: 1, completed: 0, pending: 1, completion_percentage: 0.0, overdue: [] },
          submissions: { total: 1, weeks_submitted: [1], details: [] },
        });
      }
      if (url === "/api/projects/1/milestones/") return jsonResponse([]);
      if (url === "/api/projects/1/members/") return jsonResponse([]);
      if (url === "/api/projects/1/github/analysis") return jsonResponse(null, 404);
      if (url === "/api/projects/1/ai-summary/") {
        return jsonResponse({
          provider_configured: true,
          latest_summary: {
            id: 103,
            project_id: 1,
            provider: "groq",
            model_name: "llama-3.3-70b-versatile",
            created_at: "2026-10-15T00:00:00Z",
            document_relevance: "PARTIALLY_RELEVANT",
            detected_document_topic: "General Educational Monitoring Framework",
            assigned_project_topic: "AI-Based Student Project Monitoring and Review Automation",
            relevance_explanation: "Includes general monitoring concepts but lacks student project review automation details.",
            progress_assessment: "Preliminary conceptual alignment, but critical review features are absent.",
            supporting_evidence: [],
            relevant_findings: [],
            missing_evidence: ["Automated review pipeline details."],
            confidence: 0.75,
            summary_text: "General monitoring concepts presented.",
            risks: [],
            recommended_next_steps: [],
            review_questions: [],
            advisory_disclaimer: "Advisory only.",
          },
        });
      }
      throw new Error(`Unexpected request to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    await loginAsFaculty();

    const banner = await screen.findByTestId("relevance-banner");
    expect(banner.className).toContain("relevance-callout-partial");
    expect(
      screen.getByText(
        "Partial project-topic match detected. Some content relates to the assigned project, but significant sections appear unrelated."
      )
    ).toBeTruthy();
    expect(screen.getByText("PARTIALLY RELEVANT")).toBeTruthy();
  });

  it("renders INSUFFICIENT_CONTENT banner when document lacks meaningful text", async () => {
    fetchMock = vi.fn(async (url) => {
      if (url === "/api/auth/login") return jsonResponse({ message: "Login code sent." }, 202);
      if (url === "/api/auth/otp/verify") {
        return jsonResponse({
          access_token: "faculty-jwt-token",
          account: { id: 1, role: "faculty", name: "Dr. Supervisor", email: "supervisor@university.edu" },
        });
      }
      if (url === "/api/projects/") {
        return jsonResponse([
          {
            id: 1,
            title: "AI-Based Student Project Monitoring and Review Automation",
            description: "System for monitoring student project progress.",
            status: "ACTIVE",
          },
        ]);
      }
      if (url === "/api/students/") return jsonResponse([]);
      if (url === "/api/projects/1/progress") {
        return jsonResponse({
          project_id: 1,
          project_title: "AI-Based Student Project Monitoring and Review Automation",
          overall_status: "ACTIVE",
          milestones: { total: 1, completed: 0, pending: 1, completion_percentage: 0.0, overdue: [] },
          submissions: { total: 1, weeks_submitted: [1], details: [] },
        });
      }
      if (url === "/api/projects/1/milestones/") return jsonResponse([]);
      if (url === "/api/projects/1/members/") return jsonResponse([]);
      if (url === "/api/projects/1/github/analysis") return jsonResponse(null, 404);
      if (url === "/api/projects/1/ai-summary/") {
        return jsonResponse({
          provider_configured: true,
          latest_summary: {
            id: 104,
            project_id: 1,
            provider: "groq",
            model_name: "llama-3.3-70b-versatile",
            created_at: "2026-10-15T00:00:00Z",
            document_relevance: "INSUFFICIENT_CONTENT",
            detected_document_topic: "Unknown",
            assigned_project_topic: "AI-Based Student Project Monitoring and Review Automation",
            relevance_explanation: "Document contained insufficient readable text to establish topical relevance.",
            progress_assessment: "Cannot evaluate progress due to lack of readable content.",
            supporting_evidence: [],
            relevant_findings: [],
            missing_evidence: ["Sufficient readable text in submitted documents."],
            confidence: 0.0,
            summary_text: "Insufficient content extracted.",
            risks: [],
            recommended_next_steps: ["Ensure uploaded slides contain selectable text."],
            review_questions: [],
            advisory_disclaimer: "Advisory only.",
          },
        });
      }
      throw new Error(`Unexpected request to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    await loginAsFaculty();

    const banner = await screen.findByTestId("relevance-banner");
    expect(banner.className).toContain("relevance-callout-insufficient");
    expect(
      screen.getByText("Insufficient document content for reliable relevance determination.")
    ).toBeTruthy();
    expect(screen.getByText("INSUFFICIENT CONTENT")).toBeTruthy();
  });

  it("handles switching between two projects without leaking stale summary state", async () => {
    fetchMock = vi.fn(async (url) => {
      if (url === "/api/auth/login") return jsonResponse({ message: "Login code sent." }, 202);
      if (url === "/api/auth/otp/verify") {
        return jsonResponse({
          access_token: "faculty-jwt-token",
          account: { id: 1, role: "faculty", name: "Dr. Supervisor", email: "supervisor@university.edu" },
        });
      }
      if (url === "/api/projects/") {
        return jsonResponse([
          {
            id: 1,
            title: "AI-Based Student Project Monitoring and Review Automation",
            description: "System for monitoring student project progress.",
            status: "ACTIVE",
          },
          {
            id: 2,
            title: "Acoustic Fingerprinting using Machine Learning Algorithm",
            description: "Industrial audio ML classifier.",
            status: "ACTIVE",
          },
        ]);
      }
      if (url === "/api/students/") return jsonResponse([]);
      if (url === "/api/projects/1/progress" || url === "/api/projects/2/progress") {
        const pid = url.includes("/1/") ? 1 : 2;
        return jsonResponse({
          project_id: pid,
          project_title: pid === 1 ? "AI-Based Student Project Monitoring" : "Acoustic Fingerprinting",
          overall_status: "ACTIVE",
          milestones: { total: 1, completed: 0, pending: 1, completion_percentage: 0.0, overdue: [] },
          submissions: { total: 0, weeks_submitted: [], details: [] },
        });
      }
      if (url.includes("/milestones/") || url.includes("/members/")) return jsonResponse([]);
      if (url.includes("/github/analysis")) return jsonResponse(null, 404);
      if (url === "/api/projects/1/ai-summary/") {
        return jsonResponse({
          provider_configured: true,
          latest_summary: {
            id: 201,
            project_id: 1,
            provider: "groq",
            model_name: "llama-3.3-70b-versatile",
            created_at: "2026-10-15T00:00:00Z",
            document_relevance: "RELEVANT",
            detected_document_topic: "AI-Based Student Project Monitoring and Review Automation",
            assigned_project_topic: "AI-Based Student Project Monitoring and Review Automation",
            relevance_explanation: "Project 1 evidence is strictly aligned.",
            progress_assessment: "Substantive progress on Project 1 monitoring modules.",
            supporting_evidence: ["[Slide 1] Project 1 Monitoring Architecture"],
            relevant_findings: ["Prototyped Project 1 review workflows"],
            missing_evidence: [],
            confidence: 0.96,
            summary_text: "Grounded summary for Project 1 monitoring only.",
            risks: [],
            recommended_next_steps: [],
            review_questions: [],
            advisory_disclaimer: "Advisory only.",
          },
        });
      }
      if (url === "/api/projects/2/ai-summary/") {
        return jsonResponse({
          provider_configured: true,
          latest_summary: {
            id: 202,
            project_id: 2,
            provider: "groq",
            model_name: "llama-3.3-70b-versatile",
            created_at: "2026-10-15T00:00:00Z",
            document_relevance: "RELEVANT",
            detected_document_topic: "Acoustic Fingerprinting using Machine Learning Algorithm",
            assigned_project_topic: "Acoustic Fingerprinting using Machine Learning Algorithm",
            relevance_explanation: "Project 2 evidence strictly matches audio classification.",
            progress_assessment: "Substantive progress on audio spectrogram feature extraction.",
            supporting_evidence: ["[Slide 1] Acoustic Spectrogram Analysis"],
            relevant_findings: ["Trained CNN audio classifier with 92% accuracy"],
            missing_evidence: [],
            confidence: 0.94,
            summary_text: "Grounded summary for Project 2 acoustic fingerprinting only.",
            risks: [],
            recommended_next_steps: [],
            review_questions: [],
            advisory_disclaimer: "Advisory only.",
          },
        });
      }
      throw new Error(`Unexpected request to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    await loginAsFaculty();

    // Verify Project 1 summary initially displayed
    expect(await screen.findByText("Grounded summary for Project 1 monitoring only.")).toBeTruthy();
    expect(screen.queryByText("Grounded summary for Project 2 acoustic fingerprinting only.")).toBeNull();

    // Switch to Project 2 in dropdown
    const select = screen.getByLabelText("Select a project");
    fireEvent.change(select, { target: { value: "2" } });

    // Verify Project 2 summary displayed and Project 1 content is no longer present
    expect(await screen.findByText("Grounded summary for Project 2 acoustic fingerprinting only.")).toBeTruthy();
    expect(screen.queryByText("Grounded summary for Project 1 monitoring only.")).toBeNull();
  });

  it("gracefully handles legacy AI summary record missing document_relevance fields", async () => {
    fetchMock = vi.fn(async (url) => {
      if (url === "/api/auth/login") return jsonResponse({ message: "Login code sent." }, 202);
      if (url === "/api/auth/otp/verify") {
        return jsonResponse({
          access_token: "faculty-jwt-token",
          account: { id: 1, role: "faculty", name: "Dr. Supervisor", email: "supervisor@university.edu" },
        });
      }
      if (url === "/api/projects/") {
        return jsonResponse([
          {
            id: 1,
            title: "AI-Based Student Project Monitoring",
            description: "System for monitoring student project progress.",
            status: "ACTIVE",
          },
        ]);
      }
      if (url === "/api/students/") return jsonResponse([]);
      if (url === "/api/projects/1/progress") {
        return jsonResponse({
          project_id: 1,
          project_title: "AI-Based Student Project Monitoring",
          overall_status: "ACTIVE",
          milestones: { total: 1, completed: 0, pending: 1, completion_percentage: 0.0, overdue: [] },
          submissions: { total: 0, weeks_submitted: [], details: [] },
        });
      }
      if (url.includes("/milestones/") || url.includes("/members/")) return jsonResponse([]);
      if (url.includes("/github/analysis")) return jsonResponse(null, 404);
      if (url === "/api/projects/1/ai-summary/") {
        return jsonResponse({
          provider_configured: true,
          latest_summary: {
            id: 99,
            project_id: 1,
            provider: "groq",
            model_name: "llama-3.3-70b-versatile",
            created_at: "2026-10-14T00:00:00Z",
            // Legacy record without relevance fields:
            document_relevance: null,
            detected_document_topic: null,
            assigned_project_topic: null,
            relevance_explanation: null,
            progress_assessment: null,
            supporting_evidence: [],
            relevant_findings: null,
            key_points: ["Legacy key point"],
            missing_evidence: [],
            confidence: null,
            summary_text: "Legacy executive summary from previous schema version.",
            risks: [],
            recommended_next_steps: [],
            review_questions: [],
            advisory_disclaimer: "Advisory notice.",
          },
        });
      }
      throw new Error(`Unexpected request to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    await loginAsFaculty();

    // Verify executive summary renders safely
    expect(await screen.findByText("Legacy executive summary from previous schema version.")).toBeTruthy();
    // Key points used as fallback for relevant_findings
    expect(screen.getByText("Legacy key point")).toBeTruthy();
    // No crash and relevance banner is omitted cleanly
    expect(screen.queryByTestId("relevance-banner")).toBeNull();
  });

  it("renders NOT_RELEVANT empty state without contradictory text or raw JSON", async () => {
    fetchMock = vi.fn(async (url) => {
      if (url === "/api/auth/login") return jsonResponse({ message: "Login code sent." }, 202);
      if (url === "/api/auth/otp/verify") {
        return jsonResponse({
          access_token: "faculty-jwt-token",
          account: { id: 1, role: "faculty", name: "Dr. Supervisor", email: "supervisor@university.edu" },
        });
      }
      if (url === "/api/projects/") {
        return jsonResponse([
          {
            id: 1,
            title: "AI-Based Student Project Monitoring",
            description: "System for monitoring student project progress.",
            status: "ACTIVE",
          },
        ]);
      }
      if (url === "/api/students/") return jsonResponse([]);
      if (url === "/api/projects/1/progress") {
        return jsonResponse({
          project_id: 1,
          project_title: "AI-Based Student Project Monitoring",
          overall_status: "ACTIVE",
          milestones: { total: 1, completed: 0, pending: 1, completion_percentage: 0.0, overdue: [] },
          submissions: { total: 1, weeks_submitted: [1], details: [] },
        });
      }
      if (url.includes("/milestones/") || url.includes("/members/")) return jsonResponse([]);
      if (url.includes("/github/analysis")) return jsonResponse(null, 404);
      if (url === "/api/projects/1/ai-summary/") {
        return jsonResponse({
          provider_configured: true,
          latest_summary: {
            id: 301,
            project_id: 1,
            provider: "groq",
            model_name: "llama-3.3-70b-versatile",
            created_at: "2026-10-15T00:00:00Z",
            document_relevance: "NOT_RELEVANT",
            detected_document_topic: "Sensor Data Compression Using Lossless Algorithms",
            assigned_project_topic: "AI-Based Student Project Monitoring",
            relevance_explanation: "Document discusses sensor data compression.",
            progress_assessment: "This document cannot be treated as valid evidence of project progress.",
            supporting_evidence: ["[Slide 1] Sensor Data Compression"],
            relevant_findings: [],
            missing_evidence: [],
            confidence: 0.99,
            summary_text: "Project-topic mismatch detected.",
            risks: [],
            recommended_next_steps: [],
            review_questions: [],
            advisory_disclaimer: "Advisory notice.",
          },
        });
      }
      throw new Error(`Unexpected request to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    await loginAsFaculty();

    expect(await screen.findByTestId("relevance-banner")).toBeTruthy();
    // Context-aware empty state in verified findings
    expect(
      screen.getByText("No relevant findings \u2014 the uploaded document is not related to this project.")
    ).toBeTruthy();
    // Clean empty state in other cards without raw JSON
    expect(screen.getByText("No specific missing evidence flagged.")).toBeTruthy();
    expect(screen.getByText("No elevated risks flagged.")).toBeTruthy();
    expect(screen.getByText("No immediate steps pending.")).toBeTruthy();
    expect(screen.queryByText(/relevant_findings:/i)).toBeNull();
    expect(screen.queryByText(/\[object Object\]/)).toBeNull();
  });

  it("renders multi-document verification status, mixed deliverable alert, metric pills, and individual deliverable cards", async () => {
    fetchMock = vi.fn(async (url) => {
      if (url === "/api/auth/login") return jsonResponse({ message: "Login code sent." }, 202);
      if (url === "/api/auth/otp/verify") {
        return jsonResponse({
          access_token: "faculty-jwt-token",
          account: { id: 1, role: "faculty", name: "Dr. Supervisor", email: "supervisor@university.edu" },
        });
      }
      if (url === "/api/projects/") {
        return jsonResponse([
          {
            id: 1,
            title: "Acoustic Fingerprinting using Machine Learning Algorithm",
            description: "Acoustic ML classifier.",
            status: "ACTIVE",
          },
        ]);
      }
      if (url === "/api/students/") return jsonResponse([]);
      if (url === "/api/projects/1/progress") {
        return jsonResponse({
          project_id: 1,
          project_title: "Acoustic Fingerprinting using Machine Learning Algorithm",
          overall_status: "ACTIVE",
          milestones: { total: 1, completed: 0, pending: 1, completion_percentage: 0.0, overdue: [] },
          submissions: { total: 1, weeks_submitted: [1], details: [] },
        });
      }
      if (url.includes("/milestones/") || url.includes("/members/")) return jsonResponse([]);
      if (url.includes("/github/analysis")) return jsonResponse(null, 404);
      if (url === "/api/projects/1/ai-summary/") {
        return jsonResponse({
          provider_configured: true,
          latest_summary: {
            id: 401,
            project_id: 1,
            provider: "groq",
            model_name: "llama-3.3-70b-versatile",
            created_at: "2026-10-15T00:00:00Z",
            document_relevance: "PARTIALLY_RELEVANT",
            detected_document_topic: "Mixed deliverables: Acoustic Audio vs Sensor Compression",
            assigned_project_topic: "Acoustic Fingerprinting using Machine Learning Algorithm",
            relevance_explanation: "Report matches acoustic ML fingerprinting. Presentation covers unrelated sensor data compression.",
            progress_assessment: "Progress verified only from report. Presentation is quarantined.",
            supporting_evidence: ["[Page 3] Acoustic Spectrogram Feature Extraction Pipeline"],
            relevant_findings: ["Acoustic spectrogram feature extractor implemented."],
            missing_evidence: ["A presentation corresponding to the acoustic fingerprinting project."],
            confidence: 0.95,
            summary_text: "Submission contains contradictory deliverables.",
            risks: ["Irrelevant presentation uploaded."],
            recommended_next_steps: ["Resubmit relevant PPT."],
            review_questions: ["Why was a sensor compression presentation submitted?"],
            advisory_disclaimer: "Advisory notice.",
            submission_verification_status: "CONTRADICTORY_TOPICS",
            relevant_documents_count: 1,
            partially_relevant_documents_count: 0,
            unrelated_documents_count: 1,
            insufficient_content_documents_count: 0,
            document_results: [
              {
                file_type: "pdf",
                file_name: "week_1_acoustic_report.pdf",
                document_title: "Acoustic Fingerprinting using Machine Learning",
                detected_topic: "Acoustic Fingerprinting ML",
                relevance: "RELEVANT",
                relevance_explanation: "Matches assigned audio classifier requirements.",
                title_comparison: "Title explicitly matches.",
                content_comparison: "Content details spectrogram generation and CNN models.",
                supporting_citations: ["[Page 3] Acoustic Spectrogram Feature Extraction Pipeline"],
                conflicting_evidence: [],
                recommended_action: "Credit progress from this report.",
                confidence: 0.98,
              },
              {
                file_type: "pptx",
                file_name: "sensor_compression_week1.pptx",
                document_title: "Sensor Data Compression Using Lossless Algorithms",
                detected_topic: "Sensor Data Compression",
                relevance: "NOT_RELEVANT",
                relevance_explanation: "Covers lossless sensor compression, completely unrelated to acoustic fingerprinting.",
                title_comparison: "Title describes sensor compression instead of acoustic fingerprinting.",
                content_comparison: "No audio classification or spectrogram content present.",
                supporting_citations: ["[Slide 1] Sensor Data Compression Algorithms"],
                conflicting_evidence: ["Lossless compression benchmarks for embedded IoT sensors"],
                recommended_action: "Quarantine this presentation and request resubmission.",
                confidence: 0.99,
              },
            ],
          },
        });
      }
      throw new Error(`Unexpected request to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    await loginAsFaculty();

    // Verify submission status bar
    expect(await screen.findByTestId("submission-status-bar")).toBeTruthy();
    expect(screen.getByText("CONTRADICTORY TOPICS")).toBeTruthy();

    // Verify metric pills
    expect(screen.getByText(/1 Relevant/)).toBeTruthy();
    expect(screen.getByText(/1 Unrelated/)).toBeTruthy();

    // Verify Mixed Deliverable Alert
    expect(screen.getByTestId("mixed-deliverable-alert")).toBeTruthy();
    expect(screen.getByText("Mixed Deliverable Alert: Contradictory Submission Topics")).toBeTruthy();

    // Verify Document Verification Section
    expect(screen.getByTestId("document-verification-section")).toBeTruthy();
    expect(screen.getByText("Independent Deliverable Verification (2 Documents)")).toBeTruthy();

    // Verify PDF card
    expect(screen.getByText("week_1_acoustic_report.pdf")).toBeTruthy();
    expect(screen.getByText("Acoustic Fingerprinting using Machine Learning")).toBeTruthy();
    expect(screen.getByText("Acoustic Fingerprinting ML")).toBeTruthy();
    expect(screen.getByText("Matches assigned audio classifier requirements.")).toBeTruthy();
    expect(screen.getAllByText("[Page 3] Acoustic Spectrogram Feature Extraction Pipeline").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Credit progress from this report.")).toBeTruthy();

    // Verify PPTX card
    expect(screen.getByText("sensor_compression_week1.pptx")).toBeTruthy();
    expect(screen.getByText("Sensor Data Compression Using Lossless Algorithms")).toBeTruthy();
    expect(screen.getByText("Sensor Data Compression")).toBeTruthy();
    expect(screen.getByText("Lossless compression benchmarks for embedded IoT sensors")).toBeTruthy();
    expect(screen.getByText("Quarantine this presentation and request resubmission.")).toBeTruthy();
  });
});


