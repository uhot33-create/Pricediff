# Pricediff

複数ECサイトから型番で最安価格を取得し、CSVをメール送信するツールです。

## 機能概要

- 楽天市場 (Ichiba Item Search API)
- Yahooショッピング (商品検索API v3)
- Amazon (Product Advertising API 5.0)

各サイトから最安1件を抽出し、CSVを生成してメール送信します。

## 使い方

```bash
python pricediff.py "ABC-123" --exclude-words "中古,訳あり,並行輸入"
```

## 環境変数

### API

- `RAKUTEN_APP_ID`
- `YAHOO_APP_ID`
- `AMAZON_ACCESS_KEY`
- `AMAZON_SECRET_KEY`
- `AMAZON_PARTNER_TAG`
- `AMAZON_REGION` (任意、デフォルト: `us-east-1`)
- `AMAZON_HOST` (任意、デフォルト: `webservices.amazon.co.jp`)

### SMTP

- `SMTP_HOST`
- `SMTP_PORT` (任意、デフォルト: `587`)
- `SMTP_USER` (任意)
- `SMTP_PASSWORD` (任意)
- `SMTP_FROM`
- `SMTP_TO` (複数指定時はカンマ区切り)
- `SMTP_STARTTLS` (任意、デフォルト: `true`)

## 出力CSV

ファイル名: `yyyyMMdd_HHmmss_result.csv`

カラム:

```
商品名, 型番, 商品画像URL,
楽天価格, 楽天送料, 楽天URL,
Amazon価格, Amazon送料, AmazonURL,
Yahoo価格, Yahoo送料, YahooURL
```

## ログ

- 実行開始
- 各サイトの件数
- 最安採用
- CSVパス
- メール送信結果

## cron 設定例

```cron
0 9 * * * /usr/bin/env bash -lc 'cd /path/to/Pricediff && /usr/bin/env python3 pricediff.py "ABC-123" --exclude-words "中古,訳あり" >> pricediff.log 2>&1'
```

## Windows タスクスケジューラ例

1. 「タスクの作成」を開く
2. 「操作」タブで「プログラム/スクリプト」に `python`
3. 「引数の追加」に `C:\path\to\Pricediff\pricediff.py "ABC-123" --exclude-words "中古,訳あり"`
4. 「開始 (オプション)」に `C:\path\to\Pricediff`

## 注意事項

- Amazon PA-API は認証が必要です。
- 送料が取得できない場合は空欄になります。
- 各サイト取得に失敗しても他サイト分の取得とメール送信は継続します。
