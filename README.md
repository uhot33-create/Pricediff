# Pricediff

指定した商品名の商品について、楽天市場・Amazon・Yahooショッピングから最安値情報を取得し、
CSVに出力してメール送信するツールです。

## 実行方法

```bash
python pricediff.py "iPhone 15 Pro" --exclude-words "中古,訳あり,並行輸入"
```

実行すると `yyyyMMdd_HHmmss_result.csv` が作成され、SMTP設定がある場合はメール送信します。

### モック実行（APIアクセスなし）

```bash
python pricediff.py "iPhone 15 Pro" --mock
```

## envファイル

`.env` に環境変数を記載して実行します。スクリプト起動時に自動で読み込みます。

例:
```env
RAKUTEN_APP_ID=your_rakuten_app_id
YAHOO_APP_ID=your_yahoo_app_id

AMAZON_ACCESS_KEY=your_access_key
AMAZON_SECRET_KEY=your_secret_key
AMAZON_PARTNER_TAG=your_partner_tag
AMAZON_HOST=webservices.amazon.co.jp
AMAZON_REGION=ap-northeast-1

SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=mailer@example.com
SMTP_PASSWORD=secret
SMTP_FROM=mailer@example.com
SMTP_TO=you@example.com,team@example.com
SMTP_STARTTLS=true
```

## 必要な環境変数

### 楽天（Ichiba Item Search API 20220601）
- `RAKUTEN_APP_ID`

### Yahoo!ショッピング（商品検索API v3）
- `YAHOO_APP_ID`

### Amazon（Product Advertising API 5.0）
- `AMAZON_ACCESS_KEY`
- `AMAZON_SECRET_KEY`
- `AMAZON_PARTNER_TAG`
- `AMAZON_HOST` (省略可。既定: `webservices.amazon.co.jp`)
- `AMAZON_REGION` (省略可。既定: `ap-northeast-1`)

### SMTP
- `SMTP_HOST`
- `SMTP_PORT` (省略可。既定: `587`)
- `SMTP_USER` (省略可。未設定でも送信可)
- `SMTP_PASSWORD` (省略可)
- `SMTP_FROM`
- `SMTP_TO` (カンマ区切りで複数指定可)
- `SMTP_STARTTLS` (省略可。`true`/`false` 既定: `true`)

## 除外語の指定方法

`--exclude-words` にカンマ区切りで指定します。

例:
```bash
python pricediff.py "iPhone 15 Pro" --exclude-words "中古,訳あり,並行輸入"
```

## cron（Linux/macOS）設定例

```bash
crontab -e
```

```cron
0 9 * * * /usr/bin/env bash -lc 'cd /path/to/Pricediff && /usr/bin/python3 pricediff.py "iPhone 15 Pro" --exclude-words "中古,訳あり,並行輸入"'
```

## Windows タスクスケジューラ設定例

1. 「タスクスケジューラ」→「基本タスクの作成」
2. トリガー: 毎日 9:00
3. 操作: 「プログラムの開始」
4. プログラム/スクリプト:
   `C:\Python311\python.exe`
5. 引数の追加:
   `c:\Users\shige\workspace\CodeX\Pricediff\pricediff.py "iPhone 15 Pro" --exclude-words "中古,訳あり,並行輸入"`
6. 開始 (オプション):
   `c:\Users\shige\workspace\CodeX\Pricediff`

## 補足

- 送料が取得できない場合は空欄になります。
- Amazon API が失敗しても他サイト分は継続して処理されます。
