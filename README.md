# FresherLaunch 🚀

An editorial, human-designed resume checker and honest job-matcher engineered specifically for fresh college graduates entering the tech market.

Built with **Next.js 14 (App Router)**, **TypeScript**, **Tailwind CSS**, and **Framer Motion**.

---

## 🎨 Design System: "Warm Paper & Sharp Ink"
FresherLaunch deliberately rejects the generic "AI dashboard" look (no purple gradients, no glassmorphism, no emoji icons, no Inter/Roboto):
- **Paper Background**: `#F4EFE6`
- **Dense Carbon Ink**: `#141414`
- **Editorial Tomato Accent**: `#FF4F2E`
- **Typography**:
  - Headlines: **Fraunces** (tight, large display serif)
  - Body & UI: **DM Sans** (clean, readable geometric sans)
  - Scores & Diffs: **Space Mono** (precise typewriter numbers)
- **Visual Stylings**:
  - 2px solid ink borders
  - Hard offset drop shadows (`4px 4px 0px #141414`)
  - Rotated editorial stickers (`-2deg`, `3deg`)
  - Hand-drawn SVG underlines, asterisks, and stamps

---

## 🧭 Flow & Features

### 1. Welcome & Letter-by-Letter Hero
- Full-screen `"WELCOME, FRESHER"` title with staggered spring physics animations letter by letter.
- Real-time typewriter sequence: *"Drop your resume. Let's make it impossible to ignore."*
- Drop box fades in with drag-over tilt physics (`rotate-2`), changing state to `"Yes, right here."`
- Real-time multi-step progress animator: `Reading → Checking ATS → Scoring → Finding jobs`.

### 2. Deterministic ATS Scoring Engine (Fixed Mathematical Rules)
No hallucinated AI score guesswork. The score (0–100) is calculated strictly by code rules:
1. **Formatting & Structure (25 pts)**: Scanned image detection, encoding cleanliness, clear linebreaks, standard bullets, and absence of outdated filler phrases.
2. **Technical Keywords Density (25 pts)**: Matches against curated taxonomy of modern graduate tech skills (Python, SQL, React, Docker, Linux, Git, etc.).
3. **Essential Sections (15 pts)**: Verifies presence of Education, Skills, Projects, Experience, and Summary.
4. **Action Verbs & Impact Metrics (15 pts)**: XYZ formula validation (e.g. *engineered*, *automated*, *reduced latency by 45%*).
5. **Word Count & Page Density (10 pts)**: Targets the ideal 350–750 word 1-page graduate standard.
6. **Contact & Professional Links (10 pts)**: Professional email, phone number, GitHub repository, and LinkedIn profile.

### 3. Annotated Resume & Click-to-Fix Cards
- Displays the real parsed resume text with editorial color highlights:
  - 🔴 **Red (Must Fix)**: Missing GitHub, outdated objectives, zero quantified metrics.
  - 🟡 **Amber (Needs Improvement)**: Passive phrasing, weak bullets.
  - 🟢 **Green (Strong Match)**: High-demand technical keywords.
- Clicking any highlight opens an actionable **Fix Card**:
  - **WHERE**: e.g. *Contact Header* or *Deep Traffic-VTS Project*
  - **WHAT'S WRONG**: ATS rule explanation
  - **CHANGE THIS → TO THIS**: Copyable replacement text
  - **"Re-check"** preview showing projected score increase (+22 pts).
  - **"Download improved resume"**: Exports an ATS-safe, clean single-column DOCX.

### 4. Real Jobs Feed (Adzuna API Integration)
- Server-side integration with Adzuna Job Search API.
- Filter by timeframe (`24h`, `3d`, `7d` default, `30d`), location, and minimum match threshold.
- Senior and lead roles are strictly filtered out.
- **Honest Match Percentage**: Calculated deterministically based on verified skill overlap. Capped between 68% and 94% — **never shows a fake 100%**.
- Local **Save Job** state persisted via `localStorage`.

---

## 🔒 Privacy Guarantee
- Resumes are parsed **strictly in-memory** and **never saved** to disk or remote storage.

---

## 🛠️ Getting Started

### 1. Prerequisites
- Node.js 18+ (tested on Node v20 LTS)
- npm or pnpm

### 2. Setup & Installation
```bash
cd fresherlaunch
npm install
```

### 3. Environment Variables
Copy `.env.example` to `.env.local`:
```bash
cp .env.example .env.local
```
Add your optional Adzuna API credentials:
```env
ADZUNA_APP_ID=your_adzuna_app_id
ADZUNA_APP_KEY=your_adzuna_app_key
```
*(When omitted, FresherLaunch provides verified active graduate tech openings across India).*

### 4. Run Development Server
```bash
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## 📱 Mobile-First & Accessible
- Fully responsive across desktop (1440px) and mobile devices (375px).
- High-contrast carbon ink on warm paper exceeds WCAG AAA readability standards.
