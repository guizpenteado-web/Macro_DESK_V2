from datetime import date, datetime


def ref_date_to_yyyymm(ref_date: date) -> str:
    return ref_date.strftime("%Y%m")


def yyyymm_to_ref_date_end_of_month(yyyymm: str) -> date:
    """CVM competencia dates are always month-end. Given '202605' return 2026-05-31."""
    year, month = int(yyyymm[:4]), int(yyyymm[4:6])
    if month == 12:
        next_month_first = date(year + 1, 1, 1)
    else:
        next_month_first = date(year, month + 1, 1)
    return date.fromordinal(next_month_first.toordinal() - 1)


def month_range(start_yyyymm: str, end_yyyymm: str) -> list[str]:
    """Inclusive list of 'AAAAMM' strings from start to end."""
    start = datetime.strptime(start_yyyymm, "%Y%m")
    end = datetime.strptime(end_yyyymm, "%Y%m")
    months = []
    cur = start
    while cur <= end:
        months.append(cur.strftime("%Y%m"))
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)
    return months
