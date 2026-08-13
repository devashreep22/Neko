# 🐱 NekoAI — Your Intelligent Desktop Study Companion

NekoAI is an AI-powered desktop pet that lives on your desktop and quietly observes your computer activity in the background. It tracks productive and entertainment usage, analyzes your habits, and reacts in real time with different moods and animations.

Unlike traditional productivity trackers, NekoAI behaves like a companion. It changes its appearance based on what you are doing — coding, learning, watching content, taking a break, or getting distracted.

---

## ✨ Current Progress

### Backend (FastAPI)

* Tracks active Windows applications
* Detects browser tabs and application titles
* Classifies activities into categories such as:

  * Coding
  * Learning
  * Browsing
  * Entertainment
* Logs activity history into a JSON file
* Generates daily productivity reports
* Exposes REST API endpoints

### Desktop Application (Electron + React)

* Transparent floating desktop window
* Borderless always-on-top pet
* Draggable desktop companion
* React-based UI with Tailwind CSS
* Framer Motion animation support
* Multiple Neko state images:

  * idle
  * coding
  * learning
  * watching
  * happy
  * angry
  * sleepy
  * celebrating
  * drink

---

## 🏗️ Project Structure

```text
NekoAI/
├── backend/
│   ├── app/
│   │   ├── services/
│   │   │   ├── activity_tracker.py
│   │   │   ├── analytics.py
│   │   │   ├── current_activity.py
│   │   │   └── neko_state.py
│   │   ├── utils/
│   │   │   ├── activity_classifier.py
│   │   │   └── activity_logger.py
│   │   ├── data/
│   │   │   └── activity_log.json
│   │   └── main.py
│   └── requirements.txt
│
└── desktop/
    ├── electron/
    │   ├── main.js
    │   └── preload.cjs
    ├── src/
    │   ├── assets/
    │   │   └── neko/
    │   ├── components/
    │   │   └── Pet.jsx
    │   ├── App.jsx
    │   ├── index.css
    │   └── main.jsx
    ├── package.json
    └── vite.config.js
```

---

## ⚙️ How It Works

### Activity Tracking

NekoAI monitors the active window on your computer and records:

* Application name
* Browser tab title
* Time spent
* Category of activity

Example:

```json
{
  "window_title": "Problems - LeetCode - Brave",
  "category": "DSA",
  "duration_seconds": 1200
}
```

### Analytics

The backend aggregates activity logs and generates productivity summaries.

Example API response:

```json
{
  "category_totals": {
    "Coding": 7200,
    "Learning": 3600,
    "Browsing": 1200
  },
  "productive_time_seconds": 10800
}
```

### Neko State Engine

The backend converts activity information into emotional states.

| Activity                        | Duration | Neko State |
| ------------------------------- | -------- | ---------- |
| VS Code                         | Any      | coding     |
| Learning                        | Any      | learning   |
| Netflix / YouTube Entertainment | < 90 min | watching   |
| Entertainment                   | ≥ 90 min | angry      |
| Browsing                        | Any      | idle       |

These states will control which pet image and animation is displayed.

---

## 🚀 Running the Project

### Backend

```bash
cd backend
python -m venv venv
venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API endpoints:

* `/`
* `/health`
* `/report`
* `/current-activity`

### Desktop

```bash
cd desktop
npm install
npm run dev
npm run electron
```

This launches the transparent floating desktop pet.

---

## 🧠 Planned Features

* AI-based YouTube content classification
* Automatic mood changes based on activity
* Speech bubbles and reminders
* Goal-based productivity plans
* Daily and weekly analytics dashboard
* Streak tracking
* Hydration reminders
* Idle detection and sleep mode
* Walking and idle animations
* Custom pet themes
* Supabase cloud synchronization
* Packaging as a downloadable Windows desktop application

---

## 🛠️ Tech Stack

### Backend

* Python
* FastAPI
* pywin32
* JSON storage

### Desktop

* Electron
* React
* Vite
* Tailwind CSS
* Framer Motion

### Future

* Supabase
* PostgreSQL
* OpenAI / Gemini API
* Electron Builder

---

## 🎯 Vision

NekoAI aims to become a friendly desktop companion that helps users build better study and work habits without feeling like a strict productivity app. Instead of constantly monitoring the user with charts and numbers, NekoAI reacts emotionally, celebrates progress, reminds gently, and keeps the user company throughout the day.

---

Made with ☕ and a lot of late-night coding by **Devashree Pathak**.
