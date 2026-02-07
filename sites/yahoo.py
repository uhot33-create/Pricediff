import logging
import os
from typing import List, Optional

import requests

from .types import Item


API_URL = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"


def _contains_exclude(name: str, exclude_words: List[str]) -> bool:
    lowered = name.lower()
    return any(word.lower() in lowered for word in exclude_words)


def search_yahoo(
    session: requests.Session,
    product_name: str,
    exclude_words: List[str],
) -> Optional[Item]:
    app_id = os.getenv("YAHOO_APP_ID", "").strip()
    if not app_id:
        raise RuntimeError("YAHOO_APP_ID is not set")

    params = {
        "appid": app_id,
        "query": product_name,
        "results": 30,
        "sort": "+price",
    }

    resp = session.get(API_URL, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    hits = data.get("hits", [])
    logging.info("Yahoo items: %s", len(hits))

    best_item = None
    best_price = None

    for item in hits:
        name = item.get("name", "")
        if not name or _contains_exclude(name, exclude_words):
            continue
        price = item.get("price")
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
                image_url=_image_url(item),
                price=price_int,
                shipping=_shipping_from_yahoo(item),
                url=item.get("url", ""),
            )

    if best_item:
        logging.info("Yahoo best: %s (%s)", best_item.name, best_item.price)
    else:
        logging.info("Yahoo best: none")

    return best_item


def _image_url(item: dict) -> str:
    image = item.get("image", {})
    return image.get("medium") or image.get("small") or ""


def _shipping_from_yahoo(item: dict) -> Optional[int]:
    # Yahoo may provide 'shipping' field; if not, return None.
    shipping = item.get("shipping")
    if shipping is None:
        return None
    try:
        return int(shipping)
    except (TypeError, ValueError):
        return None
