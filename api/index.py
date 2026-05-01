"""
Vercel Serverless Function: 記事校正 API
Flask アプリとして Claude API で記事を自動校正する
"""

import os
import json
from pathlib import Path

import anthropic
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

# ── フロントエンド配信 ──────────────────────────────────────
HTML_FILE = Path(__file__).resolve().parent.parent / "public" / "index.html"


@app.route("/")
def index():
    try:
        html = HTML_FILE.read_text(encoding="utf-8")
        return Response(html, mimetype="text/html")
    except FileNotFoundError:
        return "index.html not found", 404

# ── writing_rules.txt の読み込み ──────────────────────────────
RULES_FILE = Path(__file__).resolve().parent.parent / "writing_rules.txt"
DEFAULT_RULES = "・禁止表現: 非常に、における、において、最も、常に\n・回りくどい表現は避け、簡潔に書く\n・指示語の多用禁止\n・余計な修飾語の使用禁止"

if RULES_FILE.exists():
    writing_rules = RULES_FILE.read_text(encoding="utf-8")
else:
    writing_rules = DEFAULT_RULES

# ── システムプロンプト ──────────────────────────────────────
SYSTEM_PROMPT = f"""あなたはWebライターの記事を校正するAIアシスタントです。
以下の執筆ルールに従い、記事を分析してください。

【執筆ルール】
{writing_rules}

記事を分析し、以下の4種類の問題箇所を検出してください：

1. PROHIBITED: 執筆ルールに違反する禁止表現 → 修正案も提示
2. EVIDENCE: エビデンス（根拠・出典）の引用が望ましい主張や統計
3. COMPETITOR: 他社・競合他社への批判や否定的な比較表現
4. HARMFUL: 特定の人・グループが傷つく可能性のある表現

【重要なルール】
- original_text は記事中の原文と完全一致する文字列にしてください。前後の文脈を含めず、問題のある部分だけを正確に抜き出してください。
- PROHIBITEDタイプの場合は必ず suggestion（修正案）を提示してください。
- EVIDENCE / COMPETITOR / HARMFUL タイプの場合は suggestion は null にしてください。
- 問題が見つからない場合は空の配列を返してください。
- 回りくどい表現や冗長な文章もPROHIBITEDとして検出し、簡潔な修正案を提示してください。

必ず以下のJSON形式のみで返答してください。JSON以外のテキストは一切含めないでください：

{{
  "issues": [
    {{
      "type": "PROHIBITED",
      "original_text": "問題のある元の文章（完全一致する文字列）",
      "message": "表示するメッセージ",
      "suggestion": "修正案（PROHIBITEDの場合のみ）"
    }},
    {{
      "type": "EVIDENCE",
      "original_text": "エビデンスが必要な文章",
      "message": "エビデンスの引用を検討してください。",
      "suggestion": null
    }}
  ]
}}"""


@app.route("/api/proofread", methods=["POST", "OPTIONS"])
def proofread():
    # CORS preflight
    if request.method == "OPTIONS":
        response = jsonify({})
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    data = request.get_json(silent=True)
    if not data:
        return _error_response(400, "無効なリクエストです。")

    text = data.get("text", "").strip()
    if not text:
        return _error_response(400, "校正するテキストを入力してください。")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _error_response(
            500,
            "ANTHROPIC_API_KEY が設定されていません。Vercel の環境変数を確認してください。",
        )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"以下の記事を校正してください：\n\n{text}",
                }
            ],
        )

        response_text = message.content[0].text.strip()

        # JSONパース
        try:
            # ```json ... ``` で囲まれている場合の処理
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                json_lines = []
                in_block = False
                for line in lines:
                    if line.startswith("```") and not in_block:
                        in_block = True
                        continue
                    elif line.startswith("```") and in_block:
                        break
                    elif in_block:
                        json_lines.append(line)
                response_text = "\n".join(json_lines)

            result = json.loads(response_text)
            if "issues" not in result:
                result = {"issues": []}
            return _success_response({"issues": result["issues"], "raw_text": text})

        except json.JSONDecodeError:
            # フォールバック: JSON部分を抽出
            try:
                start = response_text.index("{")
                end = response_text.rindex("}") + 1
                result = json.loads(response_text[start:end])
                return _success_response(
                    {
                        "issues": result.get("issues", []),
                        "raw_text": text,
                        "warning": "AIの応答をパースできませんでした。再度お試しください。",
                    }
                )
            except (ValueError, json.JSONDecodeError):
                return _success_response(
                    {
                        "issues": [],
                        "raw_text": text,
                        "warning": "AIの応答をパースできませんでした。再度お試しください。",
                    }
                )

    except anthropic.AuthenticationError:
        return _error_response(
            401, "API キーが無効です。Vercel の環境変数 ANTHROPIC_API_KEY を確認してください。"
        )
    except anthropic.RateLimitError:
        return _error_response(
            429, "API のレート制限に達しました。しばらく待ってから再度お試しください。"
        )
    except anthropic.APITimeoutError:
        return _error_response(
            504,
            "API がタイムアウトしました。記事が長すぎる可能性があります。短く分割してお試しください。",
        )
    except anthropic.APIError as e:
        return _error_response(500, f"API エラーが発生しました: {str(e)}")
    except Exception:
        return _error_response(500, "予期しないエラーが発生しました。")


def _success_response(data: dict):
    response = jsonify(data)
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


def _error_response(status_code: int, message: str):
    response = jsonify({"detail": message})
    response.status_code = status_code
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response

