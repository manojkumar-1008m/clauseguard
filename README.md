# ClauseGuard

A production‑oriented Chrome extension that detects potential dark patterns on consumer‑facing webpages.

## Project Structure
```
ClauseGuard/
│
├─ backend/
│   ├─ __init__.py
│   ├─ main.py
│   ├─ model_loader.py
│   ├─ schemas.py
│   ├─ preprocessing.py
│   └─ requirements.txt
├─ extension/
│   ├─ manifest.json
│   ├─ content.js
│   ├─ background.js
│   ├─ popup.html
│   ├─ popup.js
│   ├─ popup.css
│   └─ icons/
├─ model/
│   └─ clauseguard_model_v1.joblib   # place the provided model here
├─ scripts/
│   ├─ verify_model.py
│   └─ health_check.py
├─ tests/
│   ├─ test_model_loading.py
│   ├─ test_prediction.py
│   ├─ test_api.py
│   ├─ test_validation.py
│   └─ test_extension_contracts.py
├─ .gitignore
├─ README.md
└─ .env.example
```

## Local Development Setup

### 1. Create Python virtual environment
```bash
python -m venv .venv
# Windows activation
.venv\Scripts\activate
```

### 2. Install backend dependencies
```bash
pip install -r backend/requirements.txt
```

### 3. Verify the model can be loaded
Place `clauseguard_model_v1.joblib` inside the `model/` directory, then run:
```bash
python scripts/verify_model.py
```
You should see the model type and predictions for two sanity‑check sentences.

### 4. Run the FastAPI backend
```bash
uvicorn backend.main:app --reload
```
The API will be available at `http://127.0.0.1:8000`.

### 5. Run the test suite
```bash
pip install pytest httpx
pytest
```
All tests should pass once the model file is present.

### 6. Load the Chrome extension (development mode)
1. Open `chrome://extensions/`.
2. Enable **Developer mode** (toggle in the top‑right).
3. Click **Load unpacked** and select the `extension/` folder.
4. Ensure the backend is running (`uvicorn ...`).
5. Open any webpage, click the ClauseGuard extension icon, and press **Analyze Page**.

## Commands Summary
| Action | Command |
|--------|---------|
| Create env | `python -m venv .venv && .venv\Scripts\activate` |
| Install deps | `pip install -r backend/requirements.txt` |
| Verify model | `python scripts/verify_model.py` |
| Run API | `uvicorn backend.main:app --reload` |
| Run tests | `pytest` |
| Load extension | Follow steps above in Chrome UI |

## Security and Data Privacy Guarantees

ClauseGuard operates under a strict least-privilege, local-first security architecture:

- **User-Initiated Only**: Text extraction and analysis occur strictly upon the user clicking "Analyze Page". No background tracking or continuous webpage scanning occurs.
- **Local Transmission**: The extension communicates exclusively with the local backend at `http://127.0.0.1:8000/predict`. No remote servers, cloud infrastructure, or third-party analytics are contacted.
- **Payload Restrictions**: Webpage text is normalized and capped at a maximum of 5,000 characters.
- **Zero Sensitive Data Access**:
  - No browsing history is collected or accessed (`tabs` permission is removed; only ephemeral `activeTab` is used).
  - No cookies, sessions, or credentials are accessed or sent.
  - Form password values and payment-card details are never inspected.
- **No Data Persistence**: The backend evaluates text in-memory and does not store or log webpage contents to disk or a database.
- **Safe DOM Rendering**: All extension UI rendering uses `textContent`. No dynamic evaluation (`eval`, `new Function`, `innerHTML`) is permitted.

