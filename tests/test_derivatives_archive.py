import importlib.util
import io
from pathlib import Path
import zipfile
import pytest


def module():
    spec=importlib.util.spec_from_file_location("metrics_downloader",Path(__file__).resolve().parents[1]/"scripts/download_derivatives_metrics.py")
    value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def payload(name,text):
    result=io.BytesIO()
    with zipfile.ZipFile(result,"w") as archive:
        archive.writestr(name,text)
    return result.getvalue()


def test_sparse_ratios_remain_missing_not_future_filled():
    m=module()
    text=",".join(["create_time","symbol",*m.FIELDS])+"\n2022-01-01 00:00:00,BTCUSDT,100,1000,,,,\n"
    frame=m.parse_archive(payload("BTCUSDT-metrics-2022-01-01.csv",text),"2022-01-01")
    assert frame.sum_open_interest.iloc[0]==100
    assert frame[m.FIELDS[2:]].isna().all().all()


def test_archive_rejects_traversal_or_wrong_day():
    m=module()
    with pytest.raises(ValueError,match="member"):
        m.parse_archive(payload("../data.csv","ignored"),"2022-01-01")
    text=",".join(["create_time","symbol",*m.FIELDS])+"\n2022-01-02 00:00:00,BTCUSDT,100,1000,,,,\n"
    with pytest.raises(ValueError,match="outside"):
        m.parse_archive(payload("BTCUSDT-metrics-2022-01-01.csv",text),"2022-01-01")
