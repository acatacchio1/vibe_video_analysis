# Change Background to Dark Purple

## TL;DR

> **Quick Summary**: Update the CSS custom properties in `style.css` to dark purple tones.
>
> **Deliverables**: Modified `static/css/style.css` with purple background variables.
>
> **Estimated Effort**: Quick
> **Parallel Execution**: NO — single sequential task

---

## Context

### Original Request
"make the background dark purple"

### Interview Summary
No clarifying questions needed — trivial single-file change.

---

## Work Objectives

### Core Objective
Change the app background from dark blue to dark purple.

### Concrete Deliverables
- Updated `--bg-primary`, `--bg-secondary`, `--bg-tertiary`, `--bg-hover`, `--bg-card`, `--bg-input` in `:root` to purple tones
- Updated `body` gradient end color to match purple theme

### Definition of Done
- [ ] Open `http://localhost:10000` — background gradient is dark purple

### Must Have
- Purple-tinted background variables

### Must NOT Have (Guardrails)
- Do not change text colors or accent colors
- Do not modify any non-background properties

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (single task):
└── Task 1: Update CSS background variables [quick]

Wave FINAL:
└── Task F1: Plan compliance audit (oracle)
```

---

## TODOs

- [ ] 1. Update CSS Background to Dark Purple

  **What to do**:
  - Edit `static/css/style.css` lines 7-12 (`:root` block), change the `--bg-*` variables to dark purple tones:
    - `--bg-primary: #1a0a2e;` (deep purple)
    - `--bg-secondary: #1f0f35;` (dark purple)
    - `--bg-tertiary: #1e153d;` (medium dark purple)
    - `--bg-hover: #2a1d54;` (lighter purple hover)
    - `--bg-card: #251745;` (purple card)
    - `--bg-input: #120922;` (very dark purple input)
  - Edit `static/css/style.css` line 61, change the `body` gradient end color from `#15162e` to `#261645`

  **Must NOT do**:
  - Change `--text-*`, `--accent-*`, or any other variables
  - Modify non-background CSS properties

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple find-and-replace CSS edit, single file.
  - **Skills**: [] — unnecessary for this trivial edit.

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 1 (only task)
  - **Blocks**: F1 (final verification)
  - **Blocked By**: None

  **References**:
  - `static/css/style.css:7-12` — Current `--bg-*` variable values to replace
  - `static/css/style.css:61` — `body` background gradient line to update

  **Acceptance Criteria**:
  - [ ] `static/css/style.css` contains `--bg-primary: #1a0a2e;`
  - [ ] `static/css/style.css` contains `--bg-card: #251745;`
  - [ ] `body` background gradient ends with `#261645`
  - [ ] Open http://localhost:10000 — page background appears dark purple

  **QA Scenarios**:
  \`\`\`
  Scenario: Background is dark purple on page load
    Tool: Playwright
    Preconditions: Server running on port 10000
    Steps:
      1. Navigate to http://localhost:10000
      2. Get computed background of `body` via `window.getComputedStyle(document.body).background`
      3. Assert color contains purple hex values (#1a0a2e or blended gradient)
    Expected Result: Background gradient is purple-toned gradient
    Failure Indicators: Background still shows blue (#0f0f23 / #15162e)
    Evidence: .sisyphus/evidence/task-1-bg-screenshot.png

  Scenario: Cards match purple theme
    Tool: Playwright
    Preconditions: Server running, page loaded
    Steps:
      1. Navigate to http://localhost:10000
      2. Get computed `.app-card` background
      3. Assert it matches --bg-card (#251745)
    Expected Result: Card backgrounds are purple-tinted
    Evidence: .sisyphus/evidence/task-1-cards-screenshot.png
  \`\`\`

  **Commit**: YES
  - Message: `style(background): change background to dark purple theme`
  - Files: `static/css/style.css`

---

## Final Verification Wave

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Verify `--bg-*` variables are purple, `body` gradient updated, no other variables changed.

---

## Commit Strategy

- **1**: `style(background): change background to dark purple theme` — static/css/style.css

---

## Success Criteria

### Verification Commands
```bash
grep '--bg-primary' static/css/style.css  # Expected: --bg-primary: #1a0a2e;
grep '#261645' static/css/style.css       # Expected: present in body gradient
```

### Final Checklist
- [ ] All `--bg-*` variables updated to purple
- [ ] Body gradient updated
- [ ] No other variables modified
- [ ] Page background appears dark purple at http://localhost:10000
