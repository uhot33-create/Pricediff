import logging
import os
from typing import List, Optional

import requests

from .types import Item


API_URL = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"


def _contains_exclude(name: str, exclude_words: List[str]) -> bool:
    lowered = name.lower()
    return any(word.lower() in lowered for word in exclude_words)


def search_rakuten(
    session: requests.Session,
    product_name: str,
    exclude_words: List[str],
) -> Optional[Item]:
    app_id = os.getenv("RAKUTEN_APP_ID", "").strip()
    if not app_id:
        raise RuntimeError("RAKUTEN_APP_ID is not set")

    params = {
        "applicationId": app_id,
        "keyword": product_name,
        "format": "json",
        "hits": 30,
        "page": 1,
        "sort": "+itemPrice",
    }

    resp = session.get(API_URL, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    items = data.get("Items", [])
    logging.info("Rakuten items: %s", len(items))

    best_item = None
    best_price = None

    for entry in items:
        item = entry.get("Item", {})
        name = item.get("itemName", "")
        if not name or _contains_exclude(name, exclude_words):
            continue
        price = item.get("itemPrice")
        if price is None:
            continue
        try:
            price_int = int(price)
        except (TypeError, ValueError):
            continue

        if best_price is None or price_int < best_price:
            best_price = price_int
            best_item = Item(
                name=name,
                image_url=_best_image_url(item.get("mediumImageUrls") or []),
                price=price_int,
                shipping=_shipping_from_rakuten(item),
                url=item.get("itemUrl", ""),
            )

    if best_item:
        logging.info("Rakuten best: %s (%s)", best_item.name, best_item.price)
    else:
        logging.info("Rakuten best: none")

    return best_item


def _best_image_url(images) -> str:
    for img in images:
        url = img.get("imageUrl")
        if url:
            return url
    return ""


def _shipping_from_rakuten(item: dict) -> Optional[int]:
    # Rakuten provides a boolean 'postageFlag'. If 1, postage is included.
    # Shipping amount is not always available; return 0 for free, else None.
    postage_flag = item.get("postageFlag")
    if postage_flag == 1:
        return 0
    return None
