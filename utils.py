import csv
import os
from typing import List, Any, Optional

import math

def clamp(x: float, min_val: float, max_val: float) -> Optional[float]:
    if x is None or math.isnan(x):
        return None
    return max(min_val, min(max_val, x))

def ensure_dir(dir_path: str):
    if not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)

def append_csv_row(file_path: str, header: List[str], row: List[Any]):
    ensure_dir(os.path.dirname(file_path))
    file_exists = os.path.exists(file_path)

    with open(file_path, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(header)
        writer.writerow(row)

def format_signed_delta(delta: float, base: float) -> str:
    if delta is None or base is None or base == 0:
        return "-"
    sign = "+" if delta > 0 else "-" if delta < 0 else ""
    pct = (abs(delta) / abs(base)) * 100
    return f"{sign}${abs(delta):.2f}, {sign}{pct:.2f}%"
