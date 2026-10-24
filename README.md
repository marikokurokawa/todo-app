# Todoリストアプリ（Flask + Googleスプレッドシート + LINE）

## 機能

課題1
- やることの登録・編集・削除（タイトル・内容・期日）
- 一覧ページ（期限切れは赤で強調）
- データはGoogleスプレッドシートに保存

課題2で追加
1. **完了チェック**：「✓ 完了」ボタンで完了／未完了を切り替え。一覧は「未完了・完了・すべて」で絞り込み
2. **重要度**：高・中・低を設定。一覧は「期日が近い順」「重要度が高い順」で並び替え。重要度「高」は赤い線で目立たせる
3. **LINEリマインド**：毎朝8時、明日が期日の未完了のやることをLINEに自動で送る（同じ通知は1回だけ）

## ファイル構成
```
todo-app/
├── app.py                       # アプリ本体
├── requirements.txt             # 使うライブラリ（requests を追加）
├── render.yaml                  # Render用の設定
├── .gitignore
├── .github/workflows/remind.yml # 毎朝LINEリマインドを動かす設定（新規）
└── templates/
    ├── base.html / index.html / form.html / 404.html
```

## スプレッドシートについて
課題1のスプレッドシートをそのまま使えます。アプリを起動すると、1行目の見出しに次の3列が**自動で追加**されます。

| 列 | 見出し | 中身 |
|---|---|---|
| G | priority | 重要度（high / medium / low）。課題1で登録した分は「中」として表示 |
| H | done | 完了なら 1 |
| I | notified_for | LINEで通知済みの期日（期日を変えると、新しい期日でまた通知される） |

---

# 課題2の更新手順

## 手順1：LINE公式アカウントを作り、鍵を2つ手に入れる

LINE Notify はサービス終了しているため、**LINE Messaging API** を使います（無料プランで個人の通知には十分）。

1. https://developers.line.biz/ にLINEアカウントでログイン
2. 「プロバイダー」を作成（名前は何でもOK。例：todo-app）
3. 「Messaging API」のチャネルを作成する
   - 画面の案内に従って **LINE公式アカウント** を作成し、LINE Official Account Manager の「設定」→「Messaging API」→「Messaging APIを利用する」で、2で作ったプロバイダーを選ぶ
4. LINE Developers に戻り、作ったチャネルを開いて次の2つをメモ
   - 「チャネル基本設定」タブの一番下 → **あなたのユーザーID**（`U` で始まる33文字）→ `LINE_USER_ID`
   - 「Messaging API設定」タブの一番下 → **チャネルアクセストークン（長期）** の「発行」→ `LINE_CHANNEL_ACCESS_TOKEN`
5. 「Messaging API設定」タブのQRコードを自分のスマホのLINEで読み取り、**公式アカウントを友だち追加**する（追加しないと届きません）

> 画面の表記は時期によって変わることがあります。トークンは鍵と同じなので、GitHubや記事には絶対に載せないこと。

## 手順2：GitHubのファイルを更新する

ブラウザでリポジトリを開き、「Add file」→「Upload files」から次をアップロードして上書きします（`credentials.json` は上げない）。

- `app.py`
- `requirements.txt`
- `render.yaml`
- `README.md`
- `templates` フォルダの4ファイル（フォルダごとドラッグ）

続けて、毎朝の自動実行の設定ファイルを作ります（`.github` は隠しフォルダなので、アップロードではなく画面で作るのが確実）。

1. 「Add file」→「**Create new file**」
2. ファイル名の欄に `.github/workflows/remind.yml` と入力（`/` を打つとフォルダに区切られます）
3. 本文に、同梱の `.github/workflows/remind.yml` の中身をメモ帳で開いてコピー＆貼り付け
4. 「Commit changes」

GitHubを更新すると、Renderが自動で新しいバージョンを公開し直します（数分）。

## 手順3：Renderに環境変数を追加する

Renderのサービス画面 →「Environment」→「Add Environment Variable」で4つ追加し、「Save, rebuild, and deploy」。

| キー | 値 |
|---|---|
| `LINE_CHANNEL_ACCESS_TOKEN` | 手順1-4のチャネルアクセストークン |
| `LINE_USER_ID` | 手順1-4のユーザーID |
| `CRON_SECRET` | 好きな英数字30文字くらい（通知URLの合言葉。例：`r7Kq2mXa9LpZt5Wv1Nc8Hd3Fs6Gy4Bj`） |
| `APP_URL` | 公開URL（例：`https://todo-app-9pvo.onrender.com`）。通知にリンクが付きます |

## 手順4：LINEに届くかテストする

ブラウザで次のURLを開きます（`合言葉` は `CRON_SECRET` に入れた値）。

```
https://todo-app-9pvo.onrender.com/cron/remind?token=合言葉&test=1
```

- `{"ok": true, "test": true}` と表示され、LINEに「テスト通知です」が届けば成功
- `403 Forbidden` → 合言葉が違う
- `"ok": false` → 表示されたエラー文を確認（トークンやユーザーIDの間違い、友だち追加忘れなど）

## 手順5：毎朝の自動実行を設定する（GitHub Actions）

1. GitHubのリポジトリ →「Settings」→ 左メニュー「Secrets and variables」→「Actions」
2. 「New repository secret」で2つ登録

   | Name | Secret |
   |---|---|
   | `REMIND_URL` | `https://todo-app-9pvo.onrender.com/cron/remind` |
   | `CRON_SECRET` | Renderに入れたのと同じ合言葉 |

3. リポジトリの「Actions」タブ →「LINE reminder」→「Run workflow」で手動実行してみる
   - 緑のチェックが付けば成功。明日が期日のやることがあればLINEに届きます

以降は毎朝8時（日本時間）に自動で動きます。GitHubの混雑状況によって、数分〜数十分遅れることがあります。

### 動作確認のコツ
期日を**明日**にしたやることを登録 → 手順5-3の「Run workflow」を押す → LINEに届く → もう一度押しても届かない（通知済み）→ 完了にしたものは届かない、を確認できます。

---

# ローカルで動かす（Windows PowerShell）

```
cd $HOME\Downloads\todo-app\todo-app
.venv\Scripts\activate
pip install -r requirements.txt
$env:SPREADSHEET_ID="スプレッドシートID"
python app.py
```
http://localhost:5000 を開く。LINEのテストもする場合は、`$env:LINE_CHANNEL_ACCESS_TOKEN="..."`、`$env:LINE_USER_ID="..."`、`$env:CRON_SECRET="..."` も設定してから起動し、`http://localhost:5000/cron/remind?token=合言葉&test=1` を開く。

## よくあるエラー
| エラー | 原因と対処 |
|---|---|
| `SpreadsheetNotFound` / 403 | スプレッドシートをサービスアカウントに「編集者」で共有していない、またはIDの間違い |
| `JSONDecodeError` | `SPREADSHEET_ID` にURL全体や `"` が入っている |
| `スプレッドシートの1行目が想定と違います` | 1行目の見出しを手で書き換えた。A〜Iを `id, title, content, due_date, created_at, updated_at, priority, done, notified_for` に戻す |
| LINE送信で 401 | チャネルアクセストークンの間違い（コピー漏れ・スペース混入） |
| LINE送信で 400 | ユーザーIDの間違い、または公式アカウントを友だち追加していない |
