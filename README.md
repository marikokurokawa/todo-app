# Todoリストアプリ（Flask + Googleスプレッドシート）

## 機能
- やることの登録・編集・削除
- タイトル（必須・100文字以内）・内容・期日の3項目
- 一覧ページ（期日が近い順／期限切れは赤で強調）
- データはGoogleスプレッドシートに保存

## ファイル構成
```
todo-app/
├── app.py              # アプリ本体
├── requirements.txt    # 使うライブラリ
├── render.yaml         # Render公開用の設定
├── .gitignore          # credentials.json をGitに入れない設定
└── templates/
    ├── base.html       # 共通レイアウト
    ├── index.html      # 一覧ページ
    ├── form.html       # 登録・編集フォーム
    └── 404.html
```

---

## 手順1：Google側の準備（サービスアカウント）

1. https://console.cloud.google.com/ を開き、新しいプロジェクトを作る
2. 「APIとサービス」→「ライブラリ」で次の2つを**有効化**
   - Google Sheets API
   - Google Drive API
3. 「APIとサービス」→「認証情報」→「認証情報を作成」→「サービスアカウント」
   - 名前は何でもOK（例：todo-app）。ロールは設定不要
4. 作ったサービスアカウントを開く →「キー」タブ →「鍵を追加」→「新しい鍵を作成」→ **JSON**
   - ダウンロードされたファイルを `credentials.json` という名前で `todo-app/` に置く
5. JSONの中の `client_email`（`xxx@xxx.iam.gserviceaccount.com`）をコピーしておく

## 手順2：スプレッドシートの準備

1. Googleスプレッドシートで新規作成（中身は空でOK。1行目のヘッダーはアプリが自動で作ります）
2. 右上「共有」→ 手順1-5の `client_email` を追加し、**編集者**にする
3. URLの `/d/` と `/edit` の間の文字列が **スプレッドシートID**
   ```
   https://docs.google.com/spreadsheets/d/【ここがID】/edit
   ```

## 手順3：ローカルで動かす

```bash
cd todo-app
python -m venv .venv
# Mac/Linux
source .venv/bin/activate
# Windows
.venv\Scripts\activate

pip install -r requirements.txt

# Mac/Linux
export SPREADSHEET_ID="あなたのスプレッドシートID"
# Windows (PowerShell)
$env:SPREADSHEET_ID="あなたのスプレッドシートID"

python app.py
```
ブラウザで http://localhost:5000 を開く。登録するとスプレッドシートに行が増えます。

## 手順4：サーバーで公開する（Render・無料）

1. GitHubに新しいリポジトリを作り、`todo-app` の中身をpush
   - `.gitignore` により `credentials.json` は**pushされません**（鍵は絶対に公開しないこと）
2. https://render.com にGitHubでログイン →「New +」→「Blueprint」→ リポジトリを選ぶ
   - `render.yaml` が読み込まれ、自動で設定されます
   - （Blueprintを使わない場合は「Web Service」で、Build: `pip install -r requirements.txt`、Start: `gunicorn app:app`）
3. 環境変数を2つ入力
   | キー | 値 |
   |---|---|
   | `SPREADSHEET_ID` | スプレッドシートID |
   | `GOOGLE_CREDENTIALS_JSON` | `credentials.json` の**中身をまるごと**貼り付け |
4. デプロイ完了後、`https://todo-app-xxxx.onrender.com` のようなURLで公開されます

> 無料プランは15分アクセスがないとスリープし、次のアクセスで起動に30秒〜1分かかります。

## よくあるエラー
| エラー | 原因と対処 |
|---|---|
| `SpreadsheetNotFound` / 403 | スプレッドシートをサービスアカウントに「編集者」で共有していない、またはIDの間違い |
| `APIError: ... has not been used` | Sheets API / Drive API を有効化していない（有効化後、数分待つ） |
| `KeyError: 'SPREADSHEET_ID'` | 環境変数 `SPREADSHEET_ID` を設定していない |
| `FileNotFoundError: credentials.json` | ローカルで `credentials.json` を置いていない |
