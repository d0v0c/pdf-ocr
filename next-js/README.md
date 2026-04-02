# PDF OCR & Stamp Tool (Next.js)

## Setup

```bash
# 1. Install dependencies
npm install
# 2. Set up API keys and stamp.png.
cp .env.example .env
# 3. Runs on port 3000. Entry path: /portal
npm run dev
# Production deployment
npm run build
npm run start
```

## Notes

### API Switch (HTTP 429 Too Many Requests)

The Gemini Free tier is unstable during peak hours and has strict quotas. If a 429 error occurs, use the UI button to switch to Paid mode. The code maintains two separate clients (`clientFree` & `clientPaid`) to handle this.

### File Cleanup

Stamped PDFs are temporarily saved in `temp-pdfs/`. After the download finishes, Next.js `after()` triggers `fs.unlink` to delete the file.

### Concurrent Requests

The PDF is split by pages and sent to the LLM concurrently via `tasks.push`. The total execution time depends on the slowest single page.

### Model Stability

Keeping temperature at 0.0 is stable. Even at 0.1, the parsing failures increase noticeably.
