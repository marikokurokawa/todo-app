"""
Todoリストアプリ（Flask + Googleスプレッドシート + LINE Messaging API）

課題1
- やることの登録・編集・削除
- タイトル・内容・期日の3項目
- 一覧ページ

課題2で追加した機能
1. 完了チェック（完了／未完了の切り替え、未完了・完了・すべての絞り込み）
2. 重要度（高・中・低）の設定と、期日順／重要度順の並び替え
3. 期日の前日にLINEへリマインドを自動送信（/cron/remind を毎朝呼び出す）
"""
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import gspread
import requests
from flask import (
    Flask, abort, flash, jsonify, redirect, render_template, request, url_for,
)

JST = timezone(timedelta(hours=9))

# 列の順番は課題1と同じ A〜F のまま、G〜I に新しい列を足す
# （課題1で作ったスプレッドシートをそのまま使えるようにするため）
HEADERS = [
    "id", "title", "content", "due_date", "created_at", "updated_at",  # A〜F
    "priority",     # G: 重要度 high / medium / low
    "done",         # H: 完了なら "1"、未完了なら空
    "notified_for", # I: LINEで通知済みの期日（期日を変えたら再通知される）
]
TITLE_MAX = 100

PRIORITIES = {"high": "高", "medium": "中", "low": "低"}
PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}
DEFAULT_PRIORITY = "medium"

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"

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
        ensure_headers(ws)
        _worksheet = ws
    return _worksheet


def ensure_headers(ws):
    """1行目の見出しを用意する。課題1のシート（A〜Fだけ）なら G〜I を書き足す。"""
    current = ws.row_values(1)
    if current == HEADERS:
        return
    if not current:
        ws.append_row(HEADERS, value_input_option="RAW")
    elif current == HEADERS[: len(current)]:
        ws.update([HEADERS], "A1:I1", value_input_option="RAW")
    else:
        raise RuntimeError(
            "スプレッドシートの1行目が想定と違います: " + ", ".join(current)
        )


def now_jst():
    return datetime.now(JST)


def now_str():
    return now_jst().strftime("%Y-%m-%d %H:%M")


def today_str():
    return now_jst().date().isoformat()


# ------------------------------------------------------------
# データ操作
# ------------------------------------------------------------
def normalize(record):
    """シートの1行を、画面で扱いやすい形に整える。"""
    todo = {k: str(record.get(k, "")) for k in HEADERS}
    if todo["priority"] not in PRIORITIES:
        todo["priority"] = DEFAULT_PRIORITY  # 課題1で登録した行は「中」として扱う
    todo["done"] = todo["done"] == "1"
    todo["priority_label"] = PRIORITIES[todo["priority"]]
    return todo


def all_todos():
    ws = get_worksheet()
    # numericise_ignore=["all"] で「123」などの文字列が数値に変換されないようにする
    records = ws.get_all_records(numericise_ignore=["all"])
    return [normalize(r) for r in records if r.get("id")]


def sort_todos(todos, sort):
    def by_due(t):
        # 期日なしは最後
        return (t["due_date"] == "", t["due_date"])

    def by_priority(t):
        return PRIORITY_RANK[t["priority"]]

    if sort == "priority":
        key = lambda t: (by_priority(t), *by_due(t), t["created_at"])
    else:
        key = lambda t: (*by_due(t), by_priority(t), t["created_at"])
    # 未完了を上、完了済みを下にまとめる
    return sorted(todos, key=lambda t: (t["done"], key(t)))


def find_row(todo_id):
    """idからシート上の行番号（1始まり）を探す。見つからなければ None。"""
    ids = get_worksheet().col_values(1)
    try:
        row = ids.index(todo_id) + 1
    except ValueError:
        return None
    return None if row == 1 else row


def get_todo(todo_id):
    row = find_row(todo_id)
    if row is None:
        return None
    values = get_worksheet().row_values(row)
    values += [""] * (len(HEADERS) - len(values))
    return normalize(dict(zip(HEADERS, values)))


def create_todo(title, content, due_date, priority):
    ts = now_str()
    todo_id = uuid.uuid4().hex[:8]
    get_worksheet().append_row(
        [todo_id, title, content, due_date, ts, ts, priority, "", ""],
        value_input_option="RAW",
    )
    return todo_id


def update_todo(todo_id, title, content, due_date, priority):
    row = find_row(todo_id)
    if row is None:
        return False
    ws = get_worksheet()
    ws.batch_update(
        [
            {"range": f"B{row}:D{row}", "values": [[title, content, due_date]]},
            {"range": f"F{row}:G{row}", "values": [[now_str(), priority]]},
        ],
        value_input_option="RAW",
    )
    return True


def set_done(todo_id, done):
    row = find_row(todo_id)
    if row is None:
        return False
    ws = get_worksheet()
    ws.batch_update(
        [
            {"range": f"F{row}", "values": [[now_str()]]},
            {"range": f"H{row}", "values": [["1" if done else ""]]},
        ],
        value_input_option="RAW",
    )
    return True


def delete_todo(todo_id):
    row = find_row(todo_id)
    if row is None:
        return False
    get_worksheet().delete_rows(row)
    return True


# ------------------------------------------------------------
# LINE リマインド
# ------------------------------------------------------------
def send_line_message(text):
    """LINE Messaging API のプッシュメッセージで自分に送る。"""
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    if not token or not user_id:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN と LINE_USER_ID を設定してください。")
    res = requests.post(
        LINE_PUSH_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"to": user_id, "messages": [{"type": "text", "text": text[:5000]}]},
        timeout=10,
    )
    if res.status_code != 200:
        raise RuntimeError(f"LINEへの送信に失敗しました（{res.status_code}）: {res.text}")


def build_reminder(todos, due_date):
    lines = [f"【明日（{due_date}）が期日のやること】"]
    for t in sorted(todos, key=lambda t: PRIORITY_RANK[t["priority"]]):
        lines.append(f"・[重要度:{t['priority_label']}] {t['title']}")
    app_url = os.environ.get("APP_URL")
    if app_url:
        lines.append("")
        lines.append(f"一覧を見る: {app_url}")
    return "\n".join(lines)


def run_reminder():
    """明日が期日で、未完了・未通知のやることをまとめてLINEに送る。"""
    tomorrow = (now_jst().date() + timedelta(days=1)).isoformat()
    targets = [
        t for t in all_todos()
        if not t["done"] and t["due_date"] == tomorrow and t["notified_for"] != tomorrow
    ]
    if not targets:
        return {"sent": 0, "date": tomorrow}

    send_line_message(build_reminder(targets, tomorrow))

    # 同じ通知を2回送らないよう「通知済み」を記録する
    ws = get_worksheet()
    updates = []
    for t in targets:
        row = find_row(t["id"])
        if row:
            updates.append({"range": f"I{row}", "values": [[tomorrow]]})
    if updates:
        ws.batch_update(updates, value_input_option="RAW")
    return {"sent": len(targets), "date": tomorrow}


def check_cron_token():
    """/cron/ のURLを知っている人だけが実行できるようにする。"""
    secret = os.environ.get("CRON_SECRET")
    given = request.headers.get("X-Cron-Token") or request.args.get("token")
    if not secret or given != secret:
        abort(403)


# ------------------------------------------------------------
# 入力チェック
# ------------------------------------------------------------
def read_form():
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    due_date = request.form.get("due_date", "").strip()
    priority = request.form.get("priority", DEFAULT_PRIORITY)

    errors = []
    if not title:
        errors.append("タイトルを入力してください。")
    elif len(title) > TITLE_MAX:
        errors.append(f"タイトルは{TITLE_MAX}文字以内で入力してください。")
    if due_date:
        try:
            datetime.strptime(due_date, "%Y-%m-%d")
        except ValueError:
            errors.append("期日の形式が正しくありません。")
    if priority not in PRIORITIES:
        errors.append("重要度を選んでください。")
        priority = DEFAULT_PRIORITY
    form = {"title": title, "content": content, "due_date": due_date, "priority": priority}
    return form, errors


EMPTY_FORM = {"title": "", "content": "", "due_date": "", "priority": DEFAULT_PRIORITY}


# ------------------------------------------------------------
# ルーティング
# ------------------------------------------------------------
@app.route("/")
def index():
    show = request.args.get("show", "active")    # active / done / all
    sort = request.args.get("sort", "due")       # due / priority
    if show not in ("active", "done", "all"):
        show = "active"
    if sort not in ("due", "priority"):
        sort = "due"

    todos = all_todos()
    counts = {
        "active": sum(not t["done"] for t in todos),
        "done": sum(t["done"] for t in todos),
        "all": len(todos),
    }
    if show == "active":
        todos = [t for t in todos if not t["done"]]
    elif show == "done":
        todos = [t for t in todos if t["done"]]

    return render_template(
        "index.html",
        todos=sort_todos(todos, sort),
        today=today_str(),
        show=show,
        sort=sort,
        counts=counts,
    )


def back_to_list():
    """一覧の絞り込み・並び替えを保ったまま一覧に戻る。"""
    return redirect(url_for(
        "index",
        show=request.values.get("show", "active"),
        sort=request.values.get("sort", "due"),
    ))


@app.route("/todos/new", methods=["GET", "POST"])
def new_todo():
    if request.method == "POST":
        form, errors = read_form()
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("form.html", todo=form, mode="new",
                                   priorities=PRIORITIES), 400
        create_todo(**form)
        flash("やることを登録しました。", "success")
        return redirect(url_for("index"))
    return render_template("form.html", todo=EMPTY_FORM, mode="new",
                           priorities=PRIORITIES)


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
            return render_template("form.html", todo={**todo, **form}, mode="edit",
                                   priorities=PRIORITIES), 400
        update_todo(todo_id, **form)
        flash("やることを更新しました。", "success")
        return redirect(url_for("index"))
    return render_template("form.html", todo=todo, mode="edit", priorities=PRIORITIES)


@app.route("/todos/<todo_id>/toggle", methods=["POST"])
def toggle_todo(todo_id):
    todo = get_todo(todo_id)
    if todo is None:
        abort(404)
    set_done(todo_id, not todo["done"])
    if todo["done"]:
        flash(f"「{todo['title']}」を未完了に戻しました。", "success")
    else:
        flash(f"「{todo['title']}」を完了にしました。", "success")
    return back_to_list()


@app.route("/todos/<todo_id>/delete", methods=["POST"])
def remove_todo(todo_id):
    if not delete_todo(todo_id):
        abort(404)
    flash("やることを削除しました。", "success")
    return back_to_list()


@app.route("/cron/remind", methods=["GET", "POST"])
def cron_remind():
    """毎朝 GitHub Actions などから呼び出す。?test=1 ならテストメッセージを送る。"""
    check_cron_token()
    try:
        if request.args.get("test"):
            send_line_message("Todoリストアプリからのテスト通知です。LINE連携は正常に動いています。")
            return jsonify({"ok": True, "test": True})
        result = run_reminder()
        return jsonify({"ok": True, **result})
    except RuntimeError as e:
        app.logger.error(str(e))
        return jsonify({"ok": False, "error": str(e)}), 500


@app.errorhandler(404)
def not_found(_):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
