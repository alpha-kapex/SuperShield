# SuperShield web

Evidence-led React workspace for the SuperShield synthetic franchise investigation.

## Run locally

```bash
npm install
npm run dev
```

The development server proxies `/health`, `/demo-cases`, `/cases`, and `/runs` to `http://127.0.0.1:8000`. Set `VITE_API_BASE_URL` when the API is hosted elsewhere.

## Verify

```bash
npm test
npm run build
```

The UI uses the backend’s camelCase schema, opens the native SSE run stream, and falls back to run polling when the stream disconnects.
