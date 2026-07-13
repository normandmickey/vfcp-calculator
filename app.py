import csv
import io
import math
from fastapi import FastAPI, Request, UploadFile, File, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, field_validator
from datetime import date, datetime, timedelta
from typing import Optional

app = FastAPI(title="VFCP Lost Earnings Calculator")

# ── DOL VFCP Interest Rates (annual %) ──
# Source: DOL Interest Rate Tables for VFCP
# Two columns per quarter: mid-term rate, high rate.
# VFCP lost earnings use the mid-term rate (first column).
# Rates are quarterly (Jan–Mar, Apr–Jun, Jul–Sep, Oct–Dec).
VFCP_RATES = {}

# (year, quarter): (mid_term_rate, high_rate)
# Quarter 1=Jan–Mar, 2=Apr–Jun, 3=Jul–Sep, 4=Oct–Dec
DOL_RATE_TABLE = {
    (2026, 1): (7, 9),
    (2026, 2): (6, 8),
    (2026, 3): (7, 9),
    (2025, 4): (7, 9),
    (2025, 3): (7, 9),
    (2025, 2): (7, 9),
    (2025, 1): (7, 9),
    (2024, 4): (8, 10),
    (2024, 3): (8, 10),
    (2024, 2): (8, 10),
    (2024, 1): (8, 10),
    (2023, 4): (8, 10),
    (2023, 3): (7, 9),
    (2023, 2): (7, 9),
    (2023, 1): (7, 9),
    (2022, 4): (6, 8),
    (2022, 3): (5, 7),
    (2022, 2): (4, 6),
    (2022, 1): (3, 5),
    (2021, 4): (3, 5),
    (2021, 3): (3, 5),
    (2021, 2): (3, 5),
    (2021, 1): (3, 5),
    (2020, 4): (3, 5),
    (2020, 3): (3, 5),
    (2020, 2): (5, 7),
    (2020, 1): (5, 7),
    (2019, 4): (5, 7),
    (2019, 3): (5, 7),
    (2019, 2): (6, 8),
    (2019, 1): (6, 8),
    (2018, 4): (5, 7),
    (2018, 3): (5, 7),
    (2018, 2): (5, 7),
    (2018, 1): (4, 6),
    (2017, 4): (4, 6),
    (2017, 3): (4, 6),
    (2017, 2): (4, 6),
    (2017, 1): (4, 6),
    (2016, 4): (4, 6),
    (2016, 3): (4, 6),
    (2016, 2): (4, 6),
    (2016, 1): (3, 5),
    (2015, 4): (3, 5),
    (2015, 3): (3, 5),
    (2015, 2): (3, 5),
    (2015, 1): (3, 5),
    (2014, 4): (3, 5),
    (2014, 3): (3, 5),
    (2014, 2): (3, 5),
    (2014, 1): (3, 5),
    (2013, 4): (3, 5),
    (2013, 3): (3, 5),
    (2013, 2): (3, 5),
    (2013, 1): (3, 5),
    (2012, 4): (3, 5),
    (2012, 3): (3, 5),
    (2012, 2): (3, 5),
    (2012, 1): (3, 5),
    (2011, 4): (3, 5),
    (2011, 3): (4, 6),
    (2011, 2): (4, 6),
    (2011, 1): (3, 5),
    (2010, 4): (4, 6),
    (2010, 3): (4, 6),
    (2010, 2): (4, 6),
    (2010, 1): (4, 6),
    (2009, 4): (4, 6),
    (2009, 3): (4, 6),
    (2009, 2): (4, 6),
    (2009, 1): (5, 7),
    (2008, 4): (6, 8),
    (2008, 3): (5, 7),
    (2008, 2): (6, 8),
    (2008, 1): (7, 9),
    (2007, 4): (8, 10),
    (2007, 3): (8, 10),
    (2007, 2): (8, 10),
    (2007, 1): (8, 10),
    (2006, 4): (8, 10),
    (2006, 3): (8, 10),
    (2006, 2): (7, 9),
    (2006, 1): (7, 9),
    (2005, 4): (7, 9),
    (2005, 3): (6, 8),
    (2005, 2): (6, 8),
    (2005, 1): (5, 7),
    (2004, 4): (5, 7),
    (2004, 3): (4, 6),
    (2004, 2): (5, 7),
    (2004, 1): (4, 6),
    (2003, 4): (4, 6),
    (2003, 3): (5, 7),
    (2003, 2): (5, 7),
    (2003, 1): (5, 7),
    (2002, 4): (6, 8),
    (2002, 3): (6, 8),
    (2002, 2): (6, 8),
    (2002, 1): (6, 8),
    (2001, 4): (7, 9),
    (2001, 3): (7, 9),
    (2001, 2): (8, 10),
    (2001, 1): (9, 11),
    (2000, 4): (9, 11),
    (2000, 3): (9, 11),
    (2000, 2): (9, 11),
    (2000, 1): (8, 10),
    (1999, 4): (8, 10),
    (1999, 3): (8, 10),
    (1999, 2): (8, 10),
    (1999, 1): (7, 9),
    (1998, 4): (8, 10),
    (1998, 3): (8, 10),
    (1998, 2): (8, 10),
    (1998, 1): (9, 11),
    (1997, 4): (9, 11),
    (1997, 3): (9, 11),
    (1997, 2): (9, 11),
    (1997, 1): (9, 11),
    (1996, 4): (9, 11),
    (1996, 3): (9, 11),
    (1996, 2): (8, 10),
    (1996, 1): (9, 11),
    (1995, 4): (9, 11),
    (1995, 3): (9, 11),
    (1995, 2): (10, 12),
    (1995, 1): (9, 11),
    (1994, 4): (9, 11),
    (1994, 3): (8, 10),
    (1994, 2): (7, 9),
    (1994, 1): (7, 9),
    (1993, 4): (7, 9),
    (1993, 3): (7, 9),
    (1993, 2): (7, 9),
    (1993, 1): (7, 9),
    (1992, 4): (7, 9),
    (1992, 3): (8, 10),
    (1992, 2): (8, 10),
    (1992, 1): (9, 11),
    (1991, 4): (10, 12),
    (1991, 3): (10, 12),
    (1991, 2): (10, 12),
    (1991, 1): (11, 13),
    (1990, 4): (11, None),
    (1990, 3): (11, None),
    (1990, 2): (11, None),
    (1990, 1): (11, None),
}


def _build_vfcp_rates():
    """Expand quarterly rates into per-month lookup."""
    rates = {}
    for (year, quarter), (mid, _high) in DOL_RATE_TABLE.items():
        for m_off in range(3):
            m = quarter * 3 - 3 + m_off + 1  # Q1→1,2,3; Q2→4,5,6; etc.
            if year not in rates:
                rates[year] = {}
            rates[year][m] = float(mid)
    return rates


VFCP_RATES = _build_vfcp_rates()


def get_rate_for_date(d: date) -> float:
    """Return the DOL mid-term interest rate for a given date, or None if unavailable."""
    # Check pre-built monthly lookup first
    if d.year in VFCP_RATES and d.month in VFCP_RATES[d.year]:
        return VFCP_RATES[d.year][d.month]
    # Fall back to quarter lookup
    quarter = (d.month - 1) // 3 + 1
    entry = DOL_RATE_TABLE.get((d.year, quarter))
    if entry is None:
        return None
    return float(entry[0])


def lost_earnings_factor(days: int, annual_rate: float) -> float:
    """
    Simple interest factor: (days / 365) * (rate / 100)
    """
    return (days / 365.0) * (annual_rate / 100.0)


def compute_lost_earnings(
    amount: float,
    due_date: date,
    deposit_date: date,
    final_payment_date: Optional[date] = None,
    use_compounding: bool = False,
) -> list[dict]:
    """
    Compute VFCP lost earnings using simple interest.

    Interest accrues from due_date through the final payment date (inclusive).
    If no final_payment_date is given, deposit_date is used as the end date.

    Formula: Amount × (days / 365) × (rate / 100)
    Each month is computed separately with that month's rate.
    By default uses simple interest (no compounding), matching DOL methodology.
    """
    if final_payment_date is None:
        final_payment_date = deposit_date

    results = []
    balance = amount
    current = due_date

    while current <= final_payment_date:
        year = current.year
        month = current.month
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        month_end = next_month - timedelta(days=1)

        period_end = min(month_end, final_payment_date)
        days = (period_end - current).days + 1
        rate = get_rate_for_date(current)

        if rate is None:
            # No published rate for this month — skip and note it
            results.append({
                "month": f"{year}-{month:02d}",
                "rate": None,
                "days": days,
                "beginning_balance": round(balance, 2),
                "earnings": 0.0,
                "ending_balance": round(balance, 2),
                "note": "No rate available",
            })
            if month_end >= final_payment_date:
                break
            current = next_month
            continue

        factor = lost_earnings_factor(days, rate)
        earnings = round(balance * factor, 2)

        if use_compounding:
            balance = round(balance + earnings, 2)
            results.append({
                "month": f"{year}-{month:02d}",
                "rate": rate,
                "days": days,
                "factor": factor,
                "beginning_balance": round(balance - earnings, 2),
                "earnings": earnings,
                "ending_balance": balance,
            })
        else:
            # Simple interest: always on original amount, no compounding
            total_earnings = sum(r["earnings"] for r in results)
            results.append({
                "month": f"{year}-{month:02d}",
                "rate": rate,
                "days": days,
                "factor": factor,
                "beginning_balance": amount,
                "earnings": earnings,
                "ending_balance": round(amount + total_earnings + earnings, 2),
            })

        if month_end >= final_payment_date:
            break
        current = next_month

    return results


def compute_single(
    amount: float,
    due: date,
    deposit: date,
    final_payment: Optional[date] = None,
    use_compounding: bool = True,
) -> dict:
    breakdown = compute_lost_earnings(amount, due, deposit, final_payment_date=final_payment, use_compounding=use_compounding)
    lost = round(sum(r["earnings"] for r in breakdown), 2)
    end_date = final_payment or deposit
    return {
        "amount": amount,
        "due_date": due.isoformat(),
        "deposit_date": deposit.isoformat(),
        "final_payment_date": end_date.isoformat() if final_payment else None,
        "days_late": (end_date - due).days,
        "lost_earnings": lost,
        "breakdown": breakdown,
    }


# ── Pydantic models ──

class EntryRequest(BaseModel):
    description: str = ""
    amount: float
    due_date: str
    deposit_date: str
    final_payment_date: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v):
        if v <= 0:
            raise ValueError("Amount must be positive")
        return v


class CalcRequest(BaseModel):
    entries: list[EntryRequest]
    method: str = "monthly"


# ── CSV helpers ──

CSV_COLUMNS = ["Description", "Amount", "Due_Date", "Deposit_Date", "Final_Payment_Date"]
CSV_RESULT_COLUMNS = CSV_COLUMNS + ["Days_Late", "Lost_Earnings"]


def parse_flexible_date(s: str) -> date | None:
    """Parse a date string in YYYY-MM-DD, MM/DD/YYYY, or MM/DD/YY format."""
    s = s.strip()
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_csv_rows(content: str) -> tuple[list[dict], list[str]]:
    reader = csv.DictReader(io.StringIO(content))
    rows = []
    errors = []
    for i, row in enumerate(reader, start=2):
        desc = (row.get("Description") or row.get("description") or "").strip()
        amt_str = (row.get("Amount") or row.get("amount") or "").strip().replace("$", "").replace(",", "")
        due_str = (row.get("Due_Date") or row.get("due_date") or row.get("Due Date") or row.get("due date") or "").strip()
        dep_str = (row.get("Deposit_Date") or row.get("deposit_date") or row.get("Deposit Date") or row.get("deposit date") or "").strip()
        fp_str = (row.get("Final_Payment_Date") or row.get("final_payment_date") or row.get("Final Payment Date") or "").strip()

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

        fp = parse_flexible_date(fp_str) if fp_str else None

        rows.append({
            "description": desc or f"Entry {i-1}",
            "amount": amt,
            "due_date": due,
            "deposit_date": dep,
            "final_payment_date": fp,
        })

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
            r.get("final_payment_date", ""),
            r["days_late"],
            r["lost_earnings"],
        ])
    total = round(sum(r["lost_earnings"] for r in results), 2)
    writer.writerow([])
    writer.writerow(["TOTAL", sum(r["amount"] for r in results), "", "", "", sum(r["days_late"] for r in results) // len(results) if results else 0, total])
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
    writer.writerow(["Q1 employer match - John Smith", "5000.00", "2025-01-15", "2025-04-15", ""])
    writer.writerow(["Employee deferral - Jane Doe", "3200.00", "2025-02-01", "2025-05-20", "2025-05-20"])
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
    .fp-field { max-width: 140px; }
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
              <div class="mb-3">
                <div class="section-title mb-0">Contribution Entries</div>
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
                Upload a CSV with columns: <code>Description</code>, <code>Amount</code>, <code>Due_Date</code>, <code>Deposit_Date</code>,
                <code>Final_Payment_Date</code> (optional, defaults to Deposit_Date).
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
          <div class="section-title">DOL VFCP Interest Rates (Annual %)</div>
          <p class="text-muted mb-2" style="font-size:0.78rem;">
            Source: DOL Interest Rate Table for VFCP · Mid-term / High rate per quarter
          </p>
          <div class="overflow-auto" style="max-height: 520px;">
            <table class="table table-sm rate-table table-bordered">
              <thead><tr><th>Period</th><th>Mid-term</th><th>High</th></tr></thead>
              <tbody id="rate-tbody"></tbody>
            </table>
          </div>
        </div>

        <div class="card p-4">
          <div class="section-title">How It Works</div>
          <p class="text-muted" style="font-size:0.85rem;">
            Under the DOL's VFCP, fiduciaries who made late participant contributions to 401(k) plans
            must pay <strong>lost earnings</strong> — the interest the participant would have earned
            had the deposit been made on time.
          </p>
          <p class="text-muted" style="font-size:0.85rem;">
            The lost earnings are calculated using the <strong>DOL mid-term rate</strong> (5-Year CMT)
            for the relevant month, applied as simple interest. Interest accrues from the
            <strong>Loss Date</strong> through the <strong>Final Payment Date</strong> (inclusive).
          </p>
          <p class="text-muted mb-0" style="font-size:0.85rem;">
            <strong>Formula:</strong><br>
            <code>Lost Earnings = Amount × (Days / 365) × (Rate / 100)</code>
          </p>
        </div>
      </div>
    </div>
  </div>

  <div class="toast-container" id="toast-container"></div>

  <script>
    let entryCount = 0;
    let bulkEntries = [];
    let bulkErrors = [];

    

    // ── Manual entries ──

    function addEntry(desc = '', amount = '', due = '', deposit = '', fp = '') {
      entryCount++;
      const id = entryCount;
      const html = `
        <div class="entry-row" id="entry-${id}">
          <div class="row g-2 align-items-end">
            <div class="col-12">
              <label class="form-label" style="font-size:0.8rem;">Description</label>
              <input type="text" class="form-control form-control-sm entry-desc" placeholder="e.g., Q1 2025 employer match — John Smith" value="${desc}">
            </div>
            <div class="col-sm-4 col-6">
              <label class="form-label" style="font-size:0.8rem;">Amount ($)</label>
              <input type="number" class="form-control form-control-sm entry-amount" placeholder="5,000" step="0.01" min="0" value="${amount}">
            </div>
            <div class="col-sm-4 col-6">
              <label class="form-label" style="font-size:0.8rem;">Loss Date</label>
              <input type="date" class="form-control form-control-sm entry-due" value="${due}">
            </div>
            <div class="col-sm-4 col-6">
              <label class="form-label" style="font-size:0.8rem;">Recovery Date</label>
              <input type="date" class="form-control form-control-sm entry-deposit" value="${deposit}">
            </div>
            <div class="col-sm-4 col-6">
              <label class="form-label" style="font-size:0.8rem;">Final Payment Date <span class="text-muted" style="font-size:0.7rem;">(optional)</span></label>
              <input type="date" class="form-control form-control-sm entry-fp fp-field" value="${fp}" placeholder="Same as Recovery">
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
        const fp = row.querySelector('.entry-fp').value;
        const desc = row.querySelector('.entry-desc').value.trim() || `Entry`;
        if (!isNaN(amount) && due && deposit) {
          const entry = { description: desc, amount, due_date: due, deposit_date: deposit };
          if (fp) entry.final_payment_date = fp;
          entries.push(entry);
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
          body: JSON.stringify({ entries, method: 'simple' })
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
      if (!file || !file.name.endsWith(".csv")) {
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
        let html = '<table class="table table-sm table-bordered"><thead><tr><th>#</th><th>Description</th><th>Amount</th><th>Due</th><th>Deposit</th><th>Final Pay</th></tr></thead><tbody>';
        data.valid_entries.forEach((e, i) => {
          html += `<tr><td>${i+1}</td><td>${e.description}</td><td>$${e.amount.toLocaleString()}</td><td>${e.due_date}</td><td>${e.deposit_date}</td><td>${e.final_payment_date || '—'}</td></tr>`;
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
        const res = await fetch('/api/bulk/calculate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ entries: bulkEntries, method: 'simple' })
        });
        const data = await res.json();
        if (data.error) { showToast(data.error); return; }

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
          <div class="mt-1" style="font-size:0.85rem;">across ${data.results.length} contribution${data.results.length > 1 ? 's' : ''} &middot; Simple Interest</div>
        </div>`;

      for (const r of data.results) {
        html += `<div class="card p-3 mb-3"><strong>${r.description}</strong><br>
          <span class="text-muted" style="font-size:0.82rem;">
            ${fmt(r.amount)} &middot; Loss: ${r.due_date} &middot; Recovery: ${r.deposit_date}`;
        if (r.final_payment_date && r.final_payment_date !== r.deposit_date) {
          html += ` &middot; Final Payment: ${r.final_payment_date}`;
        }
        html += ` &middot;
            <span class="badge bg-warning text-dark">${r.days_late} days</span>
          </span>`;

        if (r.breakdown.length > 0) {
          html += `<div class="month-detail mt-2">
            <table class="table table-sm table-bordered results-table">
              <thead><tr><th>Month</th><th>Rate %</th><th>Days</th><th>Factor</th><th>Start Bal</th><th>Earnings</th><th>End Bal</th></tr></thead>
              <tbody>`;
          for (const m of r.breakdown) {
            const rateStr = m.rate != null ? m.rate.toFixed(2) + '%' : 'N/A';
            const noteStr = m.note ? ` <span class="text-muted">(${m.note})</span>` : '';
            const factorStr = m.factor != null ? m.factor.toFixed(6) : '—';
            html += `<tr>
              <td>${m.month}</td>
              <td>${rateStr}${noteStr}</td>
              <td>${m.days}</td>
              <td>${factorStr}</td>
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
      const quarters = RATE_TABLE_PLACEHOLDER;
      const qLabels = {1: 'Jan 1 – Mar 31', 2: 'Apr 1 – Jun 30', 3: 'Jul 1 – Sep 30', 4: 'Oct 1 – Dec 31'};
      // Sort newest first, within year Q4 first
      quarters.sort((a, b) => {
        if (a[0] !== b[0]) return b[0] - a[0];
        return b[1] - a[1];
      });
      for (const [year, q, mid, high] of quarters) {
        const label = qLabels[q] || `Q${q}`;
        const period = `${label}, ${year}`;
        const highStr = high != null ? `${high}%` : 'N/A';
        const tr = document.createElement('tr');
        tr.innerHTML = `<td class="text-start">${period}</td><td>${mid}%</td><td>${highStr}</td>`;
        tbody.appendChild(tr);
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
    # Build list of [year, quarter, mid, high] for JS
    table_data = [[y, q, mid, hi] for (y, q), (mid, hi) in DOL_RATE_TABLE.items()]
    return html.replace("RATE_TABLE_PLACEHOLDER", json.dumps(table_data))


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

        final_payment = None
        if entry.final_payment_date:
            try:
                final_payment = date.fromisoformat(entry.final_payment_date)
            except ValueError:
                return JSONResponse(status_code=400, content={"error": "Invalid final payment date format. Use YYYY-MM-DD."})

        if deposit <= due:
            return JSONResponse(status_code=400, content={"error": f"Deposit date must be after due date for: {entry.description}"})

        use_compounding = req.method != "simple"
        breakdown = compute_lost_earnings(entry.amount, due, deposit, final_payment_date=final_payment, use_compounding=use_compounding)
        lost_earnings = sum(row["earnings"] for row in breakdown)
        end_date = final_payment or deposit
        days_late = (end_date - due).days

        results.append({
            "description": entry.description or "Entry",
            "amount": entry.amount,
            "due_date": entry.due_date,
            "deposit_date": entry.deposit_date,
            "final_payment_date": final_payment.isoformat() if final_payment else None,
            "days_late": days_late,
            "breakdown": breakdown,
            "lost_earnings": round(lost_earnings, 2),
        })

    total = round(sum(r["lost_earnings"] for r in results), 2)

    return {
        "method": req.method,
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
                "final_payment_date": r["final_payment_date"].isoformat() if r["final_payment_date"] else None,
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

        final_payment = None
        if e.get("final_payment_date"):
            try:
                final_payment = date.fromisoformat(e["final_payment_date"])
            except ValueError:
                return JSONResponse(status_code=400, content={"error": f"Invalid final payment date for: {desc}"})

        use_compounding = body.get("method", "monthly") != "simple"
        result = compute_single(amount, due, deposit, final_payment=final_payment, use_compounding=use_compounding)
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
    return {"status": "ok", "app": "VFCP Lost Earnings Calculator", "methodology": "Simple Interest"}
