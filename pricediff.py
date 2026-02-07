#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import json
import logging
import os
import smtplib
import sys
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate
from typing import List, Optional, Tuple

import requests
from requests.exceptions import RequestException


@dataclass
class ItemResult:
    title: str = ""
    image_url: str = ""
    price: str = ""
    shipping: str = ""
    url: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Price search across Rakuten, Yahoo, Amazon.")
    parser.add_argument("model_number", help="Target model number")
    parser.add_argument(
        "--exclude-words",
        default="",
        help="Comma-separated words to exclude from product titles (e.g. '中古,訳あり')",
    )
    return parser.parse_args()


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def split_exclude_words(raw: str) -> List[str]:
    return [w.strip() for w in raw.split(",") if w.strip()]


def is_excluded(title: str, exclude_words: List[str]) -> bool:
    lowered = title.lower()
    return any(word.lower() in lowered for word in exclude_words)


def safe_get(url: str, params: dict, headers: Optional[dict] = None, timeout: int = 20) -> Optional[dict]:
    try:
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except (RequestException, json.JSONDecodeError) as exc:
        logging.error("HTTP error for %s: %s", url, exc)
        return None


def fetch_rakuten(model_number: str, exclude_words: List[str]) -> Optional[ItemResult]:
    app_id = os.getenv("RAKUTEN_APP_ID")
    if not app_id:
        logging.warning("RAKUTEN_APP_ID is not set. Skipping Rakuten.")
        return None

    url = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20170706"
    params = {
        "applicationId": app_id,
        "keyword": model_number,
        "hits": 30,
        "page": 1,
        "format": "json",
    }
    data = safe_get(url, params)
    if not data or "Items" not in data:
        logging.warning("Rakuten response missing Items.")
        return None

    items = []
    for entry in data.get("Items", []):
        item = entry.get("Item", {})
        title = item.get("itemName", "")
        if not title or is_excluded(title, exclude_words):
            continue
        price = item.get("itemPrice")
        if price is None:
            continue
        shipping = "0" if item.get("postageFlag") == 1 else ""
        image_url = ""
        images = item.get("mediumImageUrls") or []
        if images:
            image_url = images[0].get("imageUrl", "")
        items.append(
            ItemResult(
                title=title,
                image_url=image_url,
                price=str(price),
                shipping=shipping,
                url=item.get("itemUrl", ""),
            )
        )

    logging.info("Rakuten items after exclude: %d", len(items))
    if not items:
        return None

    cheapest = min(items, key=lambda x: float(x.price))
    logging.info("Rakuten cheapest: %s", cheapest.price)
    return cheapest


def fetch_yahoo(model_number: str, exclude_words: List[str]) -> Optional[ItemResult]:
    app_id = os.getenv("YAHOO_APP_ID")
    if not app_id:
        logging.warning("YAHOO_APP_ID is not set. Skipping Yahoo Shopping.")
        return None

    url = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"
    params = {
        "appid": app_id,
        "query": model_number,
        "results": 30,
    }
    data = safe_get(url, params)
    if not data or "hits" not in data:
        logging.warning("Yahoo response missing hits.")
        return None

    items = []
    for item in data.get("hits", []):
        title = item.get("name", "")
        if not title or is_excluded(title, exclude_words):
            continue
        price_raw = item.get("price")
        if isinstance(price_raw, dict):
            price = price_raw.get("value")
        else:
            price = price_raw
        if price is None:
            continue
        shipping = ""
        shipping_info = item.get("shipping")
        if isinstance(shipping_info, dict):
            shipping_val = shipping_info.get("price")
            if shipping_val is not None:
                shipping = str(shipping_val)
        shipping_code = item.get("shippingCode")
        if shipping == "" and shipping_code in (0, "0"):
            shipping = "0"

        items.append(
            ItemResult(
                title=title,
                image_url=item.get("image", {}).get("medium", ""),
                price=str(price),
                shipping=shipping,
                url=item.get("url", ""),
            )
        )

    logging.info("Yahoo items after exclude: %d", len(items))
    if not items:
        return None

    cheapest = min(items, key=lambda x: float(x.price))
    logging.info("Yahoo cheapest: %s", cheapest.price)
    return cheapest


def _sign(key: bytes, msg: str) -> bytes:
    import hmac
    import hashlib

    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _get_signature_key(key: str, date_stamp: str, region_name: str, service_name: str) -> bytes:
    k_date = _sign(("AWS4" + key).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region_name)
    k_service = _sign(k_region, service_name)
    k_signing = _sign(k_service, "aws4_request")
    return k_signing


def fetch_amazon(model_number: str, exclude_words: List[str]) -> Optional[ItemResult]:
    import hmac

    access_key = os.getenv("AMAZON_ACCESS_KEY")
    secret_key = os.getenv("AMAZON_SECRET_KEY")
    partner_tag = os.getenv("AMAZON_PARTNER_TAG")
    region = os.getenv("AMAZON_REGION", "us-east-1")
    host = os.getenv("AMAZON_HOST", "webservices.amazon.co.jp")

    if not all([access_key, secret_key, partner_tag]):
        logging.warning("Amazon credentials are not fully set. Skipping Amazon.")
        return None

    endpoint = f"https://{host}/paapi5/searchitems"
    service = "ProductAdvertisingAPI"
    amz_target = "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems"

    payload = {
        "Keywords": model_number,
        "PartnerTag": partner_tag,
        "PartnerType": "Associates",
        "Marketplace": "www.amazon.co.jp",
        "Resources": [
            "ItemInfo.Title",
            "Images.Primary.Medium",
            "Offers.Listings.Price",
            "Offers.Listings.DeliveryInfo",
        ],
    }

    t = dt.datetime.utcnow()
    amz_date = t.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = t.strftime("%Y%m%d")

    canonical_uri = "/paapi5/searchitems"
    canonical_querystring = ""
    canonical_headers = (
        f"content-encoding:amz-1.0\n"
        f"content-type:application/json; charset=utf-8\n"
        f"host:{host}\n"
        f"x-amz-date:{amz_date}\n"
        f"x-amz-target:{amz_target}\n"
    )
    signed_headers = "content-encoding;content-type;host;x-amz-date;x-amz-target"
    payload_json = json.dumps(payload)

    import hashlib

    payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    canonical_request = "\n".join(
        [
            "POST",
            canonical_uri,
            canonical_querystring,
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )

    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        [algorithm, amz_date, credential_scope, hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()]
    )

    signing_key = _get_signature_key(secret_key, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization_header = (
        f"{algorithm} Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    headers = {
        "content-encoding": "amz-1.0",
        "content-type": "application/json; charset=utf-8",
        "host": host,
        "x-amz-date": amz_date,
        "x-amz-target": amz_target,
        "Authorization": authorization_header,
    }

    try:
        response = requests.post(endpoint, headers=headers, data=payload_json, timeout=20)
        response.raise_for_status()
        data = response.json()
    except (RequestException, json.JSONDecodeError) as exc:
        logging.error("Amazon request failed: %s", exc)
        return None

    items = []
    for item in data.get("SearchResult", {}).get("Items", []):
        title = item.get("ItemInfo", {}).get("Title", {}).get("DisplayValue", "")
        if not title or is_excluded(title, exclude_words):
            continue
        listings = item.get("Offers", {}).get("Listings", [])
        if not listings:
            continue
        listing = listings[0]
        price_val = listing.get("Price", {}).get("Amount")
        if price_val is None:
            continue
        shipping = ""
        delivery = listing.get("DeliveryInfo", {})
        if delivery.get("IsFreeShipping") is True:
            shipping = "0"
        image_url = item.get("Images", {}).get("Primary", {}).get("Medium", {}).get("URL", "")
        items.append(
            ItemResult(
                title=title,
                image_url=image_url,
                price=str(price_val),
                shipping=shipping,
                url=item.get("DetailPageURL", ""),
            )
        )

    logging.info("Amazon items after exclude: %d", len(items))
    if not items:
        return None

    cheapest = min(items, key=lambda x: float(x.price))
    logging.info("Amazon cheapest: %s", cheapest.price)
    return cheapest


def write_csv(
    model_number: str,
    rakuten: Optional[ItemResult],
    amazon: Optional[ItemResult],
    yahoo: Optional[ItemResult],
    timestamp: dt.datetime,
) -> str:
    filename = timestamp.strftime("%Y%m%d_%H%M%S_result.csv")
    header = [
        "商品名",
        "型番",
        "商品画像URL",
        "楽天価格",
        "楽天送料",
        "楽天URL",
        "Amazon価格",
        "Amazon送料",
        "AmazonURL",
        "Yahoo価格",
        "Yahoo送料",
        "YahooURL",
    ]

    def pick_title() -> Tuple[str, str]:
        for item in (rakuten, amazon, yahoo):
            if item and item.title:
                return item.title, item.image_url
        return "", ""

    title, image_url = pick_title()

    row = [
        title,
        model_number,
        image_url,
        rakuten.price if rakuten else "",
        rakuten.shipping if rakuten else "",
        rakuten.url if rakuten else "",
        amazon.price if amazon else "",
        amazon.shipping if amazon else "",
        amazon.url if amazon else "",
        yahoo.price if yahoo else "",
        yahoo.shipping if yahoo else "",
        yahoo.url if yahoo else "",
    ]

    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(header)
        writer.writerow(row)

    return filename


def send_email(subject: str, body: str, attachment_path: str) -> None:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM")
    smtp_to = os.getenv("SMTP_TO")
    starttls = os.getenv("SMTP_STARTTLS", "true").lower() == "true"

    if not all([smtp_host, smtp_from, smtp_to]):
        raise ValueError("SMTP_HOST, SMTP_FROM, SMTP_TO must be set")

    recipients = [addr.strip() for addr in smtp_to.split(",") if addr.strip()]

    message = EmailMessage()
    message["From"] = smtp_from
    message["To"] = ", ".join(recipients)
    message["Date"] = formatdate(localtime=True)
    message["Subject"] = subject
    message.set_content(body)

    with open(attachment_path, "rb") as handle:
        data = handle.read()
    message.add_attachment(data, maintype="text", subtype="csv", filename=os.path.basename(attachment_path))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            if starttls:
                server.starttls()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            server.send_message(message)
    except smtplib.SMTPException as exc:
        raise RuntimeError(f"Failed to send email: {exc}") from exc


def main() -> int:
    setup_logging()
    args = parse_args()
    exclude_words = split_exclude_words(args.exclude_words)
    logging.info("Start price search for %s", args.model_number)

    rakuten = None
    amazon = None
    yahoo = None

    try:
        rakuten = fetch_rakuten(args.model_number, exclude_words)
    except Exception as exc:  # noqa: BLE001
        logging.error("Rakuten fetch failed: %s", exc)

    try:
        yahoo = fetch_yahoo(args.model_number, exclude_words)
    except Exception as exc:  # noqa: BLE001
        logging.error("Yahoo fetch failed: %s", exc)

    try:
        amazon = fetch_amazon(args.model_number, exclude_words)
    except Exception as exc:  # noqa: BLE001
        logging.error("Amazon fetch failed: %s", exc)

    timestamp = dt.datetime.now()
    csv_path = write_csv(args.model_number, rakuten, amazon, yahoo, timestamp)
    logging.info("CSV written: %s", csv_path)

    subject = f"価格調査結果 {args.model_number} {timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
    body = f"価格調査結果CSVを添付します。\n\n型番: {args.model_number}\nCSV: {csv_path}\n"

    try:
        send_email(subject, body, csv_path)
        logging.info("Email sent successfully.")
    except Exception as exc:  # noqa: BLE001
        logging.error("Email send failed: %s", exc)

    return 0


if __name__ == "__main__":
    sys.exit(main())
