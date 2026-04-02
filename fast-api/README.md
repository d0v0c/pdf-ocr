# [Deprecated] PDF OCR & Stamp Tool

>  This FastAPI/HTML implementation has been completely refactored into a [Next.js](../next-js) application for better UI reactivity.

Personal workflow: extract PDF information, verify total price, and auto-stamp. Built with FastAPI + Gemini 2.5 Flash.

## Setup

```bash
# 1. Install dependencies
uv sync
# 2. Set up API keys and stamp.png. Pydantic will block startup if missing.
cp .env.example .env
# 3. Runs on port 8001. Entry path: /portal
uv run main.py
```

## Notes

### API Switch (HTTP 429 Too Many Requests)

The Gemini Free tier is unstable during peak hours and has strict quotas. If a 429 error occurs, use the UI button to switch to Paid mode. The code maintains two separate clients (`client_free` & `client_paid`) to handle this smoothly.

### File Cleanup

Stamped PDFs are temporarily saved in `temp_pdfs/`. After the download finishes, FastAPI's `BackgroundTasks` asynchronously triggers `pathlib.unlink` to delete the file. Comment out the LLM API calls and this cleanup step to test the framework without wasting tokens.

### Concurrent Requests

The PDF is split by pages and sent to the LLM concurrently via `asyncio.gather`. The total execution time depends on the slowest single page.

### Model Stability

Keeping temperature at 0.0 is stable. Even at 0.1, the parsing failures increase noticeably.