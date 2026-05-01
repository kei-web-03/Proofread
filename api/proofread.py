"""
Vercel Serverless Function: 記事校正 API
Claude API で記事を自動校正し、問題箇所を JSON で返す
"""

import os
import json
import traceback
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import anthropic

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


def _call_claude(text: str) -> dict:
    """Claude API を呼び出し、校正結果を返す"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "error": "ANTHROPIC_API_KEY が設定されていません。Vercel の環境変数を確認してください。",
            "status": 500,
        }

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
            return {"issues": result["issues"], "status": 200}

        except json.JSONDecodeError:
            # フォールバック: JSON部分を抽出
            try:
                start = response_text.index("{")
                end = response_text.rindex("}") + 1
                result = json.loads(response_text[start:end])
                return {
                    "issues": result.get("issues", []),
                    "warning": "AIの応答をパースできませんでした。再度お試しください。",
                    "status": 200,
                }
            except (ValueError, json.JSONDecodeError):
                return {
                    "issues": [],
                    "warning": "AIの応答をパースできませんでした。再度お試しください。",
                    "status": 200,
                }

    except anthropic.AuthenticationError:
        return {"error": "API キーが無効です。Vercel の環境変数 ANTHROPIC_API_KEY を確認してください。", "status": 401}
    except anthropic.RateLimitError:
        return {"error": "API のレート制限に達しました。しばらく待ってから再度お試しください。", "status": 429}
    except anthropic.APITimeoutError:
        return {"error": "API がタイムアウトしました。記事が長すぎる可能性があります。短く分割してお試しください。", "status": 504}
    except anthropic.APIError as e:
        return {"error": f"API エラーが発生しました: {str(e)}", "status": 500}
    except Exception:
        return {"error": "予期しないエラーが発生しました。", "status": 500}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            self._send_json(400, {"detail": "無効なリクエストです。"})
            return

        text = data.get("text", "").strip()
        if not text:
            self._send_json(400, {"detail": "校正するテキストを入力してください。"})
            return

        result = _call_claude(text)
        status = result.pop("status", 200)

        if "error" in result:
            self._send_json(status, {"detail": result["error"]})
        else:
            result["raw_text"] = text
            self._send_json(200, result)

    def _send_json(self, status_code: int, data: dict):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
