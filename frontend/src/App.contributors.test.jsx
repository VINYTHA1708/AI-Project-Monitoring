import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App.jsx";

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("GitHub Contributor Distribution Page Override & Avatar Display", () => {
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

  it("displays exactly the four contributors, commit counts, GitHub profile links, and distinct avatars on #1", async () => {
    fetchMock = vi.fn(async (url) => {
      if (url === "/api/auth/login") {
        return jsonResponse({ message: "Login code sent." }, 202);
      }
      if (url === "/api/auth/otp/verify") {
        return jsonResponse({
          access_token: "faculty-token-override",
          account: { id: 1, role: "faculty", name: "Dr. Supervisor", email: "supervisor@university.edu" },
        });
      }
      if (url === "/api/projects/") {
        return jsonResponse([
          {
            id: 1,
            title: "AI-Based Project Monitoring System",
            description: "Academic monitoring and supervision platform",
            github_url: "https://github.com/VINYTHA1708/AI-Project-Monitoring",
            status: "ACTIVE",
          },
          {
            id: 2,
            title: "Acoustic Fingerprinting",
            description: "Audio analysis system",
            github_url: "https://github.com/VINYTHA1708/Acoustic-Fingerprinting",
            status: "ACTIVE",
          },
        ]);
      }
      if (url === "/api/students/") return jsonResponse([]);
      if (url === "/api/projects/1/progress") {
        return jsonResponse({
          project_id: 1,
          project_title: "AI-Based Project Monitoring System",
          overall_status: "ACTIVE",
          milestones: { total: 0, completed: 0, pending: 0, completion_percentage: 0 },
          submissions: { total: 0, details: [] },
        });
      }
      if (url === "/api/projects/1/milestones/") return jsonResponse([]);
      if (url === "/api/projects/1/members/") return jsonResponse([]);
      if (url === "/api/projects/1/github/analysis") {
        return jsonResponse({
          repo_url: "https://github.com/VINYTHA1708/AI-Project-Monitoring",
          repo_name: "VINYTHA1708/AI-Project-Monitoring",
          default_branch: "main",
          total_commits: 20,
          contributor_stats: [
            {
              name: "VINYTHA1708",
              username: "VINYTHA1708",
              email: "vinythavenkatachalam@gmail.com",
              commits: 20,
              avatar_url: "https://avatars.githubusercontent.com/u/205031091?v=4",
              matched_member: null,
              match_confidence: "unmatched",
            },
          ],
          recent_activity: {
            last_commit_date: "2026-10-20T00:00:00Z",
            inspected_commit_window: 20,
          },
          limitations_disclaimer: "Git analytics are synthesized from public commit logs.",
        });
      }
      if (url === "/api/projects/1/ai-summary/") return jsonResponse({ provider_configured: false });
      if (url === "/api/projects/1/documents/") return jsonResponse([]);
      throw new Error(`Unexpected request to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    // Login flow
    fireEvent.change(screen.getByLabelText("Institutional email"), { target: { value: "supervisor@university.edu" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secure-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue to verification" }));

    await screen.findByLabelText("Six-digit verification code");
    fireEvent.change(screen.getByLabelText("Six-digit verification code"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify email" }));

    // Wait for Dashboard to render
    await screen.findByRole("heading", { name: "Faculty Dashboard", level: 1 });

    // Navigate to GitHub Insights
    window.location.hash = "#github";
    window.dispatchEvent(new Event("hashchange"));

    // Verify on GitHub Insights page
    await screen.findByRole("heading", { name: "GitHub Insights", level: 1 });

    // Verify all four contributors are displayed with exact usernames and commit counts
    expect(await screen.findByText(/VINYTHA1708 \(@VINYTHA1708\)/i)).toBeTruthy();
    expect(screen.getByText(/vinythavenkatachalam@gmail\.com/i)).toBeTruthy();
    expect(screen.getByText(/12 commits/i)).toBeTruthy();

    expect(screen.getByText(/akshayaasa81-del \(@akshayaasa81-del\)/i)).toBeTruthy();
    expect(screen.getByText(/akshayaasa81@gmail\.com/i)).toBeTruthy();
    expect(screen.getByText(/10 commits/i)).toBeTruthy();

    expect(screen.getByText(/theertha436 \(@theertha436\)/i)).toBeTruthy();
    expect(screen.getByText(/theerthaesvar@gmail\.com/i)).toBeTruthy();
    expect(screen.getByText(/9 commits/i)).toBeTruthy();

    // Verify specifically swasthiprakash (@swasthiprakash) and 8 commits
    expect(screen.getByText(/swasthiprakash \(@swasthiprakash\)/i)).toBeTruthy();
    expect(screen.getByText(/swasthikaprakash@gmail\.com/i)).toBeTruthy();
    expect(screen.getByText(/8 commits/i)).toBeTruthy();

    // Confirm swasthika2106 is not present
    expect(screen.queryByText(/swasthika2106/i)).toBeNull();

    // Verify profile links
    const vinythaLink = screen.getByRole("link", { name: /VINYTHA1708 \(@VINYTHA1708\)/i });
    const akshayaaLink = screen.getByRole("link", { name: /akshayaasa81-del \(@akshayaasa81-del\)/i });
    const theerthaLink = screen.getByRole("link", { name: /theertha436 \(@theertha436\)/i });
    const swasthiLink = screen.getByRole("link", { name: /swasthiprakash \(@swasthiprakash\)/i });

    expect(vinythaLink.getAttribute("href")).toBe("https://github.com/VINYTHA1708");
    expect(akshayaaLink.getAttribute("href")).toBe("https://github.com/akshayaasa81-del");
    expect(theerthaLink.getAttribute("href")).toBe("https://github.com/theertha436");
    expect(swasthiLink.getAttribute("href")).toBe("https://github.com/swasthiprakash");

    // Verify mailto links
    expect(screen.getByRole("link", { name: "vinythavenkatachalam@gmail.com" }).getAttribute("href")).toBe("mailto:vinythavenkatachalam@gmail.com");
    expect(screen.getByRole("link", { name: "akshayaasa81@gmail.com" }).getAttribute("href")).toBe("mailto:akshayaasa81@gmail.com");
    expect(screen.getByRole("link", { name: "theerthaesvar@gmail.com" }).getAttribute("href")).toBe("mailto:theerthaesvar@gmail.com");
    expect(screen.getByRole("link", { name: "swasthikaprakash@gmail.com" }).getAttribute("href")).toBe("mailto:swasthikaprakash@gmail.com");

    // Verify that every contributor has an avatar img with their respective distinct GitHub avatar URL
    const vinythaAvatar = screen.getByAltText(/VINYTHA1708's profile avatar/i);
    const akshayaaAvatar = screen.getByAltText(/akshayaasa81-del's profile avatar/i);
    const theerthaAvatar = screen.getByAltText(/theertha436's profile avatar/i);
    const swasthiAvatar = screen.getByAltText(/swasthiprakash's profile avatar/i);

    expect(vinythaAvatar.getAttribute("src")).toBe("https://avatars.githubusercontent.com/u/205031091?v=4");
    expect(akshayaaAvatar.getAttribute("src")).toBe("https://avatars.githubusercontent.com/u/232072385?v=4");
    expect(theerthaAvatar.getAttribute("src")).toBe("https://avatars.githubusercontent.com/u/228942184?v=4");
    expect(swasthiAvatar.getAttribute("src")).toBe("https://avatars.githubusercontent.com/u/233741519?v=4");

    // Verify all images have consistent class
    expect(vinythaAvatar.className).toContain("contributor-avatar");
    expect(akshayaaAvatar.className).toContain("contributor-avatar");
    expect(theerthaAvatar.className).toContain("contributor-avatar");
    expect(swasthiAvatar.className).toContain("contributor-avatar");

    // Verify no avatars reuse VINYTHA1708's image for other contributors
    const srcList = [vinythaAvatar, akshayaaAvatar, theerthaAvatar, swasthiAvatar].map((img) => img.getAttribute("src"));
    const uniqueSrcs = new Set(srcList);
    expect(uniqueSrcs.size).toBe(4);

    // Verify fallback avatar behavior when an image fails to load
    fireEvent.error(swasthiAvatar);
    const fallback = screen.getByText("SW");
    expect(fallback.className).toContain("contributor-avatar-fallback");
    expect(fallback.textContent).toBe("SW");
  });

  it("student view on #1. AI-Based Project Monitoring System also shows swasthiprakash and distinct avatars", async () => {
    fetchMock = vi.fn(async (url) => {
      if (url === "/api/auth/login") return jsonResponse({ message: "Login code sent." }, 202);
      if (url === "/api/auth/otp/verify") {
        return jsonResponse({
          access_token: "student-token-override",
          account: { id: 2, role: "student", name: "Student User", email: "student@university.edu", student_id: 10 },
        });
      }
      if (url === "/api/projects/") {
        return jsonResponse([
          {
            id: 1,
            title: "AI-Based Project Monitoring System",
            description: "Academic monitoring and supervision platform",
            github_url: "https://github.com/VINYTHA1708/AI-Project-Monitoring",
            status: "ACTIVE",
          },
        ]);
      }
      if (url === "/api/projects/1/progress") {
        return jsonResponse({
          project_id: 1,
          project_title: "AI-Based Project Monitoring System",
          overall_status: "ACTIVE",
          milestones: { total: 0, completed: 0, pending: 0, completion_percentage: 0 },
          submissions: { total: 0, details: [] },
        });
      }
      if (url === "/api/projects/1/milestones/") return jsonResponse([]);
      if (url === "/api/projects/1/members/") return jsonResponse([]);
      if (url === "/api/projects/1/github/analysis") {
        return jsonResponse({
          repo_url: "https://github.com/VINYTHA1708/AI-Project-Monitoring",
          repo_name: "VINYTHA1708/AI-Project-Monitoring",
          default_branch: "main",
          total_commits: 20,
          contributor_stats: [],
          recent_activity: null,
          limitations_disclaimer: "Advisory git insights.",
        });
      }
      if (url === "/api/projects/1/ai-summary/") return jsonResponse({ provider_configured: false });
      if (url === "/api/projects/1/documents/") return jsonResponse([]);
      throw new Error(`Unexpected request to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.change(screen.getByLabelText("Institutional email"), { target: { value: "student@university.edu" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secure-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue to verification" }));

    await screen.findByLabelText("Six-digit verification code");
    fireEvent.change(screen.getByLabelText("Six-digit verification code"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify email" }));

    await screen.findByRole("heading", { name: "Dashboard", level: 1 });

    window.location.hash = "#github";
    window.dispatchEvent(new Event("hashchange"));

    await screen.findByRole("heading", { name: "GitHub Activity", level: 1 });

    expect(await screen.findByText(/VINYTHA1708 \(@VINYTHA1708\)/i)).toBeTruthy();
    expect(screen.getByText(/akshayaasa81-del \(@akshayaasa81-del\)/i)).toBeTruthy();
    expect(screen.getByText(/theertha436 \(@theertha436\)/i)).toBeTruthy();
    expect(screen.getByText(/swasthiprakash \(@swasthiprakash\)/i)).toBeTruthy();
    expect(screen.queryByText(/swasthika2106/i)).toBeNull();

    expect(screen.getByAltText(/VINYTHA1708's profile avatar/i).getAttribute("src")).toBe("https://avatars.githubusercontent.com/u/205031091?v=4");
    expect(screen.getByAltText(/akshayaasa81-del's profile avatar/i).getAttribute("src")).toBe("https://avatars.githubusercontent.com/u/232072385?v=4");
    expect(screen.getByAltText(/theertha436's profile avatar/i).getAttribute("src")).toBe("https://avatars.githubusercontent.com/u/228942184?v=4");
    expect(screen.getByAltText(/swasthiprakash's profile avatar/i).getAttribute("src")).toBe("https://avatars.githubusercontent.com/u/233741519?v=4");
  });

  it("does not override contributor data for other projects", async () => {
    fetchMock = vi.fn(async (url) => {
      if (url === "/api/auth/login") return jsonResponse({ message: "Login code sent." }, 202);
      if (url === "/api/auth/otp/verify") {
        return jsonResponse({
          access_token: "faculty-token-override",
          account: { id: 1, role: "faculty", name: "Dr. Supervisor", email: "supervisor@university.edu" },
        });
      }
      if (url === "/api/projects/") {
        return jsonResponse([
          {
            id: 2,
            title: "Acoustic Fingerprinting",
            description: "Audio analysis system",
            github_url: "https://github.com/VINYTHA1708/Acoustic-Fingerprinting",
            status: "ACTIVE",
          },
        ]);
      }
      if (url === "/api/students/") return jsonResponse([]);
      if (url === "/api/projects/2/progress") {
        return jsonResponse({
          project_id: 2,
          project_title: "Acoustic Fingerprinting",
          overall_status: "ACTIVE",
          milestones: { total: 0, completed: 0, pending: 0, completion_percentage: 0 },
          submissions: { total: 0, details: [] },
        });
      }
      if (url === "/api/projects/2/milestones/") return jsonResponse([]);
      if (url === "/api/projects/2/members/") return jsonResponse([]);
      if (url === "/api/projects/2/github/analysis") {
        return jsonResponse({
          repo_url: "https://github.com/VINYTHA1708/Acoustic-Fingerprinting",
          repo_name: "VINYTHA1708/Acoustic-Fingerprinting",
          default_branch: "main",
          total_commits: 39,
          contributor_stats: [
            {
              name: "VINYTHA1708",
              username: "VINYTHA1708",
              email: "vinythavenkatachalam@gmail.com",
              commits: 39,
              avatar_url: "https://avatars.githubusercontent.com/u/205031091?v=4",
              matched_member: null,
              match_confidence: "unmatched",
            },
          ],
          recent_activity: {
            last_commit_date: "2026-10-20T00:00:00Z",
            inspected_commit_window: 39,
          },
          limitations_disclaimer: "Git analytics are synthesized from public commit logs.",
        });
      }
      if (url === "/api/projects/2/ai-summary/") return jsonResponse({ provider_configured: false });
      if (url === "/api/projects/2/documents/") return jsonResponse([]);
      throw new Error(`Unexpected request to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.change(screen.getByLabelText("Institutional email"), { target: { value: "supervisor@university.edu" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secure-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue to verification" }));

    await screen.findByLabelText("Six-digit verification code");
    fireEvent.change(screen.getByLabelText("Six-digit verification code"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify email" }));

    await screen.findByRole("heading", { name: "Faculty Dashboard", level: 1 });

    // Navigate to GitHub Insights
    window.location.hash = "#github";
    window.dispatchEvent(new Event("hashchange"));

    await screen.findByRole("heading", { name: "GitHub Insights", level: 1 });

    // Project #2 should show its real dynamic contributor stats (1 contributor, 39 commits)
    expect(await screen.findByText(/VINYTHA1708 \(@VINYTHA1708\)/i)).toBeTruthy();
    expect(screen.getByText("vinythavenkatachalam@gmail.com")).toBeTruthy();
    expect(screen.getAllByText(/39 commits/i).length).toBeGreaterThan(0);

    // The manual override contributors should NOT appear
    expect(screen.queryByText(/akshayaasa81-del/i)).toBeNull();
    expect(screen.queryByText(/theertha436/i)).toBeNull();
    expect(screen.queryByText(/swasthiprakash/i)).toBeNull();
    expect(screen.queryByText(/swasthika2106/i)).toBeNull();
  });
});
