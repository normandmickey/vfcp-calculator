from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import os

app = FastAPI(title="vcfp-calculator2")

HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>vcfp-calculator2</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
  <div class="container py-5 text-center">
    <h1>vcfp-calculator2</h1>
    <p class="lead text-muted">A FastAPI app built with SaaSClaw Studio.</p>
    <p>Try the <a href="/docs">auto-generated API docs</a>.</p>
  </div>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def home():
    return HTML


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": "vcfp-calculator2"}
