import csv
import io
import math
from openpyxl import load_workbook
from xlrd import open_workbook as xlrd_open_workbook
from fastapi import FastAPI, Request, UploadFile, File, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, field_validator, model_validator
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


def get_rate_for_date(d: date, rate_type: str = "employee") -> float:
    """Return the DOL interest rate for a given date.
    rate_type: "employee" uses mid-term rate, "employer" uses high rate.
    Returns None if unavailable.
    """
    quarter = (d.month - 1) // 3 + 1
    entry = DOL_RATE_TABLE.get((d.year, quarter))
    if entry is None:
        return None
    mid, high = entry
    if rate_type == "employer" and high is not None:
        return float(high)
    return float(mid)


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
    rate_type: str = "employee",
) -> list[dict]:
    """
    Compute VFCP lost earnings using simple interest.

    Interest accrues from due_date through the final payment date (inclusive).
    If no final_payment_date is given, deposit_date is used as the end date.

    Formula: Amount × (days / 365) × (rate / 100)
    Each month is computed separately with that month's rate.
    By default uses simple interest (no compounding), matching DOL methodology.
    rate_type: "employee" uses mid-term rate, "employer" uses high rate.
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
        rate = get_rate_for_date(current, rate_type=rate_type)

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
    employee_amount: float = 0.0
    employer_amount: float = 0.0
    loan_amount: float = 0.0
    due_date: str
    deposit_date: str
    final_payment_date: Optional[str] = None

    @field_validator("employee_amount", "employer_amount", "loan_amount")
    @classmethod
    def amounts_non_negative(cls, v):
        if v < 0:
            raise ValueError("Amounts must be non-negative")
        return v

    @model_validator(mode="after")
    def at_least_one_amount(self):
        if self.employee_amount <= 0 and self.employer_amount <= 0 and self.loan_amount <= 0:
            raise ValueError("Enter at least one amount (employee deferral, employer match, or loan repayment)")
        return self


class CalcRequest(BaseModel):
    entries: list[EntryRequest]
    method: str = "monthly"


# ── CSV helpers ──

CSV_COLUMNS = ["Description", "Employee_Amount", "Employer_Amount", "Loan_Amount", "Due_Date", "Deposit_Date", "Final_Payment_Date"]
CSV_RESULT_COLUMNS = CSV_COLUMNS + ["Contribution_Type", "Days_Late", "Lost_Earnings"]


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
        emp_str = (row.get("Employee_Amount") or row.get("employee_amount") or row.get("Employee Amount") or "").strip().replace("$", "").replace(",", "")
        er_str = (row.get("Employer_Amount") or row.get("employer_amount") or row.get("Employer Amount") or "").strip().replace("$", "").replace(",", "")
        loan_str = (row.get("Loan_Amount") or row.get("loan_amount") or row.get("Loan Amount") or "").strip().replace("$", "").replace(",", "")
        due_str = (row.get("Due_Date") or row.get("due_date") or row.get("Due Date") or row.get("due date") or "").strip()
        dep_str = (row.get("Deposit_Date") or row.get("deposit_date") or row.get("Deposit Date") or row.get("deposit date") or "").strip()
        fp_str = (row.get("Final_Payment_Date") or row.get("final_payment_date") or row.get("Final Payment Date") or "").strip()

        try:
            emp_amt = float(emp_str) if emp_str else 0.0
        except (ValueError, TypeError):
            errors.append(f"Row {i}: Invalid employee amount '{emp_str}'")
            continue
        try:
            er_amt = float(er_str) if er_str else 0.0
        except (ValueError, TypeError):
            errors.append(f"Row {i}: Invalid employer amount '{er_str}'")
            continue
        try:
            loan_amt = float(loan_str) if loan_str else 0.0
        except (ValueError, TypeError):
            errors.append(f"Row {i}: Invalid loan amount '{loan_str}'")
            continue
        if emp_amt < 0 or er_amt < 0 or loan_amt < 0:
            errors.append(f"Row {i}: Amounts must be non-negative")
            continue
        if emp_amt <= 0 and er_amt <= 0 and loan_amt <= 0:
            errors.append(f"Row {i}: Enter at least one amount (employee, employer, or loan)")
            continue
        due = parse_flexible_date(due_str)
        if due is None:
            errors.append(f"Row {i}: Invalid due date '{due_str}' (use YYYY-MM-DD or MM/DD/YYYY)")
            continue
        dep = parse_flexible_date(dep_str)
        if dep is None:
            errors.append(f"Row {i}: Invalid deposit date '{dep_str}' (use YYYY-MM-DD or MM/DD/YYYY)")
            continue
        fp = parse_flexible_date(fp_str) if fp_str else None

        rows.append({
            "description": desc or f"Entry {i-1}",
            "employee_amount": emp_amt,
            "employer_amount": er_amt,
            "loan_amount": loan_amt,
            "due_date": due,
            "deposit_date": dep,
            "final_payment_date": fp,
        })

    return rows, errors


def parse_excel_rows(content: bytes, filename: str) -> tuple[list[dict], list[str]]:
    """Parse an .xlsx (openpyxl) or .xls (xlrd) file and return rows matching the CSV schema."""
    rows = []
    errors = []

    if filename.lower().endswith(".xls"):
        # Legacy .xls via xlrd
        wb = xlrd_open_workbook(file_contents=content)
        ws = wb.sheet_by_index(0)
        headers = [str(ws.cell_value(0, c)).strip() for c in range(ws.ncols)]
        for i in range(1, ws.nrows):
            raw = {headers[c]: str(ws.cell_value(i, c)).strip() for c in range(ws.ncols)}
            row, errs = _parse_single_row(raw, i + 2)
            rows.extend(row)
            errors.extend(errs)
    else:
        # Modern .xlsx via openpyxl
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        try:
            headers = [str(h).strip() if h is not None else "" for h in next(rows_iter)]
        except StopIteration:
            wb.close()
            return rows, ["Excel file is empty (no header row)"]
        for idx, raw_vals in enumerate(rows_iter, start=2):
            raw = {}
            for c, h in enumerate(headers):
                if c < len(raw_vals) and raw_vals[c] is not None:
                    val = raw_vals[c]
                    if isinstance(val, (int, float)):
                        raw[h] = str(val)
                    else:
                        raw[h] = str(val).strip()
                else:
                    raw[h] = ""
            row, errs = _parse_single_row(raw, idx)
            rows.extend(row)
            errors.extend(errs)
        wb.close()

    return rows, errors


def _parse_single_row(raw: dict, line_num: int) -> tuple[list[dict], list[str]]:
    """Parse one raw row dict into validated entries. Returns (rows, errors)."""
    rows = []
    errors = []

    def _get(*keys):
        for k in keys:
            v = raw.get(k, "") or raw.get(k.lower(), "") or raw.get(k.replace("_", " "), "") or ""
            if v:
                return v.strip()
        return ""

    desc = _get("Description", "description")
    emp_str = _get("Employee_Amount", "employee_amount", "Employee Amount").replace("$", "").replace(",", "")
    er_str = _get("Employer_Amount", "employer_amount", "Employer Amount").replace("$", "").replace(",", "")
    loan_str = _get("Loan_Amount", "loan_amount", "Loan Amount").replace("$", "").replace(",", "")
    due_str = _get("Due_Date", "due_date", "Due Date", "due date")
    dep_str = _get("Deposit_Date", "deposit_date", "Deposit Date", "deposit date")
    fp_str = _get("Final_Payment_Date", "final_payment_date", "Final Payment Date")

    # Handle Excel numeric dates (days since 1900 or 1904 epoch)
    def _coerce_date(val):
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            try:
                return _excel_number_to_date(val)
            except (ValueError, OverflowError):
                return None
        return parse_flexible_date(str(val))

    try:
        emp_amt = float(emp_str) if emp_str else 0.0
    except (ValueError, TypeError):
        errors.append(f"Row {line_num}: Invalid employee amount '{emp_str}'")
        return rows, errors
    try:
        er_amt = float(er_str) if er_str else 0.0
    except (ValueError, TypeError):
        errors.append(f"Row {line_num}: Invalid employer amount '{er_str}'")
        return rows, errors
    try:
        loan_amt = float(loan_str) if loan_str else 0.0
    except (ValueError, TypeError):
        errors.append(f"Row {line_num}: Invalid loan amount '{loan_str}'")
        return rows, errors

    if emp_amt < 0 or er_amt < 0 or loan_amt < 0:
        errors.append(f"Row {line_num}: Amounts must be non-negative")
        return rows, errors
    if emp_amt <= 0 and er_amt <= 0 and loan_amt <= 0:
        errors.append(f"Row {line_num}: Enter at least one amount (employee, employer, or loan)")
        return rows, errors

    due = _coerce_date(due_str) if due_str else None
    if due is None:
        errors.append(f"Row {line_num}: Invalid due date '{due_str}' (use YYYY-MM-DD or MM/DD/YYYY)")
        return rows, errors
    dep = _coerce_date(dep_str) if dep_str else None
    if dep is None:
        errors.append(f"Row {line_num}: Invalid deposit date '{dep_str}' (use YYYY-MM-DD or MM/DD/YYYY)")
        return rows, errors
    fp = _coerce_date(fp_str) if fp_str else None

    rows.append({
        "description": desc or f"Entry {line_num - 1}",
        "employee_amount": emp_amt,
        "employer_amount": er_amt,
        "loan_amount": loan_amt,
        "due_date": due,
        "deposit_date": dep,
        "final_payment_date": fp,
    })
    return rows, errors


def _excel_number_to_date(n: float) -> date:
    """Convert an Excel serial date number to a Python date."""
    # Excel epoch is 1899-12-30 (with the Lotus 1-2-3 bug where 1900 is treated as a leap year)
    if n < 0:
        raise ValueError("Negative date number")
    # Handle the 1900 leap year bug: Excel thinks 1900-02-29 exists (serial 60)
    if n > 59:
        n += 1  # Skip the phantom Feb 29, 1900
    return (date(1899, 12, 30) + timedelta(days=int(n)))


def build_result_csv(results: list[dict], errors: list[str]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_RESULT_COLUMNS)
    for r in results:
        ctype = r.get("contribution_type", "employee")
        writer.writerow([
            r["description"],
            r["amount"] if ctype == "employee" else "",
            r["amount"] if ctype == "employer" else "",
            r["amount"] if ctype == "loan" else "",
            r["due_date"],
            r["deposit_date"],
            r.get("final_payment_date", ""),
            r.get("contribution_label", ctype),
            r["days_late"],
            r["lost_earnings"],
        ])
    total = round(sum(r["lost_earnings"] for r in results), 2)
    writer.writerow([])
    writer.writerow(["TOTAL", sum(r["amount"] for r in results), "", "", "", "", sum(r["days_late"] for r in results) // len(results) if results else 0, total])
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
    writer.writerow(["Q1 contributions - John Smith", "5000.00", "2500.00", "", "2025-01-15", "2025-04-15", ""])
    writer.writerow(["Employee deferral only - Jane Doe", "3200.00", "", "", "2025-02-01", "2025-05-20", "2025-05-20"])
    writer.writerow(["Late loan repayment - Bob Lee", "", "", "450.00", "2025-03-01", "2025-06-15", ""])
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
                Upload a CSV with columns: <code>Description</code>, <code>Employee_Amount</code>, <code>Employer_Amount</code>, <code>Loan_Amount</code>, <code>Due_Date</code>, <code>Deposit_Date</code>,
                <code>Final_Payment_Date</code> (optional, defaults to Deposit_Date).
                Dates must be <code>YYYY-MM-DD</code>. Amounts as numbers.
              </p>
              <div class="drop-zone" id="drop-zone"
                   onclick="document.getElementById('csv-input').click()"
                   ondragover="event.preventDefault(); this.classList.add('dragover')"
                   ondragleave="this.classList.remove('dragover')"
                   ondrop="handleDrop(event)">
                <div class="icon">📁</div>
                <p class="mb-1 text-muted">Drag &amp; drop a CSV or Excel file here, or click to browse</p>
                <p class="mb-0 text-muted" style="font-size:0.78rem;">Accepts .csv, .xlsx, and .xls files</p>
              </div>
              <input type="file" id="csv-input" accept=".csv,.xlsx,.xls" class="d-none" onchange="handleFile(this.files[0])">

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
            Under the DOL's <strong>Voluntary Fiduciary Correction Program (VFCP)</strong>,
            fiduciaries who made late contributions to retirement plans (e.g., 401(k), 403(b))
            must pay <strong>lost earnings</strong> — the interest the participant would have earned
            had the deposit been made on time.
          </p>
          <p class="text-muted" style="font-size:0.85rem;">
            The DOL publishes two rates each quarter:
          </p>
          <div class="mb-2" style="font-size:0.82rem;">
            <div class="mb-1"><strong style="color:#2563eb;">■ Mid-term Rate (5-Year CMT)</strong> —
              Used for <em>late employee deferrals</em> (e.g., 401(k) salary deferrals, after-tax contributions).
              This is the 5-year Constant Maturity Treasury rate.
            </div>
            <div><strong style="color:#dc2626;">■ High Rate (Mid-term + 2%)</strong> —
              Used for <em>late employer matching/non-elective contributions</em>.
              This equals the mid-term rate plus 2 percentage points.
            </div>
          </div>
          <p class="text-muted mb-2" style="font-size:0.85rem;">
            <strong>Formula:</strong><br>
            <code>Lost Earnings = Amount &times; (Days / 365) &times; (Rate / 100)</code>
          </p>
          <p class="text-muted mb-0" style="font-size:0.78rem;">
            <a href="/how-it-works" class="text-decoration-underline">Read the full calculation guide &rarr;</a><br>
            <span class="text-muted">References: <a href="https://www.dol.gov/agencies/ebsa/laws-regulations/laws/vfcp" target="_blank">DOL VFCP</a> &middot;
            <a href="https://www.dol.gov/sites/dolgov/public/EBSA/about-ebsa/our-activities/resource-center/publications/interest-rate-table-for-vfcp.html" target="_blank">DOL Interest Rate Table</a></span>
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

    function addEntry(desc, emp, er, loan, due, deposit, fp) {
      if (desc === undefined) desc = '';
      if (emp === undefined) emp = '';
      if (er === undefined) er = '';
      if (loan === undefined) loan = '';
      if (due === undefined) due = '';
      if (deposit === undefined) deposit = '';
      if (fp === undefined) fp = '';
      entryCount++;
      const id = entryCount;
      const html = `
        <div class="entry-row" id="entry-${id}">
          <div class="row g-2 align-items-end">
            <div class="col-12">
              <label class="form-label" style="font-size:0.8rem;">Description</label>
              <input type="text" class="form-control form-control-sm entry-desc" placeholder="e.g., Q1 2025 employer match — John Smith" value="${desc}">
            </div>
            <div class="col-sm-3 col-6">
              <label class="form-label" style="font-size:0.8rem;">Employee Deferral ($)</label>
              <input type="number" class="form-control form-control-sm entry-emp" placeholder="0" step="0.01" min="0" value="${emp}">
            </div>
            <div class="col-sm-3 col-6">
              <label class="form-label" style="font-size:0.8rem;">Employer Match ($)</label>
              <input type="number" class="form-control form-control-sm entry-er" placeholder="0" step="0.01" min="0" value="${er}">
            </div>
            <div class="col-sm-3 col-6">
              <label class="form-label" style="font-size:0.8rem;">Loan Repayment ($)</label>
              <input type="number" class="form-control form-control-sm entry-loan" placeholder="0" step="0.01" min="0" value="${loan}">
            </div>
            <div class="col-sm-3 col-6">
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
      var rows = document.querySelectorAll('#entries .entry-row');
      var entries = [];
      for (var i = 0; i < rows.length; i++) {
        var row = rows[i];
        var empAmt = parseFloat(row.querySelector('.entry-emp').value) || 0;
        var erAmt = parseFloat(row.querySelector('.entry-er').value) || 0;
        var loanAmt = parseFloat(row.querySelector('.entry-loan').value) || 0;
        var due = row.querySelector('.entry-due').value;
        var deposit = row.querySelector('.entry-deposit').value;
        var fp = row.querySelector('.entry-fp').value;
        var desc = row.querySelector('.entry-desc').value.trim() || 'Entry';
        if ((empAmt > 0 || erAmt > 0 || loanAmt > 0) && due && deposit) {
          var entry = { description: desc, employee_amount: empAmt, employer_amount: erAmt, loan_amount: loanAmt, due_date: due, deposit_date: deposit };
          if (fp) entry.final_payment_date = fp;
          var entries = [];
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
      if (!entries.length) { showToast('Add at least one entry with amounts and dates.'); return; }
      for (var i = 0; i < entries.length; i++) {
        var e = entries[i];
        if (e.employee_amount <= 0 && e.employer_amount <= 0 && !e.loan_amount) { e.loan_amount = 0; }
        if (e.employee_amount <= 0 && e.employer_amount <= 0 && e.loan_amount <= 0) { showToast('Enter at least one amount (employee deferral, employer match, or loan repayment).'); return; }
        if (e.employee_amount <= 0 && e.employer_amount <= 0 && e.loan_amount <= 0) { showToast('Enter at least one amount (employee deferral, employer match, or loan repayment).'); return; }
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
      if (!file) return;
      const name = file.name.toLowerCase();
      if (!name.endsWith('.csv') && !name.endsWith('.xlsx') && !name.endsWith('.xls')) {
        showToast('Please upload a .csv, .xlsx, or .xls file.');
        return;
      }
      if (name.endsWith('.csv')) {
        const reader = new FileReader();
        reader.onload = function(e) {
          parseBulkCSV(e.target.result);
        };
        reader.readAsText(file);
      } else {
        // Excel files: send as binary FormData
        const formData = new FormData();
        formData.append('file', file);
        validateExcelUpload(formData);
      }
    }

    async function validateExcelUpload(formData) {
      try {
        const res = await fetch('/api/bulk/validate', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.error) { showToast(data.error); return; }
        bulkEntries = data.valid_entries;
        bulkErrors = data.errors;
        renderBulkPreview(data);
      } catch (err) {
        showToast('Failed to parse Excel file: ' + err.message);
      }
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
        var html = '<table class="table table-sm table-bordered"><thead><tr><th>#</th><th>Description</th><th>Employee</th><th>Employer</th><th>Loan</th><th>Due</th><th>Deposit</th><th>Final Pay</th></tr></thead><tbody>';
        for (var i = 0; i < data.valid_entries.length; i++) {
          var e = data.valid_entries[i];
          var empStr = e.employee_amount > 0 ? '$' + e.employee_amount.toLocaleString() : '—';
          var erStr = e.employer_amount > 0 ? '$' + e.employer_amount.toLocaleString() : '—';
          var loanStr = e.loan_amount > 0 ? '$' + e.loan_amount.toLocaleString() : '—';
          html += '<tr><td>' + (i+1) + '</td><td>' + e.description + '</td><td>' + empStr + '</td><td>' + erStr + '</td><td>' + loanStr + '</td><td>' + e.due_date + '</td><td>' + e.deposit_date + '</td><td>' + (e.final_payment_date || '—') + '</td></tr>';
        }
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
            <div class="value">$' + data.total_lost_earnings.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2}) + '</div>
            <div class="mt-1" style="font-size:0.85rem;">across ' + data.count + ' contributions</div>
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

      var html = '<div class="summary-box mb-4 text-center"><div class="label">Total Lost Earnings</div>' +
        '<div class="value">' + fmt(data.total_lost_earnings) + '</div>' +
        '<div class="mt-1" style="font-size:0.85rem;">across ' + data.results.length + ' contribution' + (data.results.length > 1 ? 's' : '') + ' &middot; Simple Interest</div></div>';

      for (const r of data.results) {
        var typeLabel = r.contribution_label || (r.contribution_type === 'employer' ? 'Employer Match' : r.contribution_type === 'loan' ? 'Loan Repayment' : 'Employee Deferral');
        var typeBadge = r.contribution_type === 'employer'
          ? '<span class="badge bg-danger">' + typeLabel + '</span>'
          : r.contribution_type === 'loan'
          ? '<span class="badge bg-success">' + typeLabel + '</span>'
          : '<span class="badge bg-primary">' + typeLabel + '</span>';
        html += '<div class="card p-3 mb-3"><strong>' + r.description + '</strong> ' + typeBadge + '<br>' +
          '<span class="text-muted" style="font-size:0.82rem;">' +
            fmt(r.amount) + ' &middot; Loss: ' + r.due_date + ' &middot; Recovery: ' + r.deposit_date;
        if (r.final_payment_date && r.final_payment_date !== r.deposit_date) {
          html += ' &middot; Final Payment: ' + r.final_payment_date;
        }
        html += ' &middot; ' +
            '<span class="badge bg-warning text-dark">' + r.days_late + ' days</span>' +
          '</span>';

        if (r.breakdown.length > 0) {
          html += '<div class="month-detail mt-2"><table class="table table-sm table-bordered results-table">' +
            '<thead><tr><th>Month</th><th>Rate %</th><th>Days</th><th>Factor</th><th>Start Bal</th><th>Earnings</th><th>End Bal</th></tr></thead><tbody>';
          for (var j = 0; j < r.breakdown.length; j++) {
            var m = r.breakdown[j];
            var rateStr = m.rate != null ? m.rate.toFixed(2) + '%' : 'N/A';
            var noteStr = m.note ? ' <span class="text-muted">(' + m.note + ')</span>' : '';
            var factorStr = m.factor != null ? m.factor.toFixed(6) : '—';
            html += '<tr><td>' + m.month + '</td><td>' + rateStr + noteStr + '</td><td>' + m.days + '</td><td>' + factorStr + '</td><td>' + fmt(m.beginning_balance) + '</td><td class="text-danger fw-semibold">' + fmt(m.earnings) + '</td><td>' + fmt(m.ending_balance) + '</td></tr>';
          }
          html += '</tbody></table></div>';
        }

        html += '<div class="text-end fw-bold" style="font-size:0.9rem;">Lost Earnings: ' + fmt(r.lost_earnings) + '</div></div>';
      }

      content.innerHTML = html;
    }

    // ── Rate table ──

    function buildRateTable() {
      const tbody = document.getElementById('rate-tbody');
      if (!tbody) return;
      const quarters = RATE_TABLE_PLACEHOLDER;
      const qLabels = {1: 'Jan 1 \u2013 Mar 31', 2: 'Apr 1 \u2013 Jun 30', 3: 'Jul 1 \u2013 Sep 30', 4: 'Oct 1 \u2013 Dec 31'};
      // Sort newest first, within year Q4 first
      quarters.sort(function(a, b) {
        if (a[0] !== b[0]) return b[0] - a[0];
        return b[1] - a[1];
      });
      var rows = '';
      for (var i = 0; i < quarters.length; i++) {
        var year = quarters[i][0], q = quarters[i][1], mid = quarters[i][2], high = quarters[i][3];
        var label = qLabels[q] || 'Q' + q;
        var period = label + ', ' + year;
        var highStr = (high !== null) ? high + '%' : 'N/A';
        rows += '<tr><td class="text-start">' + period + '</td><td>' + mid + '%</td><td>' + highStr + '</td></tr>';
      }
      tbody.innerHTML = rows;
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

        use_compounding = req.method != "simple"
        end_date = final_payment or deposit
        days_late = (end_date - due).days
        desc = entry.description or "Entry"

        if deposit <= due:
            for ctype, amt, label in [
                ("employee", entry.employee_amount, "Employee Deferral"),
                ("employer", entry.employer_amount, "Employer Match"),
                ("employee", entry.loan_amount, "Loan Repayment"),
            ]:
                if amt <= 0:
                    continue
                results.append({
                    "description": desc,
                    "amount": amt,
                    "due_date": entry.due_date,
                    "deposit_date": entry.deposit_date,
                    "final_payment_date": final_payment.isoformat() if final_payment else None,
                    "days_late": days_late,
                    "contribution_type": "loan" if label == "Loan Repayment" else ctype,
                    "contribution_label": label,
                    "breakdown": [],
                    "lost_earnings": 0.0,
                })
            continue

        for ctype, amt, label in [
            ("employee", entry.employee_amount, "Employee Deferral"),
            ("employer", entry.employer_amount, "Employer Match"),
            ("employee", entry.loan_amount, "Loan Repayment"),
        ]:
            if amt <= 0:
                continue
            breakdown = compute_lost_earnings(amt, due, deposit, final_payment_date=final_payment, use_compounding=use_compounding, rate_type=ctype)
            contrib_type = "loan" if label == "Loan Repayment" else ctype
            lost_earnings = sum(row["earnings"] for row in breakdown)
            results.append({
                "description": desc,
                "amount": amt,
                "due_date": entry.due_date,
                "deposit_date": entry.deposit_date,
                "final_payment_date": final_payment.isoformat() if final_payment else None,
                "days_late": days_late,
                "contribution_type": contrib_type,
                "contribution_label": label,
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
    fname = (file.filename or "").lower()
    if not (fname.endswith(".csv") or fname.endswith(".xlsx") or fname.endswith(".xls")):
        return JSONResponse(status_code=400, content={"error": "File must be a .csv, .xlsx, or .xls file"})
    content = await file.read()

    if fname.endswith(".csv"):
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
        rows, errors = parse_csv_rows(text)
    else:
        rows, errors = parse_excel_rows(content, file.filename)

    return {
        "valid_entries": [
            {
                "description": r["description"],
                "employee_amount": r["employee_amount"],
                "employer_amount": r["employer_amount"],
                "loan_amount": r["loan_amount"],
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
        emp_amt = float(e.get("employee_amount", 0) or 0)
        er_amt = float(e.get("employer_amount", 0) or 0)
        loan_amt = float(e.get("loan_amount", 0) or 0)
        try:
            due = date.fromisoformat(e["due_date"])
            deposit = date.fromisoformat(e["deposit_date"])
        except (ValueError, TypeError, KeyError) as exc:
            return JSONResponse(status_code=400, content={"error": f"Invalid entry data: {exc}"})

        use_compounding = body.get("method", "monthly") != "simple"
        end_date = final_payment or deposit
        days_late = (end_date - due).days

        if deposit <= due:
            for ctype, amt, label in [
                ("employee", emp_amt, "Employee Deferral"),
                ("employer", er_amt, "Employer Match"),
                ("employee", loan_amt, "Loan Repayment"),
            ]:
                if amt <= 0:
                    continue
                contrib_type = "loan" if label == "Loan Repayment" else ctype
                results.append({
                    "description": desc,
                    "amount": amt,
                    "due_date": due.isoformat(),
                    "deposit_date": deposit.isoformat(),
                    "final_payment_date": end_date.isoformat() if final_payment else None,
                    "days_late": days_late,
                    "contribution_type": contrib_type,
                    "contribution_label": label,
                    "lost_earnings": 0.0,
                    "breakdown": [],
                })
            continue

        for ctype, amt, label in [
            ("employee", emp_amt, "Employee Deferral"),
            ("employer", er_amt, "Employer Match"),
            ("employee", loan_amt, "Loan Repayment"),
        ]:
            if amt <= 0:
                continue
            breakdown = compute_lost_earnings(amt, due, deposit, final_payment_date=final_payment, use_compounding=use_compounding, rate_type=ctype)
            lost = round(sum(r["earnings"] for r in breakdown), 2)
            contrib_type = "loan" if label == "Loan Repayment" else ctype
            results.append({
                "description": desc,
                "amount": amt,
                "due_date": due.isoformat(),
                "deposit_date": deposit.isoformat(),
                "final_payment_date": end_date.isoformat() if final_payment else None,
                "days_late": days_late,
                "contribution_type": contrib_type,
                "contribution_label": label,
                "lost_earnings": lost,
                "breakdown": breakdown,
            })

    total = round(sum(r["lost_earnings"] for r in results), 2)
    csv_out = build_result_csv(results, [])

    return {
        "count": len(results),
        "total_lost_earnings": total,
        "csv": csv_out,
    }


@app.get("/how-it-works", response_class=HTMLResponse)
async def how_it_works():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>How Lost Earnings Are Calculated — VFCP Calculator</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background: #f4f6f8; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
    .page-header { background: #1a3a5c; color: #fff; padding: 2rem 0; }
    .page-header h1 { margin: 0; font-size: 1.5rem; }
    .page-header p { margin: 0.25rem 0 0; opacity: 0.85; font-size: 0.9rem; }
    .content-card { background: #fff; border-radius: 12px; padding: 2rem; margin-bottom: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
    .content-card h2 { font-size: 1.2rem; margin-top: 0; color: #1a3a5c; }
    .content-card h3 { font-size: 1.05rem; margin-top: 1.25rem; color: #2c5282; }
    .content-card p { font-size: 0.9rem; line-height: 1.65; }
    .formula-box { background: #f0f4f8; border-left: 4px solid #1a3a5c; padding: 1rem 1.25rem; border-radius: 0 8px 8px 0; font-family: monospace; font-size: 0.95rem; margin: 1rem 0; }
    .example-box { background: #fffbf0; border: 1px solid #f0d080; padding: 1rem 1.25rem; border-radius: 8px; margin: 1rem 0; }
    .example-box .step { margin-bottom: 0.5rem; font-size: 0.88rem; }
    .rate-badges { display: flex; gap: 1rem; flex-wrap: wrap; margin: 1rem 0; }
    .rate-badge { padding: 0.75rem 1rem; border-radius: 8px; flex: 1; min-width: 200px; }
    .rate-badge.emp { background: #eff6ff; border: 1px solid #93c5fd; }
    .rate-badge.er { background: #fef2f2; border: 1px solid #fca5a5; }
    .rate-badge strong { display: block; margin-bottom: 0.25rem; }
    .rate-badge .sub { font-size: 0.82rem; color: #555; }
    .ref-list { font-size: 0.82rem; }
    .ref-list li { margin-bottom: 0.5rem; }
    table.rate-example { font-size: 0.85rem; }
    table.rate-example th { background: #1a3a5c; color: #fff; }
  </style>
</head>
<body>
  <div class="page-header">
    <div class="container">
      <h1>📊 How Lost Earnings Are Calculated</h1>
      <p>VFCP Interest Rate Methodology — DOL Voluntary Fiduciary Correction Program</p>
    </div>
  </div>

  <div class="container py-4" style="max-width: 800px;">
    <p class="mb-4"><a href="/" class="text-decoration-none">&larr; Back to Calculator</a></p>

    <!-- Overview -->
    <div class="content-card">
      <h2>What Are Lost Earnings?</h2>
      <p>
        When a plan fiduciary fails to timely deposit participant contributions to a retirement plan
        (such as a 401(k) or 403(b) plan), the participants lose the investment earnings they
        would have received had the money been deposited on time. Under the
        <strong>Voluntary Fiduciary Correction Program (VFCP)</strong>, the fiduciary must make
        participants whole by paying <em>lost earnings</em> — essentially the interest the
        contributions would have earned.
      </p>
      <p>
        The DOL specifies exactly how to calculate these lost earnings using published interest
        rates, so there is no guesswork involved.
      </p>
    </div>

    <!-- Two Rates -->
    <div class="content-card">
      <h2>Two Different Rates for Two Types of Contributions</h2>
      <p>
        The DOL publishes <strong>two interest rates</strong> each quarter. Which rate you use
        depends on <em>whose</em> money was deposited late:
      </p>
      <div class="rate-badges">
        <div class="rate-badge emp">
          <strong style="color:#2563eb;">■ Mid-term Rate (5-Year CMT)</strong>
          <div class="sub">
            <strong>Applies to:</strong> Late <em>employee deferrals</em> — salary deferrals,
            after-tax contributions, and other participant contributions.<br><br>
            This is the 5-year Constant Maturity Treasury (CMT) rate, published by the
            Federal Reserve. It reflects the yield on intermediate-term U.S. Treasury bonds.
          </div>
        </div>
        <div class="rate-badge er">
          <strong style="color:#dc2626;">■ High Rate (Mid-term + 2%)</strong>
          <div class="sub">
            <strong>Applies to:</strong> Late <em>employer contributions</em> — matching
            contributions, non-elective contributions (NECs), and qualified
            nonelective contributions (QNECs).<br><br>
            This equals the mid-term rate <strong>plus 2 percentage points</strong>. The DOL adds
            a premium because employer contributions are discretionary and represent a
            higher level of fiduciary responsibility.
          </div>
        </div>
      </div>
      <h3>Why Two Rates?</h3>
      <p>
        Employee deferrals are the participant's own money taken from their paycheck —
        fiduciaries have a strict duty to deposit these promptly (generally within 7 business
        days of withholding per DOL guidance). Employer matching contributions, while still
        subject to the plan's deposit deadline, involve discretionary employer decisions.
        The higher rate reflects this distinction.
      </p>
    </div>

    <!-- Where Rates Come From -->
    <div class="content-card">
      <h2>Where Do the Rates Come From?</h2>
      <p>
        The DOL publishes an official <strong>Interest Rate Table for VFCP</strong> that lists
        both the mid-term and high rates for each calendar quarter, going back to Q1 1990.
        These rates are derived from:
      </p>
      <ul>
        <li><strong>Mid-term rate</strong> — The 5-Year CMT rate published by the Federal Reserve Board
            in its <em>H.15 Selected Interest Rates</em> statistical release.</li>
        <li><strong>High rate</strong> — The mid-term rate plus 2.00 percentage points (200 basis points).</li>
      </ul>
      <p>
        The rate that applies to any given day is the rate published for the <em>quarter</em>
        containing that day. For example, any date in April, May, or June uses the Q2 rate.
      </p>
      <table class="table table-sm rate-example table-bordered mt-2" style="width:auto;">
        <tr><th>Period</th><th>Mid-term</th><th>High (+2%)</th></tr>
        <tr><td>Jan – Mar 2026</td><td>7.00%</td><td>9.00%</td></tr>
        <tr><td>Apr – Jun 2026</td><td>6.00%</td><td>8.00%</td></tr>
        <tr><td>Jul – Sep 2026</td><td>7.00%</td><td>9.00%</td></tr>
      </table>
    </div>

    <!-- Calculation Method -->
    <div class="content-card">
      <h2>The Calculation Method</h2>
      <p>
        The DOL uses <strong>simple (non-compounding) interest</strong> applied to the
        <em>original principal amount</em>. Interest is calculated separately for each
        month (using that month's quarterly rate) and then summed.
      </p>
      <div class="formula-box">
        Lost Earnings = Amount &times; (Days in Month / 365) &times; (Quarterly Rate / 100)
      </div>
      <p>
        <strong>Key details:</strong>
      </p>
      <ul>
        <li><strong>Simple interest, not compound</strong> — Each month's interest is based on the original
            amount, never on accumulated interest.</li>
        <li><strong>365-day year</strong> — Not 360-day (banker's), not 366-day. Always 365.</li>
        <li><strong>Monthly segmentation</strong> — If the loss period spans multiple months (or quarters),
            each month is calculated separately using its applicable quarterly rate, then all months
            are summed.</li>
        <li><strong>Inclusive dates</strong> — The period includes both the loss date and the recovery date.
            If a contribution was due April 2 and deposited July 13, that's 102 days of interest.</li>
        <li><strong>Final Payment Date</strong> — If the fiduciary pays the participant on a date
            after the recovery date, interest continues accruing through the final payment date.</li>
      </ul>
    </div>

    <!-- Worked Example -->
    <div class="content-card">
      <h2>Worked Example</h2>
      <p>
        <strong>Scenario:</strong> A $1,034 employee deferral was due on April 2, 2026, but not
        deposited until July 13, 2026. No final payment date — we use July 13.
      </p>
      <p><strong>Applicable rates (mid-term for employee deferrals):</strong></p>
      <table class="table table-sm table-bordered mt-2" style="width:auto; font-size:0.85rem;">
        <tr><th>Month</th><th>Rate</th><th>Days</th><th>Calculation</th><th>Earnings</th></tr>
        <tr><td>Apr 2–30</td><td>6.00%</td><td>29</td><td>$1,034 &times; (29/365) &times; 0.06</td><td>$4.93</td></tr>
        <tr><td>May 1–31</td><td>6.00%</td><td>31</td><td>$1,034 &times; (31/365) &times; 0.06</td><td>$5.27</td></tr>
        <tr><td>Jun 1–30</td><td>6.00%</td><td>30</td><td>$1,034 &times; (30/365) &times; 0.06</td><td>$5.10</td></tr>
        <tr><td>Jul 1–13</td><td>7.00%</td><td>13</td><td>$1,034 &times; (13/365) &times; 0.07</td><td>$2.58</td></tr>
        <tr style="font-weight:bold;"><td colspan="4">Total</td><td>$17.88</td></tr>
      </table>
      <div class="example-box">
        <p class="mb-0" style="font-size:0.85rem;">
          <strong>Note:</strong> This calculator uses the DOL's published quarterly rates.
          The DOL's own online calculator may produce slightly different results depending
          on rounding conventions or rate updates. Always verify with the
          <a href="https://www.dol.gov/agencies/ebsa/workers-and-families/fiduciaries-and-plan-administrators/voluntary-fiduciary-correction-program" target="_blank">
          official DOL VFCP resources</a> before filing.
        </p>
      </div>
    </div>

    <!-- Employer Match Example -->
    <div class="content-card">
      <h2>Employer Match Example</h2>
      <p>
        <strong>Scenario:</strong> A $500 employer match contribution was due on April 2, 2026,
        deposited July 13, 2026. Since this is an employer contribution, we use the
        <strong>high rate (8.00%)</strong> instead.
      </p>
      <div class="formula-box">
        Q2 (Apr–Jun): $500 &times; (90/365) &times; 0.08 = $9.86<br>
        Q3 (Jul 1–13): $500 &times; (13/365) &times; 0.09 = $1.60<br>
        <strong>Total: $11.47</strong>
      </div>
      <p>
        The same dates, same period — but the 2 percentage-point premium on the rate means
        significantly higher lost earnings. This is why it's important to correctly identify
        <em>which</em> contributions were late.
      </p>
    </div>

    <!-- Date Definitions -->
    <div class="content-card">
      <h2>Key Date Definitions</h2>
      <dl>
        <dt><strong>Loss Date (Due Date)</strong></dt>
        <dd>The date the contribution should have been deposited. For employee deferrals,
            this is generally the date the amount was withheld from the employee's paycheck,
            or the 7th business day thereafter (per DOL guidance on timely deposits).
            For employer contributions, this is the plan's deposit deadline.</dd>

        <dt class="mt-3"><strong>Recovery Date (Deposit Date)</strong></dt>
        <dd>The date the contribution was actually deposited into the plan trust.</dd>

        <dt class="mt-3"><strong>Final Payment Date</strong></dt>
        <dd>The date the fiduciary actually pays the lost earnings to the participant.
            If left blank, the recovery date is used. If the final payment date is later
            than the recovery date, lost earnings continue accruing through that date.</dd>
      </dl>
    </div>

    <!-- References -->
    <div class="content-card">
      <h2>References</h2>
      <ul class="ref-list list-unstyled mb-0">
        <li>&#128196; <strong>DOL VFCP Program</strong><br>
          <a href="https://www.dol.gov/agencies/ebsa/laws-regulations/laws/vfcp" target="_blank">
          https://www.dol.gov/agencies/ebsa/laws-regulations/laws/vfcp</a><br>
          <span class="text-muted">The official program page describing eligibility, correction methods, and filing requirements.</span>
        </li>
        <li class="mt-2">&#128196; <strong>DOL Interest Rate Table for VFCP</strong><br>
          <a href="https://www.dol.gov/sites/dolgov/public/EBSA/about-ebsa/our-activities/resource-center/publications/interest-rate-table-for-vfcp.html" target="_blank">
          https://www.dol.gov/.../interest-rate-table-for-vfcp.html</a><br>
          <span class="text-muted">The official quarterly rate table (mid-term and high rates) used for all VFCP lost earnings calculations.</span>
        </li>
        <li class="mt-2">&#128196; <strong>DOL VFCP Online Calculator</strong><br>
          <a href="https://www.dol.gov/agencies/ebsa/workers-and-families/fiduciaries-and-plan-administrators/voluntary-fiduciary-correction-program" target="_blank">
          https://www.dol.gov/.../voluntary-fiduciary-correction-program</a><br>
          <span class="text-muted">The DOL's own online lost earnings calculator for reference.</span>
        </li>
        <li class="mt-2">&#128196; <strong>ERISA &sect; 404 — Fiduciary Duties</strong><br>
          <a href="https://www.law.cornell.edu/uscode/text/29/1104" target="_blank">
          29 U.S.C. &sect; 1104</a><br>
          <span class="text-muted">The statutory basis requiring fiduciaries to act prudently and exclusively in participants' interests.</span>
        </li>
        <li class="mt-2">&#128196; <strong>Federal Reserve H.15 — Selected Interest Rates</strong><br>
          <a href="https://www.federalreserve.gov/releases/h15/" target="_blank">
          https://www.federalreserve.gov/releases/h15/</a><br>
          <span class="text-muted">Source data for the 5-Year CMT rates used in the VFCP table.</span>
        </li>
      </ul>
    </div>

    <div class="text-center py-3">
      <a href="/" class="btn btn-primary px-4">&larr; Back to Calculator</a>
    </div>
  </div>
</body>
</html>"""


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": "VFCP Lost Earnings Calculator", "methodology": "Simple Interest"}
