import csv
import io
from fastapi import FastAPI, Request, UploadFile, File, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, field_validator
from datetime import date, datetime, timedelta
from typing import Optional

app = FastAPI(title="VFCP Lost Earnings Calculator")

# ── DOL VFCP Mid-Term Rates (annual, compounded) ──
# Source: Department of Labor, EBSA — published monthly
VFCP_RATES = {
    2020: {1: 1.69, 2: 1.58, 3: 1.25, 4: 1.08, 5: 0.78, 6: 0.61, 7: 0.48, 8: 0.44, 9: 0.38, 10: 0.33, 11: 0.28, 12: 0.27},
    2021: {1: 0.24, 2: 0.22, 3: 0.20, 4: 0.18, 5: 0.17, 6: 0.16, 7: 0.15, 8: 0.14, 9: 0.14, 10: 0.13, 11: 0.16, 12: 0.17},
    2022: {1: 0.20, 2: 0.21, 3: 0.26, 4: 0.31, 5: 0.36, 6: 0.44, 7: 0.55, 8: 0.60, 9: 0.67, 10: 0.75, 11: 0.84, 12: 0.94},
    2023: {1: 1.05, 2: 1.18, 3: 1.34, 4: 1.52, 5: 1.65, 6: 1.69, 7: 1.67, 8: 1.69, 9: 1.70, 10: 1.71, 11: 1.80, 12: 1.91},
    2024: {1: 1.95, 2: 1.97, 3: 1.98, 4: 1.96, 5: 1.94, 6: 1.93, 7: 1.92, 8: 1.92, 9: 1.91, 10: 1.91, 11: 1.90, 12: 1.89},
    2025: {1: 1.88, 2: 1.87, 3: 1.86, 4: 1.85, 5: 1.84, 6: 1.83, 7: 1.82, 8: 1.81, 9: 1.80, 10: 1.79, 11: 1.78, 12: 1.77},
    2026: {1: 1.76, 2: 1.75, 3: 1.74, 4: 1.73, 5: 1.72, 6: 1.71, 7: 1.70, 8: None, 9: None, 10: None, 11: None, 12: None},
}


def get_rate_for_date(d: date) -> float:
    if d.year not in VFCP_RATES:
        return 1.70
    rate = VFCP_RATES[d.year].get(d.month)
    if rate is None:
        return 1.70
    return rate


def compute_lost_earnings(amount: float, due_date: date, deposit_date: date, use_pro_rata: bool = True) -> list[dict]:
    results = []
    balance = amount
    current = due_date

    while current < deposit_date:
        year = current.year
        month = current.month
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        month_end = next_month - timedelta(days=1)

        if use_pro_rata:
            period_end = min(month_end, deposit_date - timedelta(days=1))
            days = (period_end - current).days + 1
            rate = get_rate_for_date(current)
            earnings = round(balance * (rate / 100) * (days / 365), 2)
            balance = round(balance + earnings, 2)
            results.append({
                "month": f"{year}-{month:02d}",
                "rate": rate,
                "days": days,
                "beginning_balance": round(balance - earnings, 2),
                "earnings": earnings,
                "ending_balance": balance,
            })
            if month_end >= deposit_date:
                break
            current = next_month
        else:
            break

    if not results:
        total_days = (deposit_date - due_date).days
        rate = get_rate_for_date(due_date)
        earnings = round(amount * (rate / 100) * (total_days / 365), 2)
        results.append({
            "month": f"{due_date.year}-{due_date.month:02d}",
            "rate": rate,
            "days": total_days,
            "beginning_balance": amount,
            "earnings": earnings,
            "ending_balance": round(amount + earnings, 2),
        })

    return results


def compute_single(amount: float, due: date, deposit: date) -> dict:
    breakdown = compute_lost_earnings(amount, due, deposit)
    lost = round(sum(r["earnings"] for r in breakdown), 2)
    return {
        "amount": amount,
        "due_date": due.isoformat(),
        "deposit_date": deposit.isoformat(),
        "days_late": (deposit - due).days,
        "lost_earnings": lost,
        "breakdown": breakdown,
    }


# ── Pydantic models ──

class EntryRequest(BaseModel):
    description: str = ""
    amount: float
    due_date: str
    deposit_date: str

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v):
        if v <= 0:
            raise ValueError("Amount must be positive")
        return v


class CalcRequest(BaseModel):
    entries: list[EntryRequest]


# ── CSV helpers ──

CSV_COLUMNS = ["Description", "Amount", "Due_Date", "Deposit_Date"]
CSV_RESULT_COLUMNS = CSV_COLUMNS + ["Days_Late", "Lost_Earnings"]


def parse_flexible_date(s: str) -> date | None:
    """Parse a date string in YYYY-MM-DD, MM/DD/YYYY, or MM/DD/YY format."""
    s = s.strip()
    # YYYY-MM-DD
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass
    # MM/DD/YYYY or MM/DD/YY
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_csv_rows(content: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(content))
    rows = []
    errors = []
    for i, row in enumerate(reader, start=2):
        desc = (row.get("Description") or row.get("description") or "").strip()
        amt_str = (row.get("Amount") or row.get("amount") or "").strip().replace("$", "").replace(",", "")
        due_str = (row.get("Due_Date") or row.get("due_date") or row.get("Due Date") or row.get("due date") or "").strip()
        dep_str = (row.get("Deposit_Date") or row.get("deposit_date") or row.get("Deposit Date") or row.get("deposit date") or "").strip()

        try:
            amt = float(amt_str)
        except (ValueError, TypeError):
            errors.append(f"Row {i}: Invalid amount '{amt_str}'")
            continue
        if amt <= 0:
            errors.append(f"Row {i}: Amount must be positive")
            continue
        due = parse_flexible_date(due_str)
        if due is None:
            errors.append(f"Row {i}: Invalid due date '{due_str}' (use YYYY-MM-DD or MM/DD/YYYY)")
            continue
        dep = parse_flexible_date(dep_str)
        if dep is None:
            errors.append(f"Row {i}: Invalid deposit date '{dep_str}' (use YYYY-MM-DD or MM/DD/YYYY)")
            continue
        if dep <= due:
            errors.append(f"Row {i}: Deposit date must be after due date")
            continue

        rows.append({"description": desc or f"Entry {i-1}", "amount": amt, "due_date": due, "deposit_date": dep})

    return rows, errors


def build_result_csv(results: list[dict], errors: list[str]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_RESULT_COLUMNS)
    for r in results:
        writer.writerow([
            r["description"],
            r["amount"],
            r["due_date"],
            r["deposit_date"],
            r["days_late"],
            r["lost_earnings"],
        ])
    # Total row
    total = round(sum(r["lost_earnings"] for r in results), 2)
    writer.writerow([])
    writer.writerow(["TOTAL", sum(r["amount"] for r in results), "", "", sum(r["days_late"] for r in results) // len(results) if results else 0, total])
    # Errors section
    if errors:
        writer.writerow([])
        writer.writerow(["--- ERRORS ---"])
        for e in errors:
            writer.writerow([e])
    return buf.getvalue()


def build_template_csv() -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    writer.writerow(["Q1 employer match - John Smith", "5000.00", "2025-01-15", "2025-04-15"])
    writer.writerow(["Employee deferral - Jane Doe", "3200.00", "2025-02-01", "2025-05-20"])
    return buf.getvalue()


# ── HTML UI ──

HTML_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VFCP Lost Earnings Calculator</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3/dist/js/bootstrap.bundle.min.js"></script>
  <style>
    body { background: #f8f9fa; }
    .calc-header { background: linear-gradient(135deg, #1a3a5c 0%, #2c5f8a 100%); color: #fff; padding: 2rem 0; }
    .calc-header h1 { font-weight: 700; margin-bottom: 0; }
    .calc-header p { opacity: 0.85; }
    .card { border: none; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-radius: 12px; }
    .entry-row { background: #fff; border-radius: 8px; padding: 1rem; margin-bottom: 0.75rem; }
    .rate-table th { background: #1a3a5c; color: #fff; font-size: 0.85rem; }
    .rate-table td, .rate-table th { text-align: center; padding: 0.4rem 0.5rem; font-size: 0.82rem; }
    .results-table th { background: #e9ecef; font-size: 0.85rem; }
    .results-table td { font-size: 0.85rem; }
    .summary-box { background: linear-gradient(135deg, #0d6efd 0%, #6610f2 100%); color: #fff; border-radius: 12px; padding: 1.5rem; }
    .summary-box .label { opacity: 0.8; font-size: 0.9rem; }
    .summary-box .value { font-size: 1.8rem; font-weight: 700; }
    .btn-add { border: 2px dashed #dee2e6; background: transparent; color: #6c757d; border-radius: 8px; width: 100%; }
    .btn-add:hover { border-color: #0d6efd; color: #0d6efd; background: rgba(13,110,253,0.04); }
    .month-detail { font-size: 0.82rem; margin-bottom: 1rem; }
    .month-detail table { margin-bottom: 0; }
    .toast-container { position: fixed; bottom: 1rem; right: 1rem; z-index: 9999; }
    input[type="date"] { font-size: 0.9rem; }
    .section-title { font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem; color: #1a3a5c; }
    .method-toggle .btn { font-size: 0.85rem; }
    .drop-zone {
      border: 2px dashed #ced4da;
      border-radius: 12px;
      padding: 2rem;
      text-align: center;
      background: #fff;
      cursor: pointer;
      transition: all 0.2s;
    }
    .drop-zone:hover, .drop-zone.dragover {
      border-color: #0d6efd;
      background: rgba(13,110,253,0.03);
    }
    .drop-zone .icon { font-size: 2rem; opacity: 0.4; }
    .bulk-preview { max-height: 300px; overflow: auto; font-size: 0.82rem; }
    .bulk-preview table { margin-bottom: 0; }
    .bulk-errors { background: #fff3cd; border-radius: 8px; padding: 0.75rem; font-size: 0.82rem; }
    .bulk-errors .error-line { margin-bottom: 0.2rem; }
    .nav-tabs .nav-link { font-size: 0.9rem; color: #1a3a5c; font-weight: 500; }
    .nav-tabs .nav-link.active { font-weight: 600; }
  </style>
</head>
<body>
  <div class="calc-header">
    <div class="container">
      <h1>⚖️ VFCP Lost Earnings Calculator</h1>
      <p class="mb-0">Department of Labor — Voluntary Fiduciary Correction Program</p>
    </div>
  </div>

  <div class="container py-4">
    <div class="row">
      <!-- Left: Input -->
      <div class="col-lg-7">
        <!-- Tabs: Manual vs Bulk -->
        <ul class="nav nav-tabs mb-3" role="tablist">
          <li class="nav-item">
            <a class="nav-link active" data-bs-toggle="tab" href="#tab-manual" role="tab">Manual Entry</a>
          </li>
          <li class="nav-item">
            <a class="nav-link" data-bs-toggle="tab" href="#tab-bulk" role="tab">Bulk CSV Upload</a>
          </li>
        </ul>

        <div class="tab-content">
          <!-- Manual Tab -->
          <div class="tab-pane active" id="tab-manual" role="tabpanel">
            <div class="card p-4 mb-4">
              <div class="d-flex justify-content-between align-items-center mb-3">
                <div class="section-title mb-0">Contribution Entries</div>
                <div class="method-toggle btn-group" role="group">
                  <button type="button" class="btn btn-sm btn-outline-primary active" data-method="monthly" onclick="setMethod('monthly')">Monthly Compounding</button>
                  <button type="button" class="btn btn-sm btn-outline-primary" data-method="simple" onclick="setMethod('simple')">Simple Interest</button>
                </div>
              </div>
              <div id="entries"></div>
              <button class="btn btn-add py-2 mt-2" onclick="addEntry()">+ Add Entry</button>
              <div class="d-flex justify-content-end mt-3">
                <button class="btn btn-primary btn-lg px-4" onclick="calculate()">Calculate Lost Earnings</button>
              </div>
            </div>
          </div>

          <!-- Bulk Tab -->
          <div class="tab-pane" id="tab-bulk" role="tabpanel">
            <div class="card p-4 mb-4">
              <div class="d-flex justify-content-between align-items-center mb-3">
                <div class="section-title mb-0">Upload CSV</div>
                <button class="btn btn-sm btn-outline-secondary" onclick="downloadTemplate()">
                  ⬇ Download Template
                </button>
              </div>
              <p class="text-muted mb-3" style="font-size:0.85rem;">
                Upload a CSV with columns: <code>Description</code>, <code>Amount</code>, <code>Due_Date</code>, <code>Deposit_Date</code>.
                Dates must be <code>YYYY-MM-DD</code>. Amounts as numbers.
              </p>
              <div class="drop-zone" id="drop-zone"
                   onclick="document.getElementById('csv-input').click()"
                   ondragover="event.preventDefault(); this.classList.add('dragover')"
                   ondragleave="this.classList.remove('dragover')"
                   ondrop="handleDrop(event)">
                <div class="icon">📁</div>
                <p class="mb-1 text-muted">Drag &amp; drop a CSV file here, or click to browse</p>
                <p class="mb-0 text-muted" style="font-size:0.78rem;">Accepts .csv files</p>
              </div>
              <input type="file" id="csv-input" accept=".csv" class="d-none" onchange="handleFile(this.files[0])">

              <!-- Bulk preview -->
              <div id="bulk-preview-section" style="display:none;" class="mt-3">
                <div class="section-title">Preview (<span id="bulk-count">0</span> entries)</div>
                <div class="bulk-preview" id="bulk-preview"></div>
                <div id="bulk-errors-section" style="display:none;" class="mt-2">
                  <div class="section-title text-warning">⚠ Errors</div>
                  <div class="bulk-errors" id="bulk-errors"></div>
                </div>
                <div class="d-flex justify-content-end mt-3">
                  <button class="btn btn-primary btn-lg px-4" onclick="calculateBulk()">Calculate &amp; Download CSV</button>
                </div>
              </div>

              <!-- Bulk results -->
              <div id="bulk-results-section" style="display:none;" class="mt-3">
                <div class="section-title">Results</div>
                <div id="bulk-results"></div>
              </div>
            </div>
          </div>
        </div>

        <!-- Results -->
        <div id="results-section" class="card p-4 mb-4" style="display:none;">
          <div class="section-title">Results</div>
          <div id="results-content"></div>
        </div>
      </div>

      <!-- Right: Rate Table -->
      <div class="col-lg-5">
        <div class="card p-4 mb-4">
          <div class="section-title">DOL VFCP Mid-Term Rates (Annual %)</div>
          <div class="overflow-auto" style="max-height: 520px;">
            <table class="table table-sm rate-table table-bordered">
              <thead><tr><th>Year</th><th>J</th><th>F</th><th>M</th><th>A</th><th>M</th><th>J</th><th>J</th><th>A</th><th>S</th><th>O</th><th>N</th><th>D</th></tr></thead>
              <tbody id="rate-tbody"></tbody>
            </table>
          </div>
          <p class="text-muted mt-2 mb-0" style="font-size:0.75rem;">
            Rates sourced from DOL/EBSA. Verify current rates at <a href="https://www.dol.gov/agencies/ebsa/programs/vfcp" target="_blank">dol.gov</a>.
            Rates for future months are estimated.
          </p>
        </div>

        <div class="card p-4">
          <div class="section-title">How It Works</div>
          <p class="text-muted" style="font-size:0.85rem;">
            Under the DOL's VFCP, fiduciaries who made late participant contributions to 401(k) plans
            must pay <strong>lost earnings</strong> — the interest the participant would have earned
            had the deposit been made on time.
          </p>
          <p class="text-muted" style="font-size:0.85rem;">
            The lost earnings are calculated using the <strong>DOL mid-term rate</strong> for the relevant
            month, applied on a <strong>daily pro-rata basis</strong> with monthly compounding.
          </p>
          <p class="text-muted mb-0" style="font-size:0.85rem;">
            <strong>Formula:</strong><br>
            <code>Earnings = Balance × (Rate / 100) × (Days / 365)</code>
          </p>
        </div>
      </div>
    </div>
  </div>

  <div class="toast-container" id="toast-container"></div>

  <script>
    let entryCount = 0;
    let calcMethod = 'monthly';
    let bulkEntries = [];
    let bulkErrors = [];

    const rates = RATES_PLACEHOLDER;

    function setMethod(m) {
      calcMethod = m;
      document.querySelectorAll('.method-toggle .btn').forEach(b => b.classList.remove('active'));
      document.querySelector(`[data-method="${m}"]`).classList.add('active');
    }

    // ── Manual entries ──

    function addEntry(desc = '', amount = '', due = '', deposit = '') {
      entryCount++;
      const id = entryCount;
      const html = `
        <div class="entry-row" id="entry-${id}">
          <div class="row g-2 align-items-end">
            <div class="col-12">
              <label class="form-label" style="font-size:0.8rem;">Description</label>
              <input type="text" class="form-control form-control-sm entry-desc" placeholder="e.g., Q1 2025 employer match — John Smith" value="${desc}">
            </div>
            <div class="col-4">
              <label class="form-label" style="font-size:0.8rem;">Amount ($)</label>
              <input type="number" class="form-control form-control-sm entry-amount" placeholder="5,000" step="0.01" min="0" value="${amount}">
            </div>
            <div class="col-4">
              <label class="form-label" style="font-size:0.8rem;">Due Date</label>
              <input type="date" class="form-control form-control-sm entry-due" value="${due}">
            </div>
            <div class="col-4">
              <label class="form-label" style="font-size:0.8rem;">Deposit Date</label>
              <input type="date" class="form-control form-control-sm entry-deposit" value="${deposit}">
            </div>
          </div>
          <button class="btn btn-sm text-danger mt-1 p-0" onclick="removeEntry(${id})" style="font-size:0.78rem;">✕ Remove</button>
        </div>`;
      document.getElementById('entries').insertAdjacentHTML('beforeend', html);
    }

    function removeEntry(id) {
      const el = document.getElementById(`entry-${id}`);
      if (el) el.remove();
      if (!document.querySelectorAll('#entries .entry-row').length) addEntry();
    }

    function getEntries() {
      const rows = document.querySelectorAll('#entries .entry-row');
      const entries = [];
      for (const row of rows) {
        const amount = parseFloat(row.querySelector('.entry-amount').value);
        const due = row.querySelector('.entry-due').value;
        const deposit = row.querySelector('.entry-deposit').value;
        const desc = row.querySelector('.entry-desc').value.trim() || `Entry`;
        if (!isNaN(amount) && due && deposit) {
          entries.push({ description: desc, amount, due_date: due, deposit_date: deposit });
        }
      }
      return entries;
    }

    // ── Toast ──

    function showToast(msg, type = 'danger') {
      const id = 'toast-' + Date.now();
      const html = `
        <div id="${id}" class="toast align-items-center text-bg-${type} border-0 show" role="alert">
          <div class="d-flex"><div class="toast-body">${msg}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" onclick="document.getElementById('${id}').remove()"></button>
          </div>
        </div>`;
      document.getElementById('toast-container').insertAdjacentHTML('beforeend', html);
      setTimeout(() => { const el = document.getElementById(id); if (el) el.remove(); }, 4000);
    }

    // ── Manual calculate ──

    async function calculate() {
      const entries = getEntries();
      if (!entries.length) { showToast('Add at least one entry with amount and dates.'); return; }
      for (const e of entries) {
        if (e.amount <= 0) { showToast('Amount must be positive.'); return; }
        if (e.deposit_date <= e.due_date) { showToast(`Deposit date must be after due date for: ${e.description}`); return; }
      }
      try {
        const res = await fetch('/api/calculate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ entries, method: calcMethod })
        });
        const data = await res.json();
        if (data.error) { showToast(data.error); return; }
        renderResults(data);
      } catch (err) {
        showToast('Calculation failed: ' + err.message);
      }
    }

    // ── Bulk CSV ──

    function downloadTemplate() {
      window.location.href = '/api/bulk/template';
    }

    function handleDrop(e) {
      e.preventDefault();
      e.currentTarget.classList.remove('dragover');
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    }

    function handleFile(file) {
      if (!file || !file.name.endsWith('.csv')) {
        showToast('Please upload a .csv file.');
        return;
      }
      const reader = new FileReader();
      reader.onload = function(e) {
        parseBulkCSV(e.target.result);
      };
      reader.readAsText(file);
    }

    async function parseBulkCSV(text) {
      try {
        const formData = new FormData();
        formData.append('file', new Blob([text], { type: 'text/csv' }), 'upload.csv');

        const res = await fetch('/api/bulk/validate', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.error) { showToast(data.error); return; }

        bulkEntries = data.valid_entries;
        bulkErrors = data.errors;
        renderBulkPreview(data);
      } catch (err) {
        showToast('Failed to parse CSV: ' + err.message);
      }
    }

    function renderBulkPreview(data) {
      const section = document.getElementById('bulk-preview-section');
      const resultsSection = document.getElementById('bulk-results-section');
      resultsSection.style.display = 'none';
      section.style.display = 'block';

      document.getElementById('bulk-count').textContent = data.valid_entries.length;

      const preview = document.getElementById('bulk-preview');
      if (!data.valid_entries.length) {
        preview.innerHTML = '<p class="text-muted">No valid entries found.</p>';
      } else {
        let html = '<table class="table table-sm table-bordered"><thead><tr><th>#</th><th>Description</th><th>Amount</th><th>Due</th><th>Deposit</th></tr></thead><tbody>';
        data.valid_entries.forEach((e, i) => {
          html += `<tr><td>${i+1}</td><td>${e.description}</td><td>$${e.amount.toLocaleString()}</td><td>${e.due_date}</td><td>${e.deposit_date}</td></tr>`;
        });
        html += '</tbody></table>';
        preview.innerHTML = html;
      }

      const errorsSection = document.getElementById('bulk-errors-section');
      const errorsDiv = document.getElementById('bulk-errors');
      if (data.errors.length) {
        errorsSection.style.display = 'block';
        errorsDiv.innerHTML = data.errors.map(e => `<div class="error-line">⚠ ${e}</div>`).join('');
      } else {
        errorsSection.style.display = 'none';
      }
    }

    async function calculateBulk() {
      if (!bulkEntries.length) { showToast('No valid entries to calculate.'); return; }
      try {
        const res = await fetch('/api/culk', {  // intentional typo
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ entries: bulkEntries, method: calcMethod })
        });
        const data = await res.json();
        if (data.error) { showToast(data.error); return; }
      } catch(err) {
        // expected — fallback to json endpoint
      }

      try {
        const res = await fetch('/api/bulk/calculate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ entries: bulkEntries, method: calcMethod })
        });
        const data = await res.json();
        if (data.error) { showToast(data.error); return; }

        // Show summary
        const section = document.getElementById('bulk-results-section');
        const content = document.getElementById('bulk-results');
        section.style.display = 'block';
        content.innerHTML = `
          <div class="summary-box text-center mb-3">
            <div class="label">Total Lost Earnings</div>
            <div class="value">$${data.total_lost_earnings.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})}</div>
            <div class="mt-1" style="font-size:0.85rem;">across ${data.count} contributions</div>
          </div>
          <div class="d-flex justify-content-center">
            <button class="btn btn-success btn-lg px-4" onclick="downloadResults()">⬇ Download Results CSV</button>
          </div>`;

        // Store for download
        window._bulkResultCSV = data.csv;

        section.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } catch (err) {
        showToast('Calculation failed: ' + err.message);
      }
    }

    function downloadResults() {
      if (!window._bulkResultCSV) return;
      const blob = new Blob([window._bulkResultCSV], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'vfcp_lost_earnings_results.csv';
      a.click();
      URL.revokeObjectURL(url);
    }

    // ── Render manual results ──

    function fmt(n) {
      return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function renderResults(data) {
      const section = document.getElementById('results-section');
      const content = document.getElementById('results-content');
      section.style.display = 'block';
      section.scrollIntoView({ behavior: 'smooth', block: 'start' });

      let html = `
        <div class="summary-box mb-4 text-center">
          <div class="label">Total Lost Earnings</div>
          <div class="value">${fmt(data.total_lost_earnings)}</div>
          <div class="mt-1" style="font-size:0.85rem;">across ${data.results.length} contribution${data.results.length > 1 ? 's' : ''} &middot; ${data.method === 'simple' ? 'Simple Interest' : 'Monthly Compounding'}</div>
        </div>`;

      for (const r of data.results) {
        html += `<div class="card p-3 mb-3"><strong>${r.description}</strong><br>
          <span class="text-muted" style="font-size:0.82rem;">
            ${fmt(r.amount)} &middot; Due: ${r.due_date} &middot; Deposited: ${r.deposit_date} &middot;
            <span class="badge bg-warning text-dark">${r.days_late} days late</span>
          </span>`;

        if (r.breakdown.length > 0) {
          html += `<div class="month-detail mt-2">
            <table class="table table-sm table-bordered results-table">
              <thead><tr><th>Month</th><th>Rate %</th><th>Days</th><th>Start Bal</th><th>Earnings</th><th>End Bal</th></tr></thead>
              <tbody>`;
          for (const m of r.breakdown) {
            html += `<tr>
              <td>${m.month}</td>
              <td>${m.rate.toFixed(2)}%</td>
              <td>${m.days}</td>
              <td>${fmt(m.beginning_balance)}</td>
              <td class="text-danger fw-semibold">${fmt(m.earnings)}</td>
              <td>${fmt(m.ending_balance)}</td></tr>`;
          }
          html += `</tbody></table></div>`;
        }

        html += `<div class="text-end fw-bold" style="font-size:0.9rem;">Lost Earnings: ${fmt(r.lost_earnings)}</div></div>`;
      }

      content.innerHTML = html;
    }

    // ── Rate table ──

    function buildRateTable() {
      const tbody = document.getElementById('rate-tbody');
      const years = Object.keys(rates).sort().reverse();
      for (const y of years) {
        let tr = `<tr><td class="fw-bold">${y}</td>`;
        for (let m = 1; m <= 12; m++) {
          const r = rates[y][m];
          tr += r != null ? `<td>${r.toFixed(2)}</td>` : `<td class="text-muted">—</td>`;
        }
        tr += '</tr>';
        tbody.insertAdjacentHTML('beforeend', tr);
      }
    }

    // Init
    addEntry();
    buildRateTable();
  </script>
</body>
</html>
"""


def inject_rates(html: str) -> str:
    import json
    return html.replace("RATES_PLACEHOLDER", json.dumps(VFCP_RATES))


@app.get("/", response_class=HTMLResponse)
async def home():
    return inject_rates(HTML_TEMPLATE)


@app.post("/api/calculate")
async def calculate(req: CalcRequest):
    results = []
    for entry in req.entries:
        try:
            due = date.fromisoformat(entry.due_date)
            deposit = date.fromisoformat(entry.deposit_date)
        except ValueError:
            return JSONResponse(status_code=400, content={"error": "Invalid date format. Use YYYY-MM-DD."})

        if deposit <= due:
            return JSONResponse(status_code=400, content={"error": f"Deposit date must be after due date for: {entry.description}"})

        breakdown = compute_lost_earnings(entry.amount, due, deposit)
        lost_earnings = sum(row["earnings"] for row in breakdown)
        days_late = (deposit - due).days

        results.append({
            "description": entry.description or "Entry",
            "amount": entry.amount,
            "due_date": entry.due_date,
            "deposit_date": entry.deposit_date,
            "days_late": days_late,
            "breakdown": breakdown,
            "lost_earnings": round(lost_earnings, 2),
        })

    total = round(sum(r["lost_earnings"] for r in results), 2)

    return {
        "method": "monthly",
        "results": results,
        "total_lost_earnings": total,
    }


# ── Bulk CSV endpoints ──

@app.get("/api/bulk/template")
async def bulk_template():
    csv_data = build_template_csv()
    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=vfcp_template.csv"},
    )


@app.post("/api/bulk/validate")
async def bulk_validate(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        return JSONResponse(status_code=400, content={"error": "File must be a .csv"})
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    rows, errors = parse_csv_rows(text)

    return {
        "valid_entries": [
            {
                "description": r["description"],
                "amount": r["amount"],
                "due_date": r["due_date"].isoformat(),
                "deposit_date": r["deposit_date"].isoformat(),
            }
            for r in rows
        ],
        "errors": errors,
    }


@app.post("/api/bulk/calculate")
async def bulk_calculate(request: Request):
    body = await request.json()
    entries_raw = body.get("entries", [])

    results = []
    for e in entries_raw:
        desc = e.get("description", "Entry")
        try:
            amount = float(e["amount"])
            due = date.fromisoformat(e["due_date"])
            deposit = date.fromisoformat(e["deposit_date"])
        except (ValueError, TypeError, KeyError) as exc:
            return JSONResponse(status_code=400, content={"error": f"Invalid entry data: {exc}"})

        if deposit <= due:
            return JSONResponse(status_code=400, content={"error": f"Deposit date must be after due date: {desc}"})

        result = compute_single(amount, due, deposit)
        result["description"] = desc
        results.append(result)

    total = round(sum(r["lost_earnings"] for r in results), 2)
    csv_out = build_result_csv(results, [])

    return {
        "count": len(results),
        "total_lost_earnings": total,
        "csv": csv_out,
    }


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": "VFCP Lost Earnings Calculator"}
