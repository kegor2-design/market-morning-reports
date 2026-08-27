from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import math
import os
import re
import urllib.request
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as response:
        body = response.read()
    if len(body) < 10_000:
        raise RuntimeError(f"history source response is unexpectedly small: {len(body)} bytes")
    temp = destination.with_suffix(destination.suffix + ".tmp")
    temp.write_bytes(body)
    os.replace(temp, destination)


def fetch_yahoo_monthly(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    combined: dict[str, dict[str, Any]] = {}
    period2 = int((datetime.now(timezone.utc) + timedelta(days=2)).timestamp())
    for item in series:
        symbol = urllib.parse.quote(item["symbol"], safe="")
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1=0&period2={period2}&interval=1mo&events=history"
        request = urllib.request.Request(url, headers={"User-Agent": "MarketMorningPublisher/1.2"})
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        closes = result["indicators"]["quote"][0].get("close") or []
        for timestamp, close in zip(timestamps, closes):
            if close is None or not math.isfinite(float(close)):
                continue
            value = float(close)
            if value < float(item.get("min_value", -math.inf)) or value > float(item.get("max_value", math.inf)):
                continue
            observed = datetime.fromtimestamp(timestamp, timezone.utc).date().replace(day=1).isoformat()
            combined.setdefault(observed, {"date": observed})[item["id"]] = round(value, 6)
    return [combined[key] for key in sorted(combined)]


def merge_dated_series(series_sets: Iterable[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    combined: dict[str, dict[str, Any]] = {}
    for rows in series_sets:
        for row in rows:
            combined.setdefault(row["date"], {"date": row["date"]}).update({key: value for key, value in row.items() if key != "date"})
    return [combined[key] for key in sorted(combined)]


def fetch_fred_monthly(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result_sets: list[list[dict[str, Any]]] = []
    for item in series:
        series_id = urllib.parse.quote(item["series_id"], safe="")
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd=1950-01-01"
        request = urllib.request.Request(url, headers={"User-Agent": "MarketMorningPublisher/1.2"})
        with urllib.request.urlopen(request, timeout=60) as response:
            rows = csv.DictReader(io.StringIO(response.read().decode("utf-8-sig")))
            monthly: dict[str, float] = {}
            for row in rows:
                raw = row.get(item["series_id"])
                try:
                    value = float(raw)
                except (TypeError, ValueError):
                    continue
                month = date.fromisoformat(row["observation_date"]).replace(day=1).isoformat()
                monthly[month] = value
        result_sets.append([{"date": observed, item["id"]: round(value, 8)} for observed, value in monthly.items()])
    return merge_dated_series(result_sets)


def fetch_ecos_monthly(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    api_key = os.getenv("BOK_ECOS_API_KEY") or os.getenv("ECOS_API_KEY")
    if not api_key:
        raise RuntimeError("BOK_ECOS_API_KEY is required for Korea CPI and government bond yields")
    today = datetime.now(timezone.utc).date()
    result_sets: list[list[dict[str, Any]]] = []
    for item in series:
        end = today.strftime("%Y%m" if item["cycle"] == "M" else "%Y%m%d")
        item_codes = item.get("item_codes") or [item["item_code"]]
        parts = ["https://ecos.bok.or.kr/api/StatisticSearch", api_key, "json", "kr", "1", "100000", item["stat_code"], item["cycle"], item["start"], end, *item_codes]
        url = "/".join(urllib.parse.quote(str(part), safe=":/") for part in parts) + "/"
        request = urllib.request.Request(url, headers={"User-Agent": "MarketMorningPublisher/1.2"})
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rows = payload.get("StatisticSearch", {}).get("row", [])
        monthly: dict[str, float] = {}
        for row in rows:
            raw_time = str(row.get("TIME", ""))
            try:
                observed = date(int(raw_time[:4]), int(raw_time[4:6]), 1).isoformat()
                value = float(str(row["DATA_VALUE"]).replace(",", ""))
            except (KeyError, TypeError, ValueError):
                continue
            monthly[observed] = value
        result_sets.append([{"date": observed, item["id"]: round(value, 8)} for observed, value in monthly.items()])
    return merge_dated_series(result_sets)


def fetch_imf_debt(config: dict[str, Any]) -> list[dict[str, Any]]:
    countries = list(config["countries"])
    path = "/".join([config["indicator"], *countries])
    url = "https://www.imf.org/external/datamapper/api/v1/" + path
    with urllib.request.urlopen(url, timeout=60) as response:
        values = json.loads(response.read().decode("utf-8"))["values"][config["indicator"]]
    years = sorted({year for country in countries for year in values.get(country, {})})
    return [
        {"year": int(year), **{country: values.get(country, {}).get(year) for country in countries}}
        for year in years
    ]


def shiller_date(value: Any) -> date | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    year = int(numeric)
    month = int(round((numeric - year) * 100))
    if year < 1800 or month < 1 or month > 12:
        return None
    return date(year, month, 1)


def parse_shiller_rows(rows: Iterable[list[Any]]) -> list[dict[str, Any]]:
    def optional_number(row: list[Any], index: int, scale: float = 1.0) -> float | None:
        try:
            value = float(row[index]) * scale
        except (IndexError, TypeError, ValueError):
            return None
        return round(value, 8) if math.isfinite(value) else None

    points: list[dict[str, Any]] = []
    for row in rows:
        if len(row) < 8:
            continue
        observed = shiller_date(row[0])
        try:
            price = float(row[1])
            cpi = float(row[4])
            real_price = float(row[7])
        except (TypeError, ValueError):
            continue
        if not observed or not all(math.isfinite(x) and x > 0 for x in (price, cpi, real_price)):
            continue
        points.append({
            "date": observed.isoformat(),
            "price": round(price, 6),
            "real_price": round(real_price, 6),
            "cpi": round(cpi, 6),
            "gs10_pct": optional_number(row, 6),
            "real_total_return_price": optional_number(row, 9),
            "cape": optional_number(row, 12),
            "tr_cape": optional_number(row, 14),
            "excess_cape_yield_pct": optional_number(row, 16, 100.0),
            "stock_real_return_10y_pct": optional_number(row, 19, 100.0),
            "bond_real_return_10y_pct": optional_number(row, 20, 100.0),
            "excess_real_return_10y_pct": optional_number(row, 21, 100.0),
        })
    unique = {point["date"]: point for point in points}
    return [unique[key] for key in sorted(unique)]


def read_shiller_xls(path: Path) -> list[dict[str, Any]]:
    try:
        import xlrd
    except ImportError as exc:
        raise RuntimeError("xlrd is required; install requirements-market-history.txt") from exc
    workbook = xlrd.open_workbook(path)
    sheet = workbook.sheet_by_name("Data")
    return parse_shiller_rows(sheet.row_values(index) for index in range(8, sheet.nrows))


def write_csv(path: Path, points: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    fieldnames = list(points[0].keys())
    for point in points[1:]:
        fieldnames.extend(key for key in point if key not in fieldnames)
    with temp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(points)
    os.replace(temp, path)


def drawdowns(values: list[float]) -> list[float]:
    peak = 0.0
    result: list[float] = []
    for value in values:
        peak = max(peak, value)
        result.append((value / peak - 1.0) * 100 if peak else 0.0)
    return result


def nearest_index(dates: list[date], target: date) -> int:
    return min(range(len(dates)), key=lambda index: abs((dates[index] - target).days))


def render_charts(points: list[dict[str, Any]], events: list[dict[str, Any]], output_dir: Path) -> None:
    os.environ.setdefault("MPLCONFIGDIR", str(output_dir.parent / ".matplotlib"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)
    dates = [date.fromisoformat(point["date"]) for point in points]
    prices = [float(point["price"]) for point in points]
    declines = drawdowns(prices)

    def decorate(ax: Any, show_labels: bool) -> None:
        for event_number, event in enumerate(events, start=1):
            start = date.fromisoformat(event["start_date"])
            end = date.fromisoformat(event["end_date"])
            if end < dates[0] or start > dates[-1]:
                continue
            if event["event_type"] == "RANGE":
                ax.axvspan(start, end, color="#c23b3b", alpha=0.075, linewidth=0)
                marker = start + (end - start) / 2
            else:
                ax.axvline(start, color="#b54747", alpha=0.45, linewidth=0.8)
                marker = start
            if show_labels:
                ax.text(
                    marker,
                    0.95 - (event_number % 2) * 0.055,
                    str(event_number),
                    transform=ax.get_xaxis_transform(),
                    fontsize=7,
                    fontweight="bold",
                    color="white",
                    ha="center",
                    va="center",
                    bbox={"boxstyle": "circle,pad=0.27", "facecolor": "#9d3840", "edgecolor": "white", "linewidth": 0.6},
                )

    plt.rcParams.update({"font.size": 9, "axes.titleweight": "bold"})
    fig, ax = plt.subplots(figsize=(14, 7), dpi=140)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#f7f9fc")
    ax.plot(dates, prices, color="#174f7c", linewidth=1.35)
    ax.set_yscale("log")
    decorate(ax, True)
    fig.text(0.06, 0.965, "U.S. Stock Market Long-Run Monthly Price | Shiller S&P Composite Series", fontsize=15, fontweight="bold")
    fig.text(0.06, 0.93, f"1871–{dates[-1].year} · log scale · price index, dividends excluded", color="#667085")
    ax.grid(True, which="major", color="#dfe4ea", linewidth=0.7)
    ax.grid(True, which="minor", axis="y", color="#edf0f4", linewidth=0.4)
    ax.spines[["top", "right", "left", "bottom"]].set_visible(False)
    ax.xaxis.set_major_locator(mdates.YearLocator(10))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.subplots_adjust(left=0.06, right=0.985, bottom=0.09, top=0.89)
    fig.savefig(output_dir / "us-stock-market-long-run.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(14, 5.5), dpi=140)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#f7f9fc")
    ax.fill_between(dates, declines, 0, color="#b54747", alpha=0.8, linewidth=0)
    decorate(ax, False)
    ax.set_ylim(min(-90, min(declines) - 5), 3)
    fig.text(0.06, 0.955, "U.S. Stock Market Drawdown from Prior Monthly Peak", fontsize=15, fontweight="bold")
    fig.text(0.06, 0.91, "Monthly price index · 0% = prior peak", color="#667085")
    ax.yaxis.set_major_formatter(lambda value, _: f"{value:.0f}%")
    ax.grid(True, color="#dfe4ea", linewidth=0.7)
    ax.spines[["top", "right", "left", "bottom"]].set_visible(False)
    ax.xaxis.set_major_locator(mdates.YearLocator(10))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.subplots_adjust(left=0.06, right=0.985, bottom=0.1, top=0.86)
    fig.savefig(output_dir / "us-stock-market-drawdown.png")
    plt.close(fig)

    base_price = prices[0]
    real_prices = [float(point["real_price"]) / float(points[0]["real_price"]) * 100 for point in points]
    nominal_prices = [value / base_price * 100 for value in prices]
    total_return_base = float(points[0]["real_total_return_price"])
    total_returns = [float(point["real_total_return_price"]) / total_return_base * 100 for point in points]
    fig, ax = plt.subplots(figsize=(14, 6.2), dpi=140)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#f7f9fc")
    ax.plot(dates, nominal_prices, label="Nominal price", color="#68768a", linewidth=1.0)
    ax.plot(dates, real_prices, label="Real price", color="#174f7c", linewidth=1.25)
    ax.plot(dates, total_returns, label="Real total return (dividends reinvested)", color="#087a55", linewidth=1.4)
    ax.set_yscale("log")
    fig.text(0.06, 0.96, "Nominal Price vs Real Price vs Real Total Return", fontsize=15, fontweight="bold")
    fig.text(0.06, 0.92, "January 1871 = 100 · log scale", color="#667085")
    ax.grid(True, which="major", color="#dfe4ea", linewidth=0.7)
    ax.grid(True, which="minor", axis="y", color="#edf0f4", linewidth=0.4)
    ax.legend(loc="upper left", frameon=False, ncol=3)
    ax.spines[["top", "right", "left", "bottom"]].set_visible(False)
    ax.xaxis.set_major_locator(mdates.YearLocator(10))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.subplots_adjust(left=0.06, right=0.985, bottom=0.1, top=0.87)
    fig.savefig(output_dir / "us-stock-market-real-total-return.png")
    plt.close(fig)

    valuation = [(observed, point) for observed, point in zip(dates, points) if point.get("cape") is not None]
    valuation_dates = [item[0] for item in valuation]
    capes = [float(item[1]["cape"]) for item in valuation]
    cape_yields = [100.0 / value for value in capes]
    treasury_yields = [float(item[1]["gs10_pct"]) for item in valuation]
    excess_yields = [float(item[1]["excess_cape_yield_pct"]) for item in valuation]
    fig, (cape_ax, yield_ax) = plt.subplots(2, 1, figsize=(14, 8), dpi=140, sharex=True, gridspec_kw={"height_ratios": [1.05, 1]})
    fig.patch.set_facecolor("white")
    for axis in (cape_ax, yield_ax):
        axis.set_facecolor("#f7f9fc")
        axis.grid(True, color="#dfe4ea", linewidth=0.7)
        axis.spines[["top", "right", "left", "bottom"]].set_visible(False)
    cape_ax.plot(valuation_dates, capes, color="#174f7c", linewidth=1.25, label="CAPE")
    cape_ax.axhline(sorted(capes)[len(capes) // 2], color="#98a2b3", linestyle="--", linewidth=0.9, label="Historical median")
    cape_ax.legend(loc="upper left", frameon=False, ncol=2)
    yield_ax.plot(valuation_dates, cape_yields, color="#087a55", linewidth=1.2, label="CAPE earnings yield (1/CAPE)")
    yield_ax.plot(valuation_dates, treasury_yields, color="#b7791f", linewidth=1.0, label="U.S. 10Y Treasury yield")
    yield_ax.plot(valuation_dates, excess_yields, color="#9d3840", linewidth=0.9, alpha=0.85, label="Shiller excess CAPE yield")
    yield_ax.axhline(0, color="#667085", linewidth=0.7)
    yield_ax.yaxis.set_major_formatter(lambda value, _: f"{value:.0f}%")
    yield_ax.legend(loc="upper left", frameon=False, ncol=3)
    yield_ax.xaxis.set_major_locator(mdates.YearLocator(10))
    yield_ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.text(0.06, 0.97, "CAPE Valuation and Yield Comparison", fontsize=15, fontweight="bold")
    fig.text(0.06, 0.94, "CAPE since 1881 · yields in percent", color="#667085")
    fig.subplots_adjust(left=0.06, right=0.985, bottom=0.08, top=0.9, hspace=0.14)
    fig.savefig(output_dir / "us-stock-market-cape-yields.png")
    plt.close(fig)

    forward = [
        (observed, point) for observed, point in zip(dates, points)
        if point.get("stock_real_return_10y_pct") is not None and point.get("bond_real_return_10y_pct") is not None
    ]
    forward_dates = [item[0] for item in forward]
    stock_returns = [float(item[1]["stock_real_return_10y_pct"]) for item in forward]
    bond_returns = [float(item[1]["bond_real_return_10y_pct"]) for item in forward]
    excess_returns = [float(item[1]["excess_real_return_10y_pct"]) for item in forward]
    fig, ax = plt.subplots(figsize=(14, 6.2), dpi=140)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#f7f9fc")
    ax.plot(forward_dates, stock_returns, color="#174f7c", linewidth=1.15, label="Stocks")
    ax.plot(forward_dates, bond_returns, color="#b7791f", linewidth=1.0, label="Bonds")
    ax.plot(forward_dates, excess_returns, color="#087a55", linewidth=0.9, alpha=0.8, label="Stocks minus bonds")
    ax.axhline(0, color="#667085", linewidth=0.7)
    ax.yaxis.set_major_formatter(lambda value, _: f"{value:.0f}%")
    ax.grid(True, color="#dfe4ea", linewidth=0.7)
    ax.legend(loc="upper left", frameon=False, ncol=3)
    ax.spines[["top", "right", "left", "bottom"]].set_visible(False)
    ax.xaxis.set_major_locator(mdates.YearLocator(10))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.text(0.06, 0.96, "Subsequent 10-Year Annualized Real Returns: Stocks vs Bonds", fontsize=15, fontweight="bold")
    fig.text(0.06, 0.92, f"Observation date is the investment start · realized outcomes available through {forward_dates[-1]:%Y-%m}", color="#667085")
    fig.subplots_adjust(left=0.06, right=0.985, bottom=0.1, top=0.87)
    fig.savefig(output_dir / "us-stock-vs-bond-real-returns.png")
    plt.close(fig)


def render_korea_charts(points: list[dict[str, Any]], events: list[dict[str, Any]], output_dir: Path) -> None:
    os.environ.setdefault("MPLCONFIGDIR", str(output_dir.parent / ".matplotlib"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    def series(key: str) -> tuple[list[date], list[float]]:
        selected = [(date.fromisoformat(point["date"]), float(point[key])) for point in points if point.get(key) is not None]
        return [item[0] for item in selected], [item[1] for item in selected]

    def decorate(axis: Any) -> None:
        for event in events:
            start = date.fromisoformat(event["start_date"])
            end = date.fromisoformat(event["end_date"])
            if event["event_type"] == "RANGE":
                axis.axvspan(start, end, color="#c23b3b", alpha=0.07, linewidth=0)
            else:
                axis.axvline(start, color="#b54747", alpha=0.45, linewidth=0.8)

    kospi_dates, kospi = series("kospi")
    kosdaq_dates, kosdaq = series("kosdaq")
    fx_dates, usdkrw = series("usdkrw")
    fig, (stock_ax, fx_ax) = plt.subplots(2, 1, figsize=(14, 8), dpi=140, sharex=True, gridspec_kw={"height_ratios": [1.2, 0.8]})
    fig.patch.set_facecolor("white")
    for axis in (stock_ax, fx_ax):
        axis.set_facecolor("#f7f9fc")
        axis.grid(True, color="#dfe4ea", linewidth=0.7)
        axis.spines[["top", "right", "left", "bottom"]].set_visible(False)
        decorate(axis)
    stock_ax.plot(kospi_dates, [value / kospi[0] * 100 for value in kospi], color="#174f7c", linewidth=1.25, label=f"KOSPI ({kospi_dates[0]:%Y-%m}=100)")
    stock_ax.plot(kosdaq_dates, [value / kosdaq[0] * 100 for value in kosdaq], color="#087a55", linewidth=1.15, label=f"KOSDAQ ({kosdaq_dates[0]:%Y-%m}=100)")
    stock_ax.set_yscale("log")
    stock_ax.legend(loc="upper left", frameon=False, ncol=2)
    fx_ax.plot(fx_dates, usdkrw, color="#b7791f", linewidth=1.15, label="USD/KRW")
    fx_ax.legend(loc="upper left", frameon=False)
    fx_ax.yaxis.set_major_formatter(lambda value, _: f"₩{value:,.0f}")
    fx_ax.xaxis.set_major_locator(mdates.YearLocator(2))
    fx_ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.text(0.06, 0.97, "Korea Market Long-Run Map: KOSPI, KOSDAQ and USD/KRW", fontsize=15, fontweight="bold")
    fig.text(0.06, 0.94, "Monthly observations · stock indices rebased independently · current month may be incomplete", color="#667085")
    fig.subplots_adjust(left=0.07, right=0.985, bottom=0.08, top=0.9, hspace=0.15)
    fig.savefig(output_dir / "korea-market-indices-fx.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(14, 5.8), dpi=140)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#f7f9fc")
    ax.plot(kospi_dates, drawdowns(kospi), color="#174f7c", linewidth=1.15, label="KOSPI")
    ax.plot(kosdaq_dates, drawdowns(kosdaq), color="#087a55", linewidth=1.05, label="KOSDAQ")
    decorate(ax)
    ax.axhline(0, color="#667085", linewidth=0.7)
    ax.yaxis.set_major_formatter(lambda value, _: f"{value:.0f}%")
    ax.grid(True, color="#dfe4ea", linewidth=0.7)
    ax.legend(loc="lower left", frameon=False, ncol=2)
    ax.spines[["top", "right", "left", "bottom"]].set_visible(False)
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.text(0.06, 0.96, "KOSPI and KOSDAQ Drawdown from Prior Monthly Peak", fontsize=15, fontweight="bold")
    fig.text(0.06, 0.92, "Monthly closes · 0% = prior peak", color="#667085")
    fig.subplots_adjust(left=0.06, right=0.985, bottom=0.1, top=0.87)
    fig.savefig(output_dir / "korea-market-drawdown.png")
    plt.close(fig)


def render_macro_charts(
    commodities: list[dict[str, Any]],
    macro_points: list[dict[str, Any]],
    debt: list[dict[str, Any]],
    debt_config: dict[str, Any],
    output_dir: Path,
) -> None:
    os.environ.setdefault("MPLCONFIGDIR", str(output_dir.parent / ".matplotlib"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    def selected(points: list[dict[str, Any]], key: str) -> tuple[list[date], list[float]]:
        rows = [(date.fromisoformat(point["date"]), float(point[key])) for point in points if point.get(key) is not None]
        return [row[0] for row in rows], [row[1] for row in rows]

    colors = {"gold": "#b7791f", "wti": "#174f7c", "brent": "#087a55"}
    labels = {"gold": "Gold", "wti": "WTI", "brent": "Brent"}
    fig, ax = plt.subplots(figsize=(14, 6), dpi=140)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#f7f9fc")
    for key in ("gold", "wti", "brent"):
        dates, values = selected(commodities, key)
        ax.plot(dates, [value / values[0] * 100 for value in values], color=colors[key], linewidth=1.15, label=f"{labels[key]} ({dates[0]:%Y-%m}=100)")
    ax.set_yscale("log")
    ax.grid(True, which="major", color="#dfe4ea", linewidth=0.7)
    ax.legend(loc="upper left", frameon=False, ncol=3)
    ax.spines[["top", "right", "left", "bottom"]].set_visible(False)
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.text(0.06, 0.96, "Gold and Crude Oil Long-Run Price Map", fontsize=15, fontweight="bold")
    fig.text(0.06, 0.92, "USD futures · each series rebased independently · log scale", color="#667085")
    fig.subplots_adjust(left=0.06, right=0.985, bottom=0.1, top=0.87)
    fig.savefig(output_dir / "macro-gold-oil.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(14, 5.8), dpi=140)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#f7f9fc")
    for key, label, color in (("kr_cpi", "Korea CPI YoY", "#174f7c"), ("us_cpi", "U.S. CPI YoY", "#9d3840")):
        dates, values = selected(macro_points, key)
        yoy_dates = dates[12:]
        yoy = [(values[index] / values[index - 12] - 1) * 100 for index in range(12, len(values))]
        ax.plot(yoy_dates, yoy, color=color, linewidth=1.15, label=label)
    ax.axhline(2, color="#98a2b3", linestyle="--", linewidth=0.8, label="2% reference")
    ax.axhline(0, color="#667085", linewidth=0.7)
    ax.yaxis.set_major_formatter(lambda value, _: f"{value:.0f}%")
    ax.grid(True, color="#dfe4ea", linewidth=0.7)
    ax.legend(loc="upper left", frameon=False, ncol=3)
    ax.spines[["top", "right", "left", "bottom"]].set_visible(False)
    ax.xaxis.set_major_locator(mdates.YearLocator(5))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.text(0.06, 0.96, "Korea and U.S. Consumer Price Inflation", fontsize=15, fontweight="bold")
    fig.text(0.06, 0.92, "Year-over-year change in monthly CPI", color="#667085")
    fig.subplots_adjust(left=0.06, right=0.985, bottom=0.1, top=0.87)
    fig.savefig(output_dir / "macro-korea-us-cpi.png")
    plt.close(fig)

    fig, (kr_ax, compare_ax) = plt.subplots(2, 1, figsize=(14, 8), dpi=140)
    fig.patch.set_facecolor("white")
    rate_styles = (("kr3y", "Korea 3Y", "#68768a"), ("kr10y", "Korea 10Y", "#174f7c"), ("kr30y", "Korea 30Y", "#087a55"))
    for key, label, color in rate_styles:
        dates, values = selected(macro_points, key)
        kr_ax.plot(dates, values, color=color, linewidth=1.1, label=label)
    dates10, us10 = selected(macro_points, "us10y")
    dates30, us30 = selected(macro_points, "us30y")
    compare_ax.plot(dates10, us10, color="#b7791f", linewidth=1.0, label="U.S. 10Y")
    compare_ax.plot(dates30, us30, color="#9d3840", linewidth=1.0, label="U.S. 30Y")
    aligned = [(date.fromisoformat(point["date"]), float(point["kr10y"]) - float(point["us10y"])) for point in macro_points if point.get("kr10y") is not None and point.get("us10y") is not None]
    compare_ax.plot([row[0] for row in aligned], [row[1] for row in aligned], color="#087a55", linewidth=0.9, label="Korea 10Y minus U.S. 10Y")
    compare_ax.axhline(0, color="#667085", linewidth=0.7)
    for axis in (kr_ax, compare_ax):
        axis.set_facecolor("#f7f9fc")
        axis.grid(True, color="#dfe4ea", linewidth=0.7)
        axis.yaxis.set_major_formatter(lambda value, _: f"{value:.1f}%")
        axis.legend(loc="upper left", frameon=False, ncol=3)
        axis.spines[["top", "right", "left", "bottom"]].set_visible(False)
    kr_ax.xaxis.set_major_locator(mdates.YearLocator(2))
    kr_ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    compare_ax.xaxis.set_major_locator(mdates.YearLocator(5))
    compare_ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.text(0.06, 0.97, "Korea Government Bonds and Korea-U.S. Yield Gap", fontsize=15, fontweight="bold")
    fig.text(0.06, 0.94, "Monthly last observations · percent", color="#667085")
    fig.subplots_adjust(left=0.06, right=0.985, bottom=0.08, top=0.9, hspace=0.15)
    fig.savefig(output_dir / "macro-government-bond-yields.png")
    plt.close(fig)

    fig, (money_ax, policy_ax) = plt.subplots(2, 1, figsize=(14, 8), dpi=140, sharex=False)
    fig.patch.set_facecolor("white")
    for key, label, color in (("kr_m2", "Korea M2 YoY", "#174f7c"), ("us_m2", "U.S. M2 YoY", "#9d3840")):
        dates, values = selected(macro_points, key)
        money_ax.plot(dates[12:], [(values[i] / values[i - 12] - 1) * 100 for i in range(12, len(values))], color=color, linewidth=1.1, label=label)
    for key, label, color in (("bok_base_rate", "BOK base rate", "#68768a"), ("kr3y", "Korea Treasury 3Y", "#174f7c"), ("corp_aa_3y", "Corporate AA- 3Y", "#087a55")):
        dates, values = selected(macro_points, key)
        policy_ax.plot(dates, values, color=color, linewidth=1.05, label=label)
    for axis in (money_ax, policy_ax):
        axis.set_facecolor("#f7f9fc"); axis.grid(True, color="#dfe4ea", linewidth=0.7); axis.legend(loc="upper left", frameon=False, ncol=3)
        axis.yaxis.set_major_formatter(lambda value, _: f"{value:.1f}%"); axis.spines[["top", "right", "left", "bottom"]].set_visible(False)
        axis.xaxis.set_major_locator(mdates.YearLocator(5)); axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.text(0.06, 0.97, "Money Growth, Policy Rate and Credit Conditions", fontsize=15, fontweight="bold")
    fig.text(0.06, 0.94, "M2 year-over-year · monthly policy and market rates", color="#667085")
    fig.subplots_adjust(left=0.06, right=0.985, bottom=0.08, top=0.9, hspace=0.18)
    fig.savefig(output_dir / "macro-money-policy-credit.png"); plt.close(fig)

    fig, (fx_ax, buffer_ax) = plt.subplots(2, 1, figsize=(14, 8), dpi=140, sharex=False)
    fig.patch.set_facecolor("white")
    for key, label, color in (("krwusd", "KRW per USD", "#68768a"), ("krwjpy100", "KRW per JPY 100", "#174f7c"), ("krweur", "KRW per EUR", "#9d3840"), ("krwcny", "KRW per CNY", "#b7791f")):
        dates, values = selected(macro_points, key)
        fx_ax.plot(dates, [value / values[0] * 100 for value in values], color=color, linewidth=1.05, label=f"{label} ({dates[0]:%Y-%m}=100)")
    dates, values = selected(macro_points, "kr_reer"); buffer_ax.plot(dates, values, color="#087a55", linewidth=1.15, label="Korea REER (higher = stronger)")
    reserve_dates, reserves = selected(macro_points, "fx_reserves"); reserve_ax = buffer_ax.twinx(); reserve_ax.plot(reserve_dates, [v / 1_000_000 for v in reserves], color="#68768a", linewidth=1.0, label="FX reserves (USD bn)")
    for axis in (fx_ax, buffer_ax):
        axis.set_facecolor("#f7f9fc"); axis.grid(True, color="#dfe4ea", linewidth=0.7); axis.spines[["top", "right", "left", "bottom"]].set_visible(False)
        axis.xaxis.set_major_locator(mdates.YearLocator(5)); axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fx_ax.legend(loc="upper left", frameon=False, ncol=2); buffer_ax.legend(loc="upper left", frameon=False); reserve_ax.legend(loc="upper right", frameon=False)
    fig.text(0.06, 0.97, "Korean Won Cross Rates and External Buffer", fontsize=15, fontweight="bold")
    fig.text(0.06, 0.94, "KRW cross rates rebased independently · REER and foreign-exchange reserves", color="#667085")
    fig.subplots_adjust(left=0.06, right=0.94, bottom=0.08, top=0.9, hspace=0.18)
    fig.savefig(output_dir / "macro-korea-fx-buffer.png"); plt.close(fig)

    fig, (house_ax, issuance_ax) = plt.subplots(2, 1, figsize=(14, 8), dpi=140, sharex=False)
    fig.patch.set_facecolor("white")
    for key, label, color in (("seoul_house_price", "Seoul", "#9d3840"), ("national_house_price", "National", "#174f7c")):
        dates, values = selected(macro_points, key); house_ax.plot(dates, values, color=color, linewidth=1.1, label=label)
    dates, values = selected(macro_points, "sovereign_issuance"); issuance_ax.bar(dates, [v / 1000 for v in values], width=25, color="#174f7c", alpha=0.78, label="Korea Treasury issuance")
    for axis in (house_ax, issuance_ax):
        axis.set_facecolor("#f7f9fc"); axis.grid(True, color="#dfe4ea", linewidth=0.7); axis.legend(loc="upper left", frameon=False)
        axis.spines[["top", "right", "left", "bottom"]].set_visible(False); axis.xaxis.set_major_locator(mdates.YearLocator(5)); axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    issuance_ax.yaxis.set_major_formatter(lambda value, _: f"₩{value:.0f}tn")
    fig.text(0.06, 0.97, "Korea Housing Prices and Treasury Issuance", fontsize=15, fontweight="bold")
    fig.text(0.06, 0.94, "Housing indices · monthly government bond issuance", color="#667085")
    fig.subplots_adjust(left=0.06, right=0.985, bottom=0.08, top=0.9, hspace=0.18)
    fig.savefig(output_dir / "macro-korea-housing-issuance.png"); plt.close(fig)

    countries = debt_config["countries"]
    chart_names = {"KOR": "Korea", "USA": "United States", "JPN": "Japan", "CHN": "China", "DEU": "Germany", "GBR": "United Kingdom", "FRA": "France", "ITA": "Italy"}
    actual_year = min(int(debt_config["forecast_start"]) - 1, max(row["year"] for row in debt))
    actual = next(row for row in debt if row["year"] == actual_year)
    ordered = sorted(((chart_names[code], float(actual[code])) for code in countries if actual.get(code) is not None), key=lambda item: item[1])
    fig, (history_ax, bar_ax) = plt.subplots(1, 2, figsize=(14, 6.3), dpi=140, gridspec_kw={"width_ratios": [1.7, 1]})
    fig.patch.set_facecolor("white")
    for code, color in (("KOR", "#174f7c"), ("USA", "#9d3840"), ("JPN", "#68768a"), ("CHN", "#b7791f")):
        rows = [(row["year"], float(row[code])) for row in debt if row.get(code) is not None and row["year"] <= actual_year]
        history_ax.plot([row[0] for row in rows], [row[1] for row in rows], linewidth=1.3, label=chart_names[code], color=color)
    bar_ax.barh([item[0] for item in ordered], [item[1] for item in ordered], color="#174f7c", alpha=0.82)
    for axis in (history_ax, bar_ax):
        axis.set_facecolor("#f7f9fc")
        axis.grid(True, axis="y", color="#dfe4ea", linewidth=0.7)
        axis.spines[["top", "right", "left", "bottom"]].set_visible(False)
    history_ax.xaxis.set_major_formatter(lambda value, _: f"{value:.0f}")
    bar_ax.xaxis.set_major_formatter(lambda value, _: f"{value:.0f}%")
    history_ax.yaxis.set_major_formatter(lambda value, _: f"{value:.0f}%")
    history_ax.legend(loc="upper left", frameon=False, ncol=2)
    bar_ax.set_title(f"{actual_year} actual/estimate", loc="left")
    fig.text(0.06, 0.96, "General Government Gross Debt", fontsize=15, fontweight="bold")
    fig.text(0.06, 0.92, "Percent of GDP · consistent IMF WEO definition", color="#667085")
    fig.subplots_adjust(left=0.06, right=0.985, bottom=0.1, top=0.86, wspace=0.18)
    fig.savefig(output_dir / "macro-major-country-debt.png")
    plt.close(fig)


def render_blogger_page(
    points: list[dict[str, Any]],
    events: list[dict[str, Any]],
    korea_points: list[dict[str, Any]],
    korea_events: list[dict[str, Any]],
    commodities: list[dict[str, Any]],
    macro_points: list[dict[str, Any]],
    debt: list[dict[str, Any]],
    config: dict[str, Any],
    generated_at: str,
) -> str:
    raw_base = config["public"]["github_raw_base"].rstrip("/")
    latest = points[-1]
    declines = drawdowns([float(point["price"]) for point in points])
    cape = float(latest["cape"])
    cape_yield = 100.0 / cape
    korea_latest = {key: next(point[key] for point in reversed(korea_points) if point.get(key) is not None) for key in ("kospi", "kosdaq", "usdkrw")}
    commodity_latest = {key: next(point[key] for point in reversed(commodities) if point.get(key) is not None) for key in ("gold", "wti", "brent")}
    rate_latest = {key: next(point[key] for point in reversed(macro_points) if point.get(key) is not None) for key in ("kr3y", "kr10y", "kr30y", "us10y")}
    added_latest = {key: next(point[key] for point in reversed(macro_points) if point.get(key) is not None) for key in ("bok_base_rate", "fx_reserves", "kr_reer", "seoul_house_price", "sovereign_issuance", "krwusd", "krwjpy100", "krweur", "krwcny")}
    cpi_latest: dict[str, float] = {}
    for key in ("kr_cpi", "us_cpi"):
        values = [float(point[key]) for point in macro_points if point.get(key) is not None]
        cpi_latest[key] = (values[-1] / values[-13] - 1) * 100
    debt_actual_year = int(config["macro"]["debt"]["forecast_start"]) - 1
    debt_actual = next(row for row in debt if row["year"] == debt_actual_year)
    asset_version = re.sub(r"\D", "", generated_at)
    event_rows = []
    for event_number, event in enumerate(events, start=1):
        period = event["start_date"] if event["start_date"] == event["end_date"] else f'{event["start_date"]} ~ {event["end_date"]}'
        event_rows.append(
            "<tr>"
            f'<td>{event_number}</td><td>{html.escape(period)}</td><td>{html.escape(event["title_ko"])}</td>'
            f'<td><a href="{html.escape(event["source_url"])}" target="_blank" rel="noopener noreferrer">근거 자료</a></td>'
            "</tr>"
        )
    korea_event_rows = []
    for event_number, event in enumerate(korea_events, start=1):
        period = event["start_date"] if event["start_date"] == event["end_date"] else f'{event["start_date"]} ~ {event["end_date"]}'
        korea_event_rows.append(
            "<tr>"
            f'<td>{event_number}</td><td>{html.escape(period)}</td><td>{html.escape(event["title_ko"])}</td>'
            f'<td><a href="{html.escape(event["source_url"])}" target="_blank" rel="noopener noreferrer">근거 자료</a></td>'
            "</tr>"
        )
    style = """<style>
.mmp-history{max-width:1120px;margin:0 auto;color:#142033;font-family:Arial,'Noto Sans KR',sans-serif;line-height:1.7}.mmp-history *{box-sizing:border-box}.mmp-history-header{padding:32px;background:linear-gradient(135deg,#081a31,#12375f);color:#fff;border-radius:12px}.mmp-history-header h1{margin:4px 0;font-size:30px}.mmp-history-header p{margin:6px 0;color:#d6e2ef}.mmp-history-note{margin:18px 0;padding:16px 18px;border-left:4px solid #2d6da3;background:#f4f7fa}.mmp-history-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:20px 0}.mmp-history-metric{padding:14px 16px;border:1px solid #dfe4ea;border-radius:8px;background:#fff}.mmp-history-metric small{display:block;color:#667085}.mmp-history-metric strong{display:block;margin-top:3px;font-size:20px;color:#0b1f3a}.mmp-history figure{margin:24px 0}.mmp-history img{display:block;width:100%;height:auto;border:1px solid #dfe4ea;border-radius:8px}.mmp-history figcaption{margin-top:7px;color:#667085;font-size:12px}.mmp-history-term{display:block;margin-top:4px;color:#344054}.mmp-history h2{margin-top:34px;padding-bottom:8px;border-bottom:2px solid #0b1f3a;color:#0b1f3a}.mmp-history table{width:100%;border-collapse:collapse;font-size:13px}.mmp-history th{padding:9px;background:#0b1f3a;color:#fff;text-align:left}.mmp-history td{padding:9px;border-bottom:1px solid #dfe4ea}.mmp-history a{color:#145da0}.mmp-history-small{color:#667085;font-size:12px}@media(max-width:600px){.mmp-history-header{padding:22px}.mmp-history-header h1{font-size:24px}.mmp-history-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.mmp-history table{font-size:11px}}
</style>"""
    page = (
        style
        + '<article class="mmp-history"><header class="mmp-history-header"><small>MARKET HISTORY MAP</small>'
        + '<h1>장기 시장 지도</h1><p>오늘의 시장을 1871년 이후 미국 주식시장 역사 속에서 봅니다.</p></header>'
        + '<div class="mmp-history-note"><strong>읽는 법</strong><br>장기 가격 차트는 로그 척도입니다. '
        + '가격지수이므로 배당을 포함하지 않으며, 1957년 이전 구간은 현재 공식 S&amp;P 500이 아니라 Shiller의 장기 S&amp;P Composite 계열 자료입니다. '
        + '가장 최근 월은 월초 가격 또는 추정 CPI가 포함된 잠정치일 수 있습니다.</div>'
        + '<h2>한국 시장 지도</h2>'
        + '<div class="mmp-history-metrics">'
        + f'<div class="mmp-history-metric"><small>최근 KOSPI</small><strong>{korea_latest["kospi"]:,.2f}</strong></div>'
        + f'<div class="mmp-history-metric"><small>최근 KOSDAQ</small><strong>{korea_latest["kosdaq"]:,.2f}</strong></div>'
        + f'<div class="mmp-history-metric"><small>최근 원/달러</small><strong>₩{korea_latest["usdkrw"]:,.2f}</strong></div>'
        + f'<div class="mmp-history-metric"><small>최근 관측월</small><strong>{html.escape(korea_points[-1]["date"][:7])}</strong></div>'
        + '</div>'
        + f'<figure><img src="{raw_base}/charts/korea-market-indices-fx.png" alt="KOSPI KOSDAQ 원달러 환율 장기 월간 차트">'
        + '<figcaption>KOSPI와 KOSDAQ은 각 계열의 시작월을 100으로 환산했습니다.<span class="mmp-history-term"><strong>용어:</strong> USD/KRW는 1달러에 필요한 원화입니다. 상승하면 원화 약세입니다.</span></figcaption></figure>'
        + f'<figure><img src="{raw_base}/charts/korea-market-drawdown.png" alt="KOSPI KOSDAQ 월간 고점 대비 낙폭 차트">'
        + '<figcaption>각 지수의 이전 월간 고점 대비 하락률입니다.<span class="mmp-history-term"><strong>용어:</strong> Drawdown은 직전 고점에서 얼마나 하락했는지를 뜻합니다.</span></figcaption></figure>'
        + '<h2>한국 시장 주요 사건</h2><div style="overflow-x:auto"><table><thead><tr><th>#</th><th>기간</th><th>사건</th><th>출처</th></tr></thead><tbody>'
        + "".join(korea_event_rows)
        + '</tbody></table></div>'
        + f'<p class="mmp-history-small">국내 시장 자료 출처: <a href="{html.escape(config["korea"]["source_page"])}" target="_blank" rel="noopener noreferrer">{html.escape(config["korea"]["source_name"])}</a>. 최신 월 값은 진행 중인 월의 잠정값일 수 있습니다.</p>'
        + '<h2>물가·원자재 지도</h2>'
        + '<div class="mmp-history-metrics">'
        + f'<div class="mmp-history-metric"><small>금 선물</small><strong>${commodity_latest["gold"]:,.2f}</strong></div>'
        + f'<div class="mmp-history-metric"><small>WTI 선물</small><strong>${commodity_latest["wti"]:,.2f}</strong></div>'
        + f'<div class="mmp-history-metric"><small>한국 CPI 전년비</small><strong>{cpi_latest["kr_cpi"]:+.2f}%</strong></div>'
        + f'<div class="mmp-history-metric"><small>미국 CPI 전년비</small><strong>{cpi_latest["us_cpi"]:+.2f}%</strong></div>'
        + '</div>'
        + f'<figure><img src="{raw_base}/charts/macro-gold-oil.png" alt="금 WTI 브렌트유 장기 가격 차트"><figcaption>각 계열 시작월=100의 장기 변화율입니다.<span class="mmp-history-term"><strong>용어:</strong> WTI는 미국 원유, Brent는 국제 원유의 대표 가격입니다.</span></figcaption></figure>'
        + f'<figure><img src="{raw_base}/charts/macro-korea-us-cpi.png" alt="한국 미국 소비자물가 전년동월비 차트"><figcaption>월간 CPI의 전년동월비입니다.<span class="mmp-history-term"><strong>용어:</strong> CPI는 소비자가 구매하는 상품·서비스 가격의 평균 변화입니다.</span></figcaption></figure>'
        + '<h2>한국 국고채와 한미 금리차</h2>'
        + '<div class="mmp-history-metrics">'
        + f'<div class="mmp-history-metric"><small>국고채 3년</small><strong>{rate_latest["kr3y"]:.3f}%</strong></div>'
        + f'<div class="mmp-history-metric"><small>국고채 10년</small><strong>{rate_latest["kr10y"]:.3f}%</strong></div>'
        + f'<div class="mmp-history-metric"><small>국고채 30년</small><strong>{rate_latest["kr30y"]:.3f}%</strong></div>'
        + f'<div class="mmp-history-metric"><small>한미 10년 금리차</small><strong>{rate_latest["kr10y"] - rate_latest["us10y"]:+.3f}%p</strong></div>'
        + '</div>'
        + f'<figure><img src="{raw_base}/charts/macro-government-bond-yields.png" alt="한국 국고채 만기별 금리와 한미 금리차 차트"><figcaption>한국 3·10·30년과 미국 10·30년 금리입니다.<span class="mmp-history-term"><strong>용어:</strong> 한미 금리차가 음수면 한국 10년물 금리가 미국보다 낮다는 뜻입니다.</span></figcaption></figure>'
        + '<h2>통화량·기준금리·신용여건</h2>'
        + f'<figure><img src="{raw_base}/charts/macro-money-policy-credit.png" alt="한미 M2 증가율과 한국 기준금리 시장금리 회사채 금리"><figcaption>한미 M2 증가율과 한국의 정책·시장금리입니다.<span class="mmp-history-term"><strong>용어:</strong> M2는 시중 통화량, 회사채-국고채 금리차는 기업 신용위험을 나타냅니다.</span></figcaption></figure>'
        + '<h2>원화 환율과 대외 완충력</h2><div class="mmp-history-metrics">'
        + f'<div class="mmp-history-metric"><small>원/달러</small><strong>₩{added_latest["krwusd"]:,.2f}</strong></div>'
        + f'<div class="mmp-history-metric"><small>원/100엔</small><strong>₩{added_latest["krwjpy100"]:,.2f}</strong></div>'
        + f'<div class="mmp-history-metric"><small>원/유로</small><strong>₩{added_latest["krweur"]:,.2f}</strong></div>'
        + f'<div class="mmp-history-metric"><small>원/위안</small><strong>₩{added_latest["krwcny"]:,.2f}</strong></div>'
        + f'<div class="mmp-history-metric"><small>실질실효환율</small><strong>{added_latest["kr_reer"]:,.2f}</strong></div></div>'
        + f'<figure><img src="{raw_base}/charts/macro-korea-fx-buffer.png" alt="원달러 원엔 원유로 원위안 실질실효환율 외환보유액"><figcaption><strong>회색선이 원/달러(KRW per USD)</strong>입니다. 위쪽은 시작월=100 환율, 아래쪽은 원화의 실질가치와 외환보유액입니다.<span class="mmp-history-term"><strong>용어:</strong> 환율선 상승은 원화 약세, REER 상승은 물가까지 고려한 원화 강세를 뜻합니다.</span></figcaption></figure>'
        + '<h2>주택가격과 국고채 발행</h2>'
        + f'<figure><img src="{raw_base}/charts/macro-korea-housing-issuance.png" alt="서울 전국 주택가격과 국고채 월간 발행액"><figcaption>서울·전국 주택가격과 월별 국고채 발행액입니다.<span class="mmp-history-term"><strong>용어:</strong> 국고채 발행 증가는 정부의 시장 자금 조달 확대를 의미합니다.</span></figcaption></figure>'
        + '<h2>주요국 정부부채</h2>'
        + f'<figure><img src="{raw_base}/charts/macro-major-country-debt.png" alt="주요국 일반정부 총부채 GDP 대비 비율"><figcaption>IMF 기준 일반정부 총부채/GDP입니다. {debt_actual_year}년 한국 {float(debt_actual["KOR"]):.1f}%, 미국 {float(debt_actual["USA"]):.1f}%, 일본 {float(debt_actual["JPN"]):.1f}%.<span class="mmp-history-term"><strong>용어:</strong> GDP 대비 부채는 경제 규모와 비교한 정부부채 비율입니다.</span></figcaption></figure>'
        + f'<p class="mmp-history-small">출처: 한국 CPI·국고채는 <a href="https://ecos.bok.or.kr/" target="_blank" rel="noopener noreferrer">한국은행 ECOS</a>, 미국 CPI·국채는 <a href="https://fred.stlouisfed.org/" target="_blank" rel="noopener noreferrer">FRED</a>, 국가부채는 <a href="{html.escape(config["macro"]["debt"]["source_page"])}" target="_blank" rel="noopener noreferrer">IMF WEO</a>입니다.</p>'
        + '<h2>미국 시장 지도</h2>'
        + '<div class="mmp-history-metrics">'
        + f'<div class="mmp-history-metric"><small>최근 CAPE</small><strong>{cape:.2f}</strong></div>'
        + f'<div class="mmp-history-metric"><small>CAPE 이익수익률</small><strong>{cape_yield:.2f}%</strong></div>'
        + f'<div class="mmp-history-metric"><small>미국 10년물</small><strong>{float(latest["gs10_pct"]):.2f}%</strong></div>'
        + f'<div class="mmp-history-metric"><small>Excess CAPE Yield</small><strong>{float(latest["excess_cape_yield_pct"]):.2f}%</strong></div>'
        + '</div>'
        + f'<figure><img src="{raw_base}/charts/us-stock-market-long-run.png" alt="1871년 이후 미국 주식시장 장기 월간 로그 차트">'
        + '<figcaption>붉은 음영과 선은 주요 역사 사건입니다. 모바일에서는 이미지를 눌러 확대할 수 있습니다.<span class="mmp-history-term"><strong>용어:</strong> 로그 척도는 같은 비율의 상승·하락을 같은 간격으로 보여줍니다.</span></figcaption></figure>'
        + f'<figure><img src="{raw_base}/charts/us-stock-market-drawdown.png" alt="미국 주식시장 월간 고점 대비 낙폭 차트">'
        + '<figcaption>각 시점의 이전 월간 고점 대비 하락률입니다.<span class="mmp-history-term"><strong>용어:</strong> Drawdown은 직전 고점에서 얼마나 하락했는지를 뜻합니다.</span></figcaption></figure>'
        + '<h2>물가·배당을 반영한 장기 성과</h2>'
        + f'<figure><img src="{raw_base}/charts/us-stock-market-real-total-return.png" alt="명목 가격, 실질 가격, 배당 재투자 실질 총수익 비교 차트">'
        + '<figcaption>세 계열을 1871년 1월=100으로 환산했습니다. 실질 총수익은 물가와 배당 재투자를 함께 반영합니다.<span class="mmp-history-term"><strong>용어:</strong> 명목은 표시 가격, 실질은 물가 제거, 총수익은 배당 재투자 포함입니다.</span></figcaption></figure>'
        + '<h2>밸류에이션과 금리</h2>'
        + f'<figure><img src="{raw_base}/charts/us-stock-market-cape-yields.png" alt="CAPE와 이익수익률, 미국 10년물 금리 비교 차트">'
        + '<figcaption>CAPE 이익수익률은 1/CAPE이며, Excess CAPE Yield는 Shiller가 산출한 인플레이션 조정 장기금리 대비 초과수익률 지표입니다.<span class="mmp-history-term"><strong>용어:</strong> CAPE는 최근 10년의 물가조정 평균이익으로 계산한 주가수익비율입니다.</span></figcaption></figure>'
        + '<h2>주식과 채권의 이후 10년 실질수익률</h2>'
        + f'<figure><img src="{raw_base}/charts/us-stock-vs-bond-real-returns.png" alt="관측 시점 이후 10년간 주식과 채권의 연율화 실질수익률 차트">'
        + '<figcaption>각 관측월에 투자했다고 가정한 이후 10년 연율화 실질수익률입니다. 미래 10년이 완성돼야 계산되므로 현재 공개값은 2016년까지입니다.<span class="mmp-history-term"><strong>용어:</strong> 연율화 수익률은 여러 해의 성과를 연평균 복리 수익률로 환산한 값입니다.</span></figcaption></figure>'
        + '<h2>주요 사건</h2><div style="overflow-x:auto"><table><thead><tr><th>#</th><th>기간</th><th>사건</th><th>출처</th></tr></thead><tbody>'
        + "".join(event_rows)
        + '</tbody></table></div><h2>데이터 상태</h2>'
        + f'<p>최근 관측월: <strong>{html.escape(latest["date"])}</strong> · 최근 가격값: <strong>{latest["price"]:,.2f}</strong> · 고점 대비: <strong>{declines[-1]:+.2f}%</strong></p>'
        + f'<p class="mmp-history-small">생성 시각: {html.escape(generated_at)} · 출처: <a href="{html.escape(config["source"]["source_page"])}" target="_blank" rel="noopener noreferrer">Robert J. Shiller data</a>. '
        + '이 자료는 역사적 비교와 연구를 위한 것이며 투자 권유가 아닙니다.</p></article>'
    )
    return page.replace('.png"', f'.png?v={asset_version}"')


def build(root: Path) -> dict[str, Any]:
    config = load_json(root / "config/market_history.json")
    events = load_json(root / "config/market_history_events.json")
    korea_events = load_json(root / "config/korea_market_events.json")
    private_source = root / "data/private/market_history/ie_data.xls"
    download(config["source"]["url"], private_source)
    points = read_shiller_xls(private_source)
    korea_points = fetch_yahoo_monthly(config["korea"]["series"])
    commodities = fetch_yahoo_monthly(config["macro"]["commodities"])
    fred_points = fetch_fred_monthly(config["macro"]["fred"])
    ecos_points = fetch_ecos_monthly(config["macro"]["ecos"])
    macro_points = merge_dated_series([fred_points, ecos_points])
    debt = fetch_imf_debt(config["macro"]["debt"])
    if len(points) < 1_500 or points[0]["date"] != "1871-01-01":
        raise RuntimeError("history dataset failed coverage validation")
    latest_date = date.fromisoformat(points[-1]["date"])
    if latest_date < datetime.now(timezone.utc).date().replace(day=1) - timedelta(days=62):
        raise RuntimeError(f"history dataset is stale: latest={latest_date.isoformat()}")
    if len(korea_points) < 250 or not all(any(point.get(key) is not None for point in korea_points) for key in ("kospi", "kosdaq", "usdkrw")):
        raise RuntimeError("Korea market dataset failed coverage validation")
    source_hash = hashlib.sha256(
        private_source.read_bytes()
        + json.dumps([korea_points, commodities, macro_points, debt], sort_keys=True).encode("utf-8")
    ).hexdigest()
    manifest_path = root / "public/market-history/manifest.json"
    prior_manifest = load_json(manifest_path) if manifest_path.exists() else {}
    generated_at = (
        prior_manifest.get("generated_at_utc")
        if prior_manifest.get("source_sha256") == source_hash
        else datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    public_dir = root / "public/market-history"
    write_csv(public_dir / "data/us-stock-market-monthly.csv", points)
    write_csv(public_dir / "data/korea-market-monthly.csv", korea_points)
    write_csv(public_dir / "data/macro-commodities-monthly.csv", commodities)
    write_csv(public_dir / "data/macro-cpi-rates-monthly.csv", macro_points)
    write_csv(public_dir / "data/imf-government-debt-annual.csv", debt)
    render_charts(points, events, public_dir / "charts")
    render_korea_charts(korea_points, korea_events, public_dir / "charts")
    render_macro_charts(commodities, macro_points, debt, config["macro"]["debt"], public_dir / "charts")
    page = render_blogger_page(points, events, korea_points, korea_events, commodities, macro_points, debt, config, generated_at)
    (public_dir / "blogger-page.html").write_text(page, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "source_name": config["source"]["name"],
        "source_page": config["source"]["source_page"],
        "source_sha256": source_hash,
        "first_observation": points[0]["date"],
        "last_observation": points[-1]["date"],
        "observation_count": len(points),
        "event_count": len(events),
        "latest_price": points[-1]["price"],
        "latest_drawdown_pct": round(drawdowns([float(point["price"]) for point in points])[-1], 4),
        "korea_first_observation": korea_points[0]["date"],
        "korea_last_observation": korea_points[-1]["date"],
        "korea_observation_count": len(korea_points),
        "korea_event_count": len(korea_events),
        "latest_kospi": next(point["kospi"] for point in reversed(korea_points) if point.get("kospi") is not None),
        "latest_kosdaq": next(point["kosdaq"] for point in reversed(korea_points) if point.get("kosdaq") is not None),
        "latest_usdkrw": next(point["usdkrw"] for point in reversed(korea_points) if point.get("usdkrw") is not None),
        "commodities_observation_count": len(commodities),
        "macro_observation_count": len(macro_points),
        "debt_observation_count": len(debt),
    }
    atomic_json(manifest_path, manifest)
    return manifest
