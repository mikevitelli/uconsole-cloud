---
description: "Design a UX flow for a uconsole feature — user journey, component structure, states, and edge cases"
allowed-tools: Agent, Read, Glob, Grep, Bash
---

Design the UX for: $ARGUMENTS

This is a READ-ONLY design exercise. Do NOT write code. Output a design document.

## Process

### 1. Context
Read docs/FEATURES.md and CLAUDE.md to understand where this fits. Identify the user persona (Mike on phone, new user on SSH, someone on the same WiFi, etc.).

### 2. User Journey
Map the step-by-step flow from the user's perspective:
- What triggers this flow?
- What does the user see at each step?
- What actions can they take?
- What happens on success/failure/timeout?
- What device are they on? (phone PWA, SSH terminal, browser on laptop)

### 3. States
For each screen/component involved, define:
- **Loading** — what shows while data is being fetched?
- **Empty** — what shows when there's no data?
- **Error** — what shows when something fails?
- **Offline** — what shows when the device is unreachable?
- **Edge cases** — what if the user is in AP mode? What if the token expired? What if the repo was deleted?

### 4. Component Structure
Propose which existing components to modify vs. new components to create. Reference existing patterns from the codebase (read the relevant components to match style).

### 5. Information Hierarchy
What's most important on screen? What's secondary? What can be hidden behind a tap/click?

### 6. Mobile vs Desktop
The primary use case is phone (Safari PWA). Design mobile-first. Note any desktop-specific enhancements.

### 7. Output
Produce an ASCII mockup of each screen state, plus a summary of decisions made and open questions for the user.
