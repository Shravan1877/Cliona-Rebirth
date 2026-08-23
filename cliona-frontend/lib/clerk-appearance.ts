import type { Appearance } from "@clerk/types";

/** Loosely matches CLAUDE.md §10.4 — Clerk renders its own DOM, so this is a light theming pass, not full brand parity. */
export const clerkAppearance: Appearance = {
  variables: {
    colorPrimary: "#39AAAA",
    borderRadius: "1rem",
    fontFamily: "var(--font-inter), sans-serif",
  },
};
