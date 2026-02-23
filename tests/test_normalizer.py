from esoccer_dashboard.services.normalizer import normalize_dupla


def test_normalize_orders_alphabetically():
    assert normalize_dupla("Force vs Agent") == "Agent vs Force"


def test_normalize_dedup_suffix_distribution():
    assert normalize_dupla("Cevuu vs Elmagico (2x6) (2x6)") == "Cevuu (2x6) vs Elmagico (2x6)"


def test_normalize_preserves_suffixes_per_player():
    assert (
        normalize_dupla("Yerema (ECF Volta) vs Profik (ECF Volta)")
        == "Profik (ECF Volta) vs Yerema (ECF Volta)"
    )

