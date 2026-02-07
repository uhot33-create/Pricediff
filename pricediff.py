import argparse
import csv
import datetime as dt
import logging
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable, List, Optional

import requests
from dotenv import load_dotenv

from sites.amazon import search_amazon
from sites.rakuten import search_rakuten
from sites.yahoo import search_yahoo
from sites.types import Item


def parse_exclude_words(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [w.strip() for w in raw.split(",") if w.strip()]


def item_to_row(item: Optional[Item]) -> List[str]:
    if not item:
        return ["", "", ""]
    return [
        str(item.price) if item.price is not None else "",
        str(item.shipping) if item.shipping is not None else "",
        item.url or "",
    ]


def safe_int(value) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def send_email(
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    smtp_from: str,
    smtp_to: List[str],
    subject: str,
    body: str,
    attachment_path: Path,
) -> None:
    msg = EmailMessage()
    msg["From"] = smtp_from
    msg["To"] = ", ".join(smtp_to)
    msg["Subject"] = subject
    msg.set_content(body)

    with attachment_path.open("rb") as f:
        data = f.read()
    msg.add_attachment(
        data,
        maintype="text",
        subtype="csv",
        filename=attachment_path.name,
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.ehlo()
        if os.getenv("SMTP_STARTTLS", "true").lower() in ("1", "true", "yes"):
            server.starttls()
            server.ehlo()
        if smtp_user:
            server.login(smtp_user, smtp_password)
        server.send_message(msg)


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Price diff tool")
    parser.add_argument("product_name", help="Product name (required)")
    parser.add_argument(
        "--exclude-words",
        default="",
        help='Comma-separated exclude words. e.g. "中古,訳あり,並行輸入"',
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mocked API responses (no network).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    product_name = args.product_name.strip()
    exclude_words = parse_exclude_words(args.exclude_words)
    logging.info("Start price diff for product_name=%s", product_name)

    session = requests.Session()

    rakuten_item = None
    yahoo_item = None
    amazon_item = None

    if args.mock:
        logging.info("Mock mode enabled: using local sample results.")
        rakuten_item, amazon_item, yahoo_item = get_mock_items(product_name)
    else:
        try:
            rakuten_item = search_rakuten(session, product_name, exclude_words)
        except Exception as exc:
            logging.info("Rakuten search failed: %s", exc)

        try:
            yahoo_item = search_yahoo(session, product_name, exclude_words)
        except Exception as exc:
            logging.info("Yahoo search failed: %s", exc)

        try:
            amazon_item = search_amazon(session, product_name, exclude_words)
        except Exception as exc:
            logging.info("Amazon search failed: %s", exc)

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = Path(f"{timestamp}_result.csv")

    header = [
        "商品名",
        "検索商品名",
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

    name = ""
    image_url = ""
    for candidate in (rakuten_item, amazon_item, yahoo_item):
        if candidate and candidate.name:
            name = candidate.name
            image_url = candidate.image_url
            break

    row = [
        name,
        product_name,
        image_url,
        *item_to_row(rakuten_item),
        *item_to_row(amazon_item),
        *item_to_row(yahoo_item),
    ]

    with csv_path.open("w", encoding="shift_jis", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerow(row)

    logging.info("CSV saved: %s", csv_path)

    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = safe_int(os.getenv("SMTP_PORT", "")) or 587
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM", "").strip()
    smtp_to = [x.strip() for x in os.getenv("SMTP_TO", "").split(",") if x.strip()]

    if not (smtp_host and smtp_from and smtp_to):
        logging.info("SMTP settings missing; skip email sending.")
        return 0

    subject = f"価格取得結果 {product_name} {timestamp}"
    body = f"商品名 {product_name} の最安値結果を送付します。"

    try:
        send_email(
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_user=smtp_user,
            smtp_password=smtp_password,
            smtp_from=smtp_from,
            smtp_to=smtp_to,
            subject=subject,
            body=body,
            attachment_path=csv_path,
        )
        logging.info("Email sent.")
    except Exception as exc:
        logging.error("Email send failed: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def get_mock_items(product_name: str):
    mock_rakuten = Item(
        name=f"{product_name} サンプル商品 楽天",
        image_url="https://example.com/rakuten.jpg",
        price=12345,
        shipping=0,
        url="https://example.com/rakuten",
    )
    mock_amazon = Item(
        name=f"{product_name} サンプル商品 Amazon",
        image_url="https://example.com/amazon.jpg",
        price=12500,
        shipping=None,
        url="https://example.com/amazon",
    )
    mock_yahoo = Item(
        name=f"{product_name} サンプル商品 Yahoo",
        image_url="https://example.com/yahoo.jpg",
        price=12000,
        shipping=500,
        url="https://example.com/yahoo",
    )
    return mock_rakuten, mock_amazon, mock_yahoo
