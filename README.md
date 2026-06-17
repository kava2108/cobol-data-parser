# cobol-data-parser

COBOL の DATA DIVISION を解析し、JSON に変換するツール。

COBOL モダナイゼーションの第一歩は、データ構造の把握です。本ツールは DATA DIVISION の
`01` / `05` / `10` ... レベル階層を読み取り、スキーマ生成・API 設計・LLM を用いた
移行ワークフローで活用できる JSON 表現を出力します。

## 使用例

**入力** (`customer.cob`):

```cobol
01 CUSTOMER-REC.
   05 CUST-ID        PIC 9(5).
   05 CUST-NAME.
      10 FIRST-NAME  PIC X(10).
      10 LAST-NAME   PIC X(10).
   05 BALANCE        PIC S9(7)V99.
```

**出力**:

```json
{
  "CUSTOMER-REC": {
    "CUST-ID": { "type": "numeric", "length": 5 },
    "CUST-NAME": {
      "FIRST-NAME": { "type": "string", "length": 10 },
      "LAST-NAME":  { "type": "string", "length": 10 }
    },
    "BALANCE": { "type": "signed-decimal", "precision": 7, "scale": 2 }
  }
}
```

## インストール

```bash
pip install cobol-data-parser
```

ソースからインストールする場合:

```bash
git clone https://github.com/your-org/cobol-data-parser
cd cobol-data-parser
pip install -e ".[dev]"
```

Python 3.10 以上が必要です。

## 使い方

### CLI

```bash
# ファイルを指定
cobol-data-parser customer.cob

# 標準入力から読み込む
cat customer.cob | cobol-data-parser -

# ファイルに出力
cobol-data-parser customer.cob -o customer.json

# 固定形式を強制（シーケンス番号付き、1〜72桁）
cobol-data-parser --fixed customer.cob

# 自由形式を強制
cobol-data-parser --free customer.cob
```

### Python API

```python
from cobol_data_parser import parse, emit, to_json

with open("customer.cob") as f:
    text = f.read()

items    = parse(text)      # list[DataItem]
data     = emit(items)      # dict（JSON シリアライズ可能）
json_str = to_json(items)   # str
```

## 対応 COBOL 機能

### PIC 句の型

| PIC パターン | JSON `"type"` |
|---|---|
| `X(n)`、`XXX` | `"string"` |
| `A(n)`、`AAA` | `"alphabetic"` |
| `9(n)`、`999` | `"numeric"` |
| `S9(n)` | `"signed-numeric"` |
| `9(n)V9(m)` | `"decimal"` |
| `S9(n)V9(m)` | `"signed-decimal"` |
| 混合・編集型 | `"alphanumeric-edited"` / `"numeric-edited"` |

`X(10)` のような繰り返し記法と `XXXXXXXXXX` のような明示的繰り返しの両方に対応しています。

### USAGE 句

`COMP` / `COMP-4` / `BINARY` / `COMP-5` は PIC カテゴリを `"binary"` に上書きします。  
`COMP-3` / `PACKED-DECIMAL` は `"packed-decimal"` に上書きします。  
`DISPLAY`（デフォルト）は出力に含まれません。

### 構造句

| 句 | 動作 |
|---|---|
| `REDEFINES` | `"redefines": "<対象フィールド名>"` をフィールドに付加 |
| `OCCURS n TIMES` | `"occurs": n` を付加。グループ項目は `"fields"` エンベロープで包む |
| `FILLER` | 出力から除外 |
| レベル 88（条件名） | 出力から除外 |
| レベル 77（独立項目） | トップレベルのエントリとして出力 |

### フォーマット自動検出

ソースのフォーマットは自動的に判定されます。

- **固定形式** — 行頭 6 文字がすべて数字（シーケンス番号）の行が存在する場合に判定。1〜6桁目を除去し、7桁目をインジケータ（`*` = コメント、`-` = 継続行）として処理します。
- **自由形式** — それ以外の入力。`*>` で始まる行をコメントとして扱います。

CLI の `--fixed` / `--free` オプション、または `parse()` の `fixed_format=True/False` 引数で強制指定できます。

## 出力スキーマ

### 基本項目（elementary）

```json
{ "type": "string", "length": 10 }
{ "type": "signed-decimal", "precision": 7, "scale": 2 }
{ "type": "packed-decimal", "precision": 9, "scale": 2, "usage": "COMP-3" }
```

### グループ項目（OCCURS / REDEFINES なし）

```json
{
  "CUST-NAME": {
    "FIRST-NAME": { "type": "string", "length": 10 },
    "LAST-NAME":  { "type": "string", "length": 10 }
  }
}
```

### OCCURS 付きグループ項目

```json
{
  "ORDER-LINES": {
    "occurs": 10,
    "fields": {
      "ORDER-ID":  { "type": "numeric", "length": 7 },
      "ORDER-AMT": { "type": "signed-decimal", "precision": 7, "scale": 2 }
    }
  }
}
```

## 開発

```bash
pip install -e ".[dev]"
pytest
```

## FUTURE WORK

- **COPYBOOK 展開** — `COPY` 文を解決して外部コピーブックをインライン展開してからパース。
- **`OCCURS DEPENDING ON` 対応** — ODO ターゲットフィールドを参照する可変長テーブルのサポート。
- **`REDEFINES` グラフ化** — 同一フィールドの全 REDEFINES エイリアスをユニオン型としてモデル化し、正確なストレージサイズ計算を実現。
- **DB スキーマ生成** — `01` レベルレコードから SQL DDL（`CREATE TABLE`）を出力。
- **TypeScript 型生成** — モダンバックエンドで直接使える `interface` / `type` 宣言を出力。
- **OpenAPI コンポーネント生成** — REST API ドキュメント向けに `components/schemas` エントリを出力。
- **`COMP` / `COMP-3` バイトサイズ計算** — バイナリおよびパック10進数フィールドの正確なストレージサイズを算出。
- **レベル 66（`RENAMES`）対応** — RENAMES 句で作成されるフィールドエイリアスのモデル化。
- **フルプログラム入力対応** — COBOL ソースファイル全体から DATA DIVISION を自動的に抽出（FILE SECTION の FD 記述子を含む）。

## ライセンス

MIT
