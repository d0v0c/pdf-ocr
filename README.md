# PDF OCR & Stamp Tool

Personal workflow: extract PDF information, verify total price, and auto-stamp. Powered by Gemini 2.5 Flash.

## Repository Structure

This repository contains two distinct implementations:

- [`/next-js`](./next-js)
 The unified full-stack application with better UI reactivity.

- [`/fast-api`](./fast-api) (Legacy Version)
  The original Minimum Viable Product.

[View the Demo here.](https://pdf.plandium.net/demo)

## Notes

### API Switch (HTTP 429 Too Many Requests)

The Gemini Free tier is unstable during peak hours and has strict quotas. If a 429 error occurs, use the UI button to switch to Paid mode. The code maintains two separate clients (`clientFree` & `clientPaid`) to handle this.

### File Cleanup

Stamped PDFs are temporarily saved in `temp-pdfs/`. After the download finishes, Next.js `after()` triggers `fs.unlink` to delete the file.

### Concurrent Requests

The PDF is split by pages and sent to the LLM concurrently via `tasks.push`. The total execution time depends on the slowest single page.

### Model Stability

Keeping temperature at 0.0 is stable. Even at 0.1, the parsing failures increase noticeably.

### Cloudflare WAF blocks Server Action POSTs

A PDF hang on uploading, sometimes throw exception "An unexpected response was received from the server".
Cloudflare blocks it as CVE-2025-55183 attack. 

> See `Cloudflare dashboard → Doamin Overview → Security → Analytics → Events → Export event JSON`.
> 
> Fix `Cloudflare dashboard → Doamin Overview → Security → Security rules → New custom rule → Field HTTPS → WAF components to skip: All managed rules`.