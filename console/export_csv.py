"""Export the 12 engagement records to a CSV file for Power BI."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from common.contract import load_corpus


def stringify_list_field(x):
    """Liste alanlarini (technologies, outcomes) CSV-uyumlu duz metne cevirir.
    Liste icindeki elemanlar string ise oldugu gibi birlestirir;
    dict ise "key: value" seklinde okunabilir metne cevirip birlestirir.
    Aksi halde CSV'de kose parantezli/dict gorunumlu string olusur
    ve Power BI'da temiz yuklenmez."""
    if not isinstance(x, list):
        return x
    parts = []
    for item in x:
        if isinstance(item, dict):
            parts.append(", ".join(f"{k}: {v}" for k, v in item.items()))
        else:
            parts.append(str(item))
    return "; ".join(parts)


def export_to_csv(output_path="console/engagements_export.csv"):
    records = load_corpus()
    df = pd.DataFrame(records)

    for col in ("technologies", "outcomes"):
        if col in df.columns:
            df[col] = df[col].apply(stringify_list_field)

    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"{len(df)} kayit '{output_path}' dosyasina yazildi.")
    return output_path


if __name__ == "__main__":
    export_to_csv()