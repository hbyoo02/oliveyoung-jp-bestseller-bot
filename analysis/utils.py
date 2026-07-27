def norm_key(brand: str, product_name: str) -> tuple[str, str]:
    return (brand or "").strip().lower(), (product_name or "").strip().lower()
