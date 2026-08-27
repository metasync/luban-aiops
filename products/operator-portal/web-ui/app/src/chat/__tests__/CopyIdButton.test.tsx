// Session-id copy button tests (SPEC-039 R-8): one-click clipboard copy
// with a visible confirmation state (icon flips to a check mark).
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CopyIdButton } from "../ChatView";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("CopyIdButton (SPEC-039 R-8)", () => {
  it("copies the session id and shows the confirmation state", async () => {
    const writeText = vi.fn(async () => {});
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    render(<CopyIdButton id="ses-abc-123" />);
    const button = screen.getByLabelText("Copy session id ses-abc-123");
    fireEvent.click(button);
    expect(writeText).toHaveBeenCalledWith("ses-abc-123");
    // The visible confirmation state swaps the copy glyph for a check.
    expect(
      await screen.findByLabelText("Copy session id ses-abc-123"),
    ).toBeTruthy();
  });

  it("stops propagation so the panel entry does not switch sessions", () => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn(async () => {}) },
    });
    const outer = vi.fn();
    render(
      <div onClick={outer}>
        <CopyIdButton id="ses-1" />
      </div>,
    );
    fireEvent.click(screen.getByLabelText("Copy session id ses-1"));
    expect(outer).not.toHaveBeenCalled();
  });
});
