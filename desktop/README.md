# NekoAI Desktop

## Windows launch

From PowerShell in `C:\NekoAi`, run:

```powershell
.\Start_NekoAI.bat
```

The launcher checks the Python environment, builds the React frontend, and opens the NekoAI Electron dashboard. Sign in with the local demo account configured for this demonstration; the backend validates the credentials and stores only a salted PBKDF2 hash in `%LOCALAPPDATA%\NekoAI\accounts.json`. The transparent pet window is prepared but hidden until you select **Allow Neko on Desktop**. The dashboard can show, hide, or enable mouse interaction for the pet. Use **Exit NekoAI** to stop the app and its managed backend. Closing the dashboard leaves the desktop companion and backend running; launch NekoAI again to reopen the dashboard.

The starter credentials are for local demonstration only. Before production use, replace the username, salt, hash, and iteration settings in `backend/app/accounts.py` with a freshly generated PBKDF2-HMAC-SHA256 credential, and remove the demo account data file only when intentionally resetting the account. Never commit a plaintext password. Account initialization is create-once and does not overwrite an existing `accounts.json`.

The cat window is click-through by default. Choose **Move / interact** in the dashboard or press `Ctrl+Alt+N` to enable mouse input and drag Neko. Press `Ctrl+Alt+N` again or choose **Done moving** to return to click-through. `Ctrl+Alt+D` opens the dashboard.

## Development

```powershell
cd C:\NekoAi\desktop
npm run dev
```

This runs the same Electron app with Vite serving the React UI. To view only the website in a browser, use `npm run web:dev`; browser mode explains that it cannot reveal a Windows desktop window. Do not use browser mode as the desktop-pet launcher.

## Tests and production build

```powershell
cd C:\NekoAi\desktop
npm test
npm run build
```

The backend listens on loopback port `8765` by default. Electron and the backend use `%LOCALAPPDATA%\NekoAI` for `run.json`, the launch token, and account credentials. Electron verifies the launch token against the backend before reusing it; the token remains in the main process and is never added to a renderer URL. If an unmanaged server occupies port `8765`, close the terminal/process that started it and choose **Retry after closing the other server** in the recovery dialog. NekoAI will then start its managed backend in the same data directory without deleting activity records. Authentication, origin checks, and local-only binding stay enabled.

The dashboard's live total is counted since the current backend launch. Weekly charts and the timeline aggregate completed records from the existing `backend/app/data/activity_log.json` file. This project uses that local JSON log rather than SQLite. No reminder schedule/history API currently exists, so the UI only displays reminder states if the tracker reports them.
