import datetime as dt
import hashlib
import hmac
import json
import logging
import os
from typing import List, Optional

import requests

from .types import Item


def _contains_exclude(name: str, exclude_words: List[str]) -> bool:
    lowered = name.lower()
    return any(word.lower() in lowered for word in exclude_words)


def search_amazon(
    session: requests.Session,
    product_name: str,
    exclude_words: List[str],
) -> Optional[Item]:
    access_key = os.getenv("AMAZON_ACCESS_KEY", "").strip()
    secret_key = os.getenv("AMAZON_SECRET_KEY", "").strip()
    partner_tag = os.getenv("AMAZON_PARTNER_TAG", "").strip()
    host = os.getenv("AMAZON_HOST", "webservices.amazon.co.jp").strip()
    region = os.getenv("AMAZON_REGION", "ap-northeast-1").strip()

    if not (access_key and secret_key and partner_tag):
        logging.info("Amazon credentials missing; skip Amazon search.")
        return None

    payload = {
        "Keywords": product_name,
        "SearchIndex": "All",
        "ItemCount": 10,
        "PartnerTag": partner_tag,
        "PartnerType": "Associates",
        "Resources": [
            "Images.Primary.Medium",
            "ItemInfo.Title",
            "Offers.Listings.Price",
            "Offers.Listings.DeliveryInfo.IsFreeShippingEligible",
            "Offers.Listings.DeliveryInfo.IsPrimeEligible",
            "Offers.Listings.DeliveryInfo.ShippingCharges",
        ],
    }

    try:
        response = _signed_request(
            session=session,
            method="POST",
            host=host,
            region=region,
            access_key=access_key,
            secret_key=secret_key,
            payload=payload,
        )
        data = response.json()
    except Exception as exc:
        logging.info("Amazon API error: %s", exc)
        return None

    if "Errors" in data:
        logging.info("Amazon API error: %s", data.get("Errors"))
        return None

    items = data.get("SearchResult", {}).get("Items", [])
    logging.info("Amazon items: %s", len(items))

    best_item = None
    best_price = None

    for item in items:
        title = item.get("ItemInfo", {}).get("Title", {}).get("DisplayValue", "")
        if not title or _contains_exclude(title, exclude_words):
            continue
        listing = _best_listing(item)
        if not listing:
            continue
        price = listing.get("Price", {}).get("Amount")
        if price is None:
            continue
        try:
            price_int = int(price)
        except (TypeError, ValueError):
            continue

        if best_price is None or price_int < best_price:
            best_price = price_int
            best_item = Item(
                name=title,
                image_url=_image_url(item),
                price=price_int,
                shipping=_shipping_from_listing(listing),
                url=item.get("DetailPageURL", ""),
            )

    if best_item:
        logging.info("Amazon best: %s (%s)", best_item.name, best_item.price)
    else:
        logging.info("Amazon best: none")

    return best_item


def _best_listing(item: dict) -> Optional[dict]:
    listings = item.get("Offers", {}).get("Listings", [])
    if not listings:
        return None
    return listings[0]


def _image_url(item: dict) -> str:
    return (
        item.get("Images", {})
        .get("Primary", {})
        .get("Medium", {})
        .get("URL", "")
    )


def _shipping_from_listing(listing: dict) -> Optional[int]:
    charges = listing.get("DeliveryInfo", {}).get("ShippingCharges")
    if not charges:
        return None
    amount = charges.get("Amount")
    if amount is None:
        return None
    try:
        return int(amount)
    except (TypeError, ValueError):
        return None


def _signed_request(
    session: requests.Session,
    method: str,
    host: str,
    region: str,
    access_key: str,
    secret_key: str,
    payload: dict,
) -> requests.Response:
    service = "ProductAdvertisingAPI"
    endpoint = f"https://{host}/paapi5/searchitems"
    content_type = "application/json; charset=utf-8"
    amz_target = "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems"

    now = dt.datetime.utcnow()
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    payload_str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

    canonical_headers = (
        f"content-encoding:utf-8\n"
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-amz-date:{amz_date}\n"
        f"x-amz-target:{amz_target}\n"
    )
    signed_headers = "content-encoding;content-type;host;x-amz-date;x-amz-target"
    canonical_request = "\n".join(
        [
            method,
            "/paapi5/searchitems",
            "",
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )

    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        [
            algorithm,
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )

    signing_key = _get_signature_key(secret_key, date_stamp, region, service)
    signature = hmac.new(
        signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    authorization_header = (
        f"{algorithm} Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    headers = {
        "Content-Type": content_type,
        "Content-Encoding": "utf-8",
        "X-Amz-Date": amz_date,
        "X-Amz-Target": amz_target,
        "Authorization": authorization_header,
    }

    resp = session.post(endpoint, data=payload_str.encode("utf-8"), headers=headers, timeout=20)
    resp.raise_for_status()
    return resp


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _get_signature_key(key: str, date_stamp: str, region: str, service: str) -> bytes:
    k_date = _sign(("AWS4" + key).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    return _sign(k_service, "aws4_request")
