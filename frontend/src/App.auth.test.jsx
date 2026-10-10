import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App.jsx";

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("faculty authentication", () => {
  let fetchMock;
  let storageWrite;

  beforeEach(() => {
    window.location.hash = "#submissions";
    storageWrite = vi.spyOn(Storage.prototype, "setItem");
  });

  afterEach(() => {
    cleanup();
    window.location.hash = "";
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("registers, verifies email, logs in, and uses the token in protected requests", async () => {
    fetchMock = vi.fn(async (url, options) => {
      if (url === "/api/auth/register/faculty") {
        return jsonResponse({ message: "Verification sent." }, 202);
      }
      if (url === "/api/auth/otp/verify") {
        const request = JSON.parse(options.body);
        if (request.purpose === "registration") {
          return jsonResponse({
            message: "Email verified.",
            email_verified: true,
            faculty_approval_pending: false,
          });
        }
        return jsonResponse({
          message: "Authenticated.",
          email_verified: true,
          access_token: "memory-only-token",
          token_type: "bearer",
          expires_in: 1800,
          account: { id: 1, role: "faculty", email: "faculty@university.edu", name: "Faculty" },
        });
      }
      if (url === "/api/auth/login") {
        return jsonResponse({ message: "Login code sent." }, 202);
      }
      if (url === "/api/projects/") {
        expect(options.headers.Authorization).toBe("Bearer memory-only-token");
        return jsonResponse([]);
      }
      throw new Error(`Unexpected request to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Register" }));
    fireEvent.change(screen.getByLabelText("Full name"), {
      target: { value: "Test Faculty" },
    });
    fireEvent.change(screen.getByLabelText("Faculty ID"), {
      target: { value: "FAC-1" },
    });
    fireEvent.change(screen.getByLabelText("Institutional email"), {
      target: { value: "faculty@university.edu" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "a-long-test-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    await screen.findByLabelText("Six-digit verification code");
    fireEvent.change(screen.getByLabelText("Six-digit verification code"), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify email" }));

    await screen.findByRole("heading", { name: "Welcome back" });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "a-long-test-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue to verification" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/auth/login",
        expect.objectContaining({ method: "POST" }),
      );
    });
    await screen.findByLabelText("Six-digit verification code");
    fireEvent.change(screen.getByLabelText("Six-digit verification code"), {
      target: { value: "654321" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify email" }));

    await screen.findByText("No projects yet");
    expect(screen.getByRole("heading", { name: "Submissions" })).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer memory-only-token",
        }),
      }),
    );
    expect(storageWrite).not.toHaveBeenCalled();
  });

  it("returns to sign-in when a protected request rejects the in-memory token", async () => {
    fetchMock = vi.fn(async (url, options) => {
      if (url === "/api/auth/login") {
        return jsonResponse({ message: "Login code sent." }, 202);
      }
      if (url === "/api/auth/otp/verify") {
        return jsonResponse({
          message: "Authenticated.",
          email_verified: true,
          access_token: "expired-token",
          token_type: "bearer",
          expires_in: 1800,
          account: { id: 1, role: "faculty", email: "faculty@university.edu", name: "Faculty" },
        });
      }
      if (url === "/api/projects/") {
        expect(options.headers.Authorization).toBe("Bearer expired-token");
        return jsonResponse({ detail: "Invalid or expired token." }, 401);
      }
      throw new Error(`Unexpected request to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.change(screen.getByLabelText("Institutional email"), {
      target: { value: "faculty@university.edu" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "a-long-test-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue to verification" }));
    await screen.findByLabelText("Six-digit verification code");
    fireEvent.change(screen.getByLabelText("Six-digit verification code"), {
      target: { value: "654321" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify email" }));

    await screen.findByRole("heading", { name: "Welcome back" });
    expect(storageWrite).not.toHaveBeenCalled();
  });
});
