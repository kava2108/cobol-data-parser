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

# COPYBOOK ディレクトリを指定（複数指定可）
cobol-data-parser --copybook-dir ./copybooks --copybook-dir ../shared customer.cob
```

### Python API

```python
from cobol_data_parser import parse, emit, to_json

with open("customer.cob") as f:
    text = f.read()

items    = parse(text)                              # list[DataItem]
items    = parse(text, copybook_dirs=["./cpy"])     # COPYBOOK 展開あり
data     = emit(items)                             # dict（JSON シリアライズ可能）
json_str = to_json(items)                          # str
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
| `REDEFINES` | 元フィールドの `"union"` 配列にエイリアスとして折り畳む |
| `OCCURS n TIMES` | 固定長テーブル。グループ項目は `"fields"` エンベロープで包む |
| `OCCURS n TO m TIMES DEPENDING ON field` | 可変長テーブル（ODO）。`"occurs": {"min", "max", "depending_on"}` で表現 |
| `COPY <name>` | `--copybook-dir` 指定時にインライン展開（`REPLACING` 対応） |
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

### グループ項目

```json
{
  "CUST-NAME": {
    "FIRST-NAME": { "type": "string", "length": 10 },
    "LAST-NAME":  { "type": "string", "length": 10 }
  }
}
```

### OCCURS 付きグループ項目（固定長テーブル）

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

### OCCURS DEPENDING ON（可変長テーブル）

```cobol
05 ITEM-COUNT PIC 9(3).
05 ITEMS OCCURS 1 TO 100 TIMES DEPENDING ON ITEM-COUNT.
   10 ITEM-ID  PIC 9(5).
```

```json
{
  "ITEM-COUNT": { "type": "numeric", "length": 3 },
  "ITEMS": {
    "occurs": { "min": 1, "max": 100, "depending_on": "ITEM-COUNT" },
    "fields": {
      "ITEM-ID": { "type": "numeric", "length": 5 }
    }
  }
}
```

### REDEFINES グラフ

REDEFINES エイリアスは元フィールドの `"union"` 配列に折り畳まれます。
兄弟フィールドとして独立して出現することはありません。

```cobol
05 AMOUNT-DISPLAY PIC X(8).
05 AMOUNT-PACKED  REDEFINES AMOUNT-DISPLAY PIC S9(9)V99 COMP-3.
05 AMOUNT-BINARY  REDEFINES AMOUNT-DISPLAY PIC S9(9) COMP.
```

```json
{
  "AMOUNT-DISPLAY": {
    "type": "string",
    "length": 8,
    "union": [
      { "name": "AMOUNT-PACKED", "type": "packed-decimal", "precision": 9, "scale": 2, "usage": "COMP-3" },
      { "name": "AMOUNT-BINARY", "type": "binary", "length": 9, "usage": "COMP" }
    ]
  }
}
```

### COPYBOOK 展開

```bash
# ディレクトリ内の .cpy / .cob / .CBL ファイルを検索して自動展開
cobol-data-parser --copybook-dir ./copybooks main.cob
```

`REPLACING` 句（擬似テキスト `==...== BY ==...==` および単語置換）に対応しています。  
ネストした COPY（コピーブック内の COPY）も再帰的に展開します。

## 開発

```bash
pip install -e ".[dev]"
pytest
```

## FUTURE WORK

- **DB スキーマ生成** — `01` レベルレコードから SQL DDL（`CREATE TABLE`）を出力。
- **TypeScript 型生成** — モダンバックエンドで直接使える `interface` / `type` 宣言を出力。
- **OpenAPI コンポーネント生成** — REST API ドキュメント向けに `components/schemas` エントリを出力。
- **`COMP` / `COMP-3` バイトサイズ計算** — バイナリおよびパック10進数フィールドの正確なストレージサイズを算出。
- **レベル 66（`RENAMES`）対応** — RENAMES 句で作成されるフィールドエイリアスのモデル化。
- **フルプログラム入力対応** — COBOL ソースファイル全体から DATA DIVISION を自動的に抽出（FILE SECTION の FD 記述子を含む）。

## ライセンス

MIT
