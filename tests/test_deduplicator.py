import pandas as pd

from esoccer_dashboard.services.deduplicator import deduplicate_clusters


def test_dedup_keeps_latest_when_multiple_sources_in_cluster():
    df = pd.DataFrame(
        [
            {
                "DuplaNormalizada": "A vs B",
                "Data": "2026-01-20",
                "DataHora": pd.Timestamp("2026-01-20 10:00:00"),
                "__source_file": "botA.xlsx",
            },
            {
                "DuplaNormalizada": "A vs B",
                "Data": "2026-01-20",
                "DataHora": pd.Timestamp("2026-01-20 10:03:00"),
                "__source_file": "botB.xlsx",
            },
            {
                "DuplaNormalizada": "A vs B",
                "Data": "2026-01-20",
                "DataHora": pd.Timestamp("2026-01-20 10:12:00"),
                "__source_file": "botA.xlsx",
            },
        ]
    )

    res = deduplicate_clusters(df, dedup_key=["DuplaNormalizada", "Data"], window_minutes=5)
    assert len(res.df) == 2
    assert res.df["DataHora"].tolist() == [
        pd.Timestamp("2026-01-20 10:03:00"),
        pd.Timestamp("2026-01-20 10:12:00"),
    ]


def test_dedup_does_not_collapse_single_source_cluster():
    df = pd.DataFrame(
        [
            {
                "DuplaNormalizada": "A vs B",
                "Data": "2026-01-20",
                "DataHora": pd.Timestamp("2026-01-20 10:00:00"),
                "__source_file": "botA.xlsx",
            },
            {
                "DuplaNormalizada": "A vs B",
                "Data": "2026-01-20",
                "DataHora": pd.Timestamp("2026-01-20 10:04:00"),
                "__source_file": "botA.xlsx",
            },
        ]
    )

    res = deduplicate_clusters(df, dedup_key=["DuplaNormalizada", "Data"], window_minutes=5)
    assert len(res.df) == 2


def test_dedup_three_files_overht_strategy():
    """3 fontes distintas no mesmo cluster (Over/HT): mantém só a mais tardia.
    Grupos com Linha diferente não se interferem."""
    df = pd.DataFrame(
        [
            {
                "DuplaNormalizada": "A vs B",
                "Linha": "Over 0.5 HT",
                "Data": "2026-01-20",
                "DataHora": pd.Timestamp("2026-01-20 10:00:00"),
                "__source_file": "betano.xlsx",
            },
            {
                "DuplaNormalizada": "A vs B",
                "Linha": "Over 0.5 HT",
                "Data": "2026-01-20",
                "DataHora": pd.Timestamp("2026-01-20 10:02:00"),
                "__source_file": "365.xlsx",
            },
            {
                "DuplaNormalizada": "A vs B",
                "Linha": "Over 0.5 HT",
                "Data": "2026-01-20",
                "DataHora": pd.Timestamp("2026-01-20 10:04:00"),
                "__source_file": "super.xlsx",
            },
            # Linha diferente — não deve ser agrupada com as anteriores
            {
                "DuplaNormalizada": "A vs B",
                "Linha": "Over 1.5 HT",
                "Data": "2026-01-20",
                "DataHora": pd.Timestamp("2026-01-20 10:02:00"),
                "__source_file": "betano.xlsx",
            },
        ]
    )

    res = deduplicate_clusters(
        df, dedup_key=["DuplaNormalizada", "Linha", "Data"], window_minutes=5
    )
    assert res.total_jogos_apos_dedup == 2
    timestamps = set(res.df["DataHora"].tolist())
    assert pd.Timestamp("2026-01-20 10:04:00") in timestamps  # mais tardio do cluster Over 0.5
    assert pd.Timestamp("2026-01-20 10:02:00") in timestamps  # único do cluster Over 1.5


def test_dedup_does_not_cluster_when_gap_gt_window():
    df = pd.DataFrame(
        [
            {
                "DuplaNormalizada": "A vs B",
                "Data": "2026-01-20",
                "DataHora": pd.Timestamp("2026-01-20 10:00:00"),
                "__source_file": "botA.xlsx",
            },
            {
                "DuplaNormalizada": "A vs B",
                "Data": "2026-01-20",
                "DataHora": pd.Timestamp("2026-01-20 10:06:00"),
                "__source_file": "botB.xlsx",
            },
        ]
    )

    res = deduplicate_clusters(df, dedup_key=["DuplaNormalizada", "Data"], window_minutes=5)
    assert len(res.df) == 2

