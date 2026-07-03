# NomixCloner API Example

A ready-to-use example for batch cloning via the NomixCloner API. You upload a list of apps (CSV file), the script sends them for cloning, waits until everything is ready, and saves a file with download links.

Full API documentation: [check.nomixcloner.com/docs](https://check.nomixcloner.com/docs)

## Requirements

1. **Premium** license in the NomixCloner Telegram bot.
2. **API key** — open the bot and run `/apikey`.
3. **Python 3.10 or newer** — [python.org/downloads](https://www.python.org/downloads/) (during installation on Windows, check **“Add Python to PATH”**).

## Installation

### Option A — download as ZIP (easiest)

1. Open [github.com/nomix-ai/NomixClonerApiExample](https://github.com/nomix-ai/NomixClonerApiExample).
2. Click **Code → Download ZIP**.
3. Unzip the folder anywhere on your computer.
4. Open a terminal in that folder:
   - **Windows:** open the folder in Explorer, click the address bar, type `cmd`, press Enter.
   - **macOS:** right-click the folder → **New Terminal at Folder**.
5. Install the one required library:

```bash
pip install -r requirements.txt
```

### Option B — using Git

```bash
git clone https://github.com/nomix-ai/NomixClonerApiExample.git
cd NomixClonerApiExample
pip install -r requirements.txt
```

## Quick start

### Step 1 — Prepare your batch CSV

- **Android:** edit `api_batch_clones.csv`
- **iOS:** edit `api_batch_clones_ios.csv`

Or copy your batch CSV from the Telegram bot into the matching file. **Do not rename the files** — the script picks the right one based on `--platform`.

### Step 2 — Add your API key

Copy your API key from the bot (`/apikey`).

Open `api_batch_runner.py` in any text editor (Notepad, TextEdit, VS Code). Near the top, find:

```python
API_KEY = ""
```

Paste your key between the quotes:

```python
API_KEY = "your_key_here"
```

Save the file.

> **Keep this key private.** Anyone with your key can use your account’s API access.

### Step 3 — Run the script

In the terminal, inside the project folder:

**Android:**
```bash
python api_batch_runner.py --platform Android
```

**iOS:**
```bash
python api_batch_runner.py --platform iOS
```

On some systems the command is `python3` instead of `python`:

```bash
python3 api_batch_runner.py --platform Android
```

### What you will see

The script prints progress, for example:

```
Uploading api_batch_clones.csv (Android)...
Accepted: batch_uuid=abc123, clones_count=2
Waiting for completion...
  status=processing, progress=0/2, failed=0, pending=2, result_ready=False
  status=processing, progress=1/2, failed=0, pending=1, result_ready=False
  status=completed, progress=2/2, failed=0, pending=0, result_ready=True
Result saved to results/batch_abc123.json
```

**Do not close the terminal** until you see `Result saved to ...` or an error message. Cloning can take from several minutes to hours depending on batch size.

### Where is the result?

Open the `results/` folder. Inside you will find `batch_<id>.json` — a file with download links for your cloned apps.

You can also open that JSON file in a browser or text editor and copy the `download_url` values.

## How it works

You do not need to call the API yourself — the script does it for you:

1. **Upload** — your CSV is sent to NomixCloner (`POST /api/batch`).
2. **Wait** — every 15 seconds the script checks how many clones are done (`GET /api/batch/{id}`).
3. **Download** — when everything is ready, the script saves the result file from the link provided by the server.

If something fails, the script stops and prints an error. See [Troubleshooting](#troubleshooting) below.

## CSV format

Delimiter: `;` or `,`.

**Android — required columns:** App Name, Version, Architecture, Clone Index, Location.

**iOS — required columns:** App Name, Version, Clone Index, Location.

- `Location` — `latitude, longitude` or `0, 0` for no geolocation.
- `Architecture` for Android: `armeabi-v7a`, `arm64-v8a`, `x86`, `x86-64`, `Any`.

See `api_batch_clones.csv` (Android) and `api_batch_clones_ios.csv` (iOS) for sample rows.

## Result

```json
{
  "platform": "Android",
  "apps": [
    {
      "app_id": "com.instagram.android",
      "app_name": "Instagram 1",
      "download_url": "https://download.nomixcloner.com/..."
    }
  ]
}
```

Each `download_url` is a direct link to download the cloned app.

## Useful options

| Option | Default | Description |
|--------|---------|-------------|
| `--platform` | Android | `Android` or `iOS` |
| `--csv` | platform default | `api_batch_clones.csv` (Android) or `api_batch_clones_ios.csv` (iOS) |
| `--poll-interval` | 15 | How often to check status (seconds) |
| `--output-dir` | `results/` | Where to save the result file |
| `--batch-uuid` | — | Wait for a batch that is already running |
| `--no-download` | — | Only wait, do not save the result file |
| `--timeout` | 6 hours | Maximum wait time |

**Wait for an existing batch** (if you already started one and closed the terminal):

```bash
python api_batch_runner.py --batch-uuid YOUR_BATCH_UUID
```

## Troubleshooting

| Message | What to do |
|---------|------------|
| `Error: set API_KEY...` | Paste your key into `API_KEY = "..."` in `api_batch_runner.py` and save |
| `'python' is not recognized` | Install Python and enable “Add to PATH”, or try `python3` |
| `Another batch ... already in progress` | Wait for the current batch to finish, or cancel it in the Telegram bot |
| `Batch cloning limit reached` | You have reached the daily clone limit |
| `Batch ... did not finish within ...s` | The batch took too long; try again or increase `--timeout` |
| Rate limit (429) | The script waits automatically; if it happens often, increase `--poll-interval` |

## Files

| File | Purpose |
|------|---------|
| `api_batch_runner.py` | Main script — upload, wait, download |
| `api_batch_clones.csv` | Android app list (edit this) |
| `api_batch_clones_ios.csv` | iOS app list (edit this) |
| `requirements.txt` | Python dependencies |
