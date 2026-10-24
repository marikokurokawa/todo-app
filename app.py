"""
Todoリストアプリ（Flask + Googleスプレッドシート）

- やることの登録・編集・削除
- タイトル・内容・期日の3項目
- 一覧ページ（期日順、期限切れは強調表示）
"""
import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone

import gspread
from flask import Flask, abort, flash, redirect, render_template, request, url_for

JST = timezone(timedelta(hours=9))
HEADERS = ["id", "title", "content", "due_date", "created_at", "updated_at"]
TITLE_MAX = 100

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

# ------------------------------------------------------------
# スプレッドシートとの接続
# ------------------------------------------------------------
_worksheet = None


def get_worksheet():
    """スプレッドシートの1枚目のシートを返す（初回のみ接続）。"""
    global _worksheet
    if _worksheet is None:
        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
        if creds_json:
            # 本番（Render など）：環境変数にJSONの中身をそのまま入れる
            gc = gspread.service_account_from_dict(json.loads(creds_json))
        else:
            # ローカル：credentials.json ファイルを読む
            gc = gspread.service_account(
                filename=os.environ.get("GOOGLE_CREDENTIALS_FILE", "credentials.json")
            )
        spreadsheet = gc.open_by_key(os.environ["SPREADSHEET_ID"])
        ws = spreadsheet.sheet1
        # シートが空ならヘッダー行を作る
        if not ws.row_values(1):
            ws.append_row(HEADERS, value_input_option="RAW")
        _worksheet = ws
    return _worksheet


def now_str():
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M")


# ------------------------------------------------------------
# データ操作
# ------------------------------------------------------------
def list_todos():
    ws = get_worksheet()
    # numericise_ignore=["all"] で「123」などの文字列が数値に変換されないようにする
    records = ws.get_all_records(numericise_ignore=["all"])
    todos = [{k: str(r.get(k, "")) for k in HEADERS} for r in records if r.get("id")]
    # 期日が近い順。期日なしは最後
    todos.sort(key=lambda t: (t["due_date"] == "", t["due_date"], t["created_at"]))
    return todos


def find_row(todo_id):
    """idからシート上の行番号（1始まり）を探す。見つからなければ None。"""
    ids = get_worksheet().col_values(1)
    try:
        return ids.index(todo_id) + 1
    except ValueError:
        return None


def get_todo(todo_id):
    row = find_row(todo_id)
    if row is None or row == 1:
        return None
    values = get_worksheet().row_values(row)
    values += [""] * (len(HEADERS) - len(values))
    return dict(zip(HEADERS, values))


def create_todo(title, content, due_date):
    ts = now_str()
    todo_id = uuid.uuid4().hex[:8]
    get_worksheet().append_row(
        [todo_id, title, content, due_date, ts, ts], value_input_option="RAW"
    )
    return todo_id


def update_todo(todo_id, title, content, due_date):
    row = find_row(todo_id)
    if row is None or row == 1:
        return False
    # B〜D列（タイトル・内容・期日）と F列（更新日時）を書き換える
    ws = get_worksheet()
    ws.update([[title, content, due_date]], f"B{row}:D{row}", value_input_option="RAW")
    ws.update([[now_str()]], f"F{row}", value_input_option="RAW")
    return True


def delete_todo(todo_id):
    row = find_row(todo_id)
    if row is None or row == 1:
        return False
    get_worksheet().delete_rows(row)
    return True


# ------------------------------------------------------------
# 入力チェック
# ------------------------------------------------------------
def read_form():
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    due_date = request.form.get("due_date", "").strip()

    errors = []
    if not title:
        errors.append("タイトルを入力してください。")
    elif len(title) > TITLE_MAX:
        errors.append(f"タイトルは{TITLE_MAX}文字以内で入力してください。")
    if due_date:
        try:
            date.fromisoformat(due_date)
        except ValueError:
            errors.append("期日の形式が正しくありません。")
    return {"title": title, "content": content, "due_date": due_date}, errors


# ------------------------------------------------------------
# ルーティング
# ------------------------------------------------------------
@app.route("/")
def index():
    todos = list_todos()
    today = datetime.now(JST).date().isoformat()
    return render_template("index.html", todos=todos, today=today)


@app.route("/todos/new", methods=["GET", "POST"])
def new_todo():
    if request.method == "POST":
        form, errors = read_form()
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("form.html", todo=form, mode="new"), 400
        create_todo(**form)
        flash("やることを登録しました。", "success")
        return redirect(url_for("index"))
    return render_template(
        "form.html", todo={"title": "", "content": "", "due_date": ""}, mode="new"
    )


@app.route("/todos/<todo_id>/edit", methods=["GET", "POST"])
def edit_todo(todo_id):
    todo = get_todo(todo_id)
    if todo is None:
        abort(404)
    if request.method == "POST":
        form, errors = read_form()
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("form.html", todo={**todo, **form}, mode="edit"), 400
        update_todo(todo_id, **form)
        flash("やることを更新しました。", "success")
        return redirect(url_for("index"))
    return render_template("form.html", todo=todo, mode="edit")


@app.route("/todos/<todo_id>/delete", methods=["POST"])
def remove_todo(todo_id):
    if not delete_todo(todo_id):
        abort(404)
    flash("やることを削除しました。", "success")
    return redirect(url_for("index"))


@app.errorhandler(404)
def not_found(_):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
