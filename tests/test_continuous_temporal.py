import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from research_temporal_continuous import partition_indices


def test_continuous_partitions_keep_boundary_predictions_and_censor_only_final_tail():
    time=pd.date_range("2024-01-01",periods=25,freq="D",tz="UTC")
    decisions=pd.DataFrame({"signal_time":time,"label_end":time+pd.Timedelta(days=7)})
    plan={"complete_evaluation_until":"2024-01-26T00:00:00Z","folds":[
        ["2024-01-01T00:00:00Z","2024-01-13T00:00:00Z"],
        ["2024-01-13T00:00:00Z","2024-01-26T00:00:00Z"]]}
    first,second=partition_indices(decisions,plan)
    np.testing.assert_array_equal(first,np.arange(12))
    np.testing.assert_array_equal(second,np.arange(12,18))


@pytest.mark.parametrize("boundary",["2024-01-12T00:00:00Z","2024-01-14T00:00:00Z"])
def test_continuous_partitions_reject_gaps_and_overlaps(boundary):
    decisions=pd.DataFrame({"signal_time":pd.to_datetime([],utc=True),"label_end":pd.to_datetime([],utc=True)})
    plan={"complete_evaluation_until":"2024-01-26T00:00:00Z","folds":[
        ["2024-01-01T00:00:00Z","2024-01-13T00:00:00Z"],
        [boundary,"2024-01-26T00:00:00Z"]]}
    with pytest.raises(ValueError,match="gap or overlap"):
        partition_indices(decisions,plan)
