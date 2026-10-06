import csv
from importlib.resources import files
from pathlib import Path


def load_env_data(site_id, filepath=None):
    """
    env_data.csv 파일에서 특정 SIteID의 해양 환경 데이터를 읽어옴
    """
    data_path = (
        Path(filepath)
        if filepath is not None
        else files("wec_optimization.data").joinpath("env_data.csv")
    )

    if not data_path.is_file():
        raise FileNotFoundError(f"Environment data file not found: {data_path}")

    with data_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if int(row["SiteID"]) == site_id:
                return {
                    "SiteName": row["SiteName"],
                    "Hs": float(row["Hs"]),
                    "Tp": float(row["Tp"]),
                    "Gamma": float(row["Gamma"]),
                    "Depth": float(row["Depth"]),
                }
    raise ValueError(f"SiteID '{site_id}' not found in environment data.")
