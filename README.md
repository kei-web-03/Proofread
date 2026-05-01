# 📝 記事校正システム

Webライターが執筆した記事をClaude AIで自動校正するWebアプリケーションです。
記事内の問題箇所を色付きのハイライトで視覚的に表示し、修正提案を行います。

## デプロイ方法（Vercel）

### 1. GitHub にプッシュ

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/your-username/proofread.git
git push -u origin main
```

### 2. Vercel にデプロイ

1. [Vercel](https://vercel.com) にログイン
2. 「Add New → Project」でGitHubリポジトリを選択
3. そのまま「Deploy」をクリック

### 3. 環境変数の設定（重要）

1. Vercel ダッシュボードでプロジェクトを開く
2. **Settings → Environment Variables** に移動
3. 以下を追加：

| Key | Value |
|---|---|
| `ANTHROPIC_API_KEY` | `sk-ant-xxxxxxxxxxxxx` |

4. **Redeploy** して反映させる

## ローカル開発

Vercel CLI を使ってローカルで動作確認できます：

```bash
npm i -g vercel
vercel env pull .env.local   # 環境変数を取得
vercel dev                   # ローカルサーバー起動
```

## 使い方

1. テキストエリアに校正したい記事を貼り付ける
2. 「校正する」ボタンをクリック（または `Ctrl+Enter`）
3. 右側に校正結果がカラーハイライト付きで表示される
4. ハイライト箇所をホバーで詳細確認、クリックで一覧パネルを表示

## カラーハイライトの種類

| 色 | 種別 | 内容 |
|---|---|---|
| 🔴 赤 | 禁止表現 | 修正案を表示 |
| 🟡 黄 | エビデンス不足 | 引用の検討を促す |
| 🟠 オレンジ | 他社批判 | 修正の検討を促す |
| 🟠 オレンジ | 有害表現 | 修正の検討を促す |

## 執筆ルール

`writing_rules.txt` を編集することで、校正ルールをカスタマイズできます。
変更後は再デプロイが必要です。

## ファイル構成

```
proofread/
├── api/
│   └── proofread.py    # Vercel Serverless Function
├── public/
│   └── index.html      # フロントエンド
├── writing_rules.txt   # 執筆ルールファイル
├── vercel.json         # Vercel設定
├── requirements.txt    # Python依存パッケージ
├── .gitignore          # Git除外設定
└── README.md           # このファイル
```
