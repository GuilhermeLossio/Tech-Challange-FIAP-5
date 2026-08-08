# ECloe Market Catalog Sources

- Source URL: https://www.kaggle.com/datasets/fatihkgg/ecommerce-product-images-18k
- Import mode: local generated ecommerce-image fallback
- Deterministic seed: 426
- Kaggle target dataset: `fatihkgg/ecommerce-product-images-18k`.
- Kaggle dataset license as published by Kaggle source page: Apache 2.0.
- ECloe changes: brands, prices, stock, SKUs, and display copy are synthetic demo values.
- Image rule: product image assets are copied into `src/demo/ecloe_market/assets/catalog/` for local beta runtime.
- Runtime rule: the ECloe Market app and tests use `ecloe_market_catalog.json` only.
