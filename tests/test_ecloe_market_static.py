from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ecloe_market_shared_visual_tokens_exist() -> None:
    shared_core = (ROOT / "src" / "demo" / "shared" / "core.css").read_text(encoding="utf-8")
    pay_core = (ROOT / "src" / "demo" / "ecloe_pay" / "core.css").read_text(encoding="utf-8")
    market_css = (
        ROOT / "src" / "demo" / "ecloe_market" / "assets" / "market.css"
    ).read_text(encoding="utf-8")

    for token in [
        "--font-display: \"Baloo 2\"",
        "--font-body: Nunito",
        "--font-mono: \"Space Mono\"",
        "--color-ink: #073f36",
        "--color-heading: #064437",
        "--color-page: #f7fcf7",
        "--color-rose: #ff7fab",
        "--color-mint: #9ee7d4",
        "--color-lemon: #ffe18a",
    ]:
        assert token in shared_core
    assert "--color-ink: #073f36" in pay_core
    assert '@import url("/shared/core.css");' in market_css


def test_ecloe_market_static_files_do_not_request_real_financial_data() -> None:
    market_files = [
        ROOT / "src" / "demo" / "ecloe_market" / "market_index.html",
        ROOT / "src" / "demo" / "ecloe_market" / "market_product.html",
        ROOT / "src" / "demo" / "ecloe_market" / "market_planned.html",
        ROOT / "src" / "demo" / "ecloe_market" / "market_summary.html",
        ROOT / "src" / "demo" / "ecloe_market" / "assets" / "market.css",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in market_files)

    for forbidden in ["cpf", "cvv", "agencia", "senha bancaria"]:
        assert forbidden not in combined


def test_ecloe_market_i18n_files_exist() -> None:
    i18n_dir = ROOT / "src" / "demo" / "ecloe_market" / "i18n"
    assert (i18n_dir / "pt-BR.json").exists()
    assert (i18n_dir / "en-US.json").exists()
