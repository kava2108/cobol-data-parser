# cobol-data-parser

COBOL の DATA DIVISION を解析し、JSON に変換するツール。

COBOL モダナイゼーションの第一歩は、データ構造の把握です。本ツールは DATA DIVISION の
`01` / `05` / `10` ... レベル階層を読み取り、**PIC/USAGE から物理バイト長を算出し**、
**各フィールドにバイトオフセットを付与した**上で、スキーマ生成・API 設計・LLM を用いた
移行ワークフローで活用できる JSON 表現を出力します。さらに、そのオフセット情報を使って
**実際の EBCDIC/COMP-3/バイナリのレコードをデコード**することもできます。

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
    "CUST-ID": { "type": "numeric", "length": 5, "offset": 0, "bytes": 5 },
    "CUST-NAME": {
      "FIRST-NAME": { "type": "string", "length": 10, "offset": 5, "bytes": 10 },
      "LAST-NAME":  { "type": "string", "length": 10, "offset": 15, "bytes": 10 }
    },
    "BALANCE": { "type": "signed-decimal", "precision": 7, "scale": 2, "offset": 25, "bytes": 9 }
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
from cobol_data_parser import parse, emit, to_json, decode_record, iter_records

with open("customer.cob") as f:
    text = f.read()

items    = parse(text)                              # list[DataItem]（offset/bytes 算出済み）
items    = parse(text, copybook_dirs=["./cpy"])     # COPYBOOK 展開あり
data     = emit(items)                             # dict（JSON シリアライズ可能）
json_str = to_json(items)                          # str

# 実データ（EBCDIC 等でエンコードされたバイト列）をデコード
with open("customer.dat", "rb") as f:
    raw = f.read()

record = decode_record(items[0], raw)               # 1レコード分の dict
records = list(iter_records(items[0], raw))          # 固定長ファイル全体を1レコードずつ
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

### バイト長・オフセットの算出（型ロワリング／AST正規化）

PIC と USAGE の組み合わせから、実際の物理ストレージサイズを算出し `"bytes"` として出力します。

| PIC / USAGE | バイト長 |
|---|---|
| DISPLAY（既定） | 桁数と同じ（符号はオーバーパンチのため追加バイトなし） |
| `COMP-3` / `PACKED-DECIMAL` | `桁数 // 2 + 1` |
| `COMP` / `COMP-4` / `COMP-5` / `BINARY` | 桁数に応じて 2 / 4 / 8 バイト（IBM標準の階層） |
| `COMP-1` / `COMP-2` | 固定 4 / 8 バイト |
| `INDEX` / `POINTER` | 固定 4 バイト |

さらに各フィールドには、レコード先頭からの `"offset"` が付与されます。`01`/`77` レベルの
各レコードは offset 0 起点です。`REDEFINES` エイリアスは対象と同じ offset を共有し
（カーソルは進めず、幅は base とエイリアスのうち最大値を採用）、`OCCURS n TIMES` は
要素サイズ×回数分カーソルを進めます。`OCCURS ... DEPENDING ON` に到達すると、
実データがないと長さが確定しないため、それ以降の兄弟フィールドの `"offset"` は
`null`（Python では `None`）になります — この先はデコード時に動的に解決されます
（後述の「デコード」セクション参照）。

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

各項目には可能な限り `"offset"`（レコード先頭からのバイト位置）と `"bytes"`
（1件分の物理バイト長）が付与されます。算出方法は前述の
「バイト長・オフセットの算出」を参照してください。

### 基本項目（elementary）

```json
{ "type": "string", "length": 10, "offset": 0, "bytes": 10 }
{ "type": "signed-decimal", "precision": 7, "scale": 2, "offset": 10, "bytes": 9 }
{ "type": "packed-decimal", "precision": 9, "scale": 2, "usage": "COMP-3", "offset": 19, "bytes": 6 }
```

### グループ項目

```json
{
  "CUST-NAME": {
    "FIRST-NAME": { "type": "string", "length": 10, "offset": 5, "bytes": 10 },
    "LAST-NAME":  { "type": "string", "length": 10, "offset": 15, "bytes": 10 }
  }
}
```

OCCURS を持たないグループ自身は `"fields"` エンベロープでは包まれず、子フィールドを
直接展開します（そのため自身の `"offset"`/`"bytes"` は出力されません）。

### OCCURS 付きグループ項目（固定長テーブル）

```json
{
  "ORDER-LINES": {
    "offset": 0,
    "bytes": 16,
    "occurs": 10,
    "fields": {
      "ORDER-ID":  { "type": "numeric", "length": 7, "offset": 0, "bytes": 7 },
      "ORDER-AMT": { "type": "signed-decimal", "precision": 7, "scale": 2, "offset": 7, "bytes": 9 }
    }
  }
}
```

`"bytes"` はテーブルの **1行分** のサイズです（`occurs` 回分を掛けた合計ではありません）。
親レベルのオフセット計算では `bytes × occurs` 分だけカーソルが進みます。

### OCCURS DEPENDING ON（可変長テーブル）

```cobol
05 ITEM-COUNT PIC 9(3).
05 ITEMS OCCURS 1 TO 100 TIMES DEPENDING ON ITEM-COUNT.
   10 ITEM-ID  PIC 9(5).
05 TRAILER PIC X(3).
```

```json
{
  "ITEM-COUNT": { "type": "numeric", "length": 3, "offset": 0, "bytes": 3 },
  "ITEMS": {
    "offset": 3,
    "occurs": { "min": 1, "max": 100, "depending_on": "ITEM-COUNT" },
    "fields": {
      "ITEM-ID": { "type": "numeric", "length": 5, "offset": 3, "bytes": 5 }
    }
  },
  "TRAILER": { "type": "string", "length": 3 }
}
```

`ITEMS` は実データがないと長さが確定しないため `"bytes"` は出力されません。
`ITEMS` より後ろの `TRAILER` も `"offset"` を静的には算出できないため省略されます
（実データを使った動的な解決は後述の「デコード」セクションを参照）。

### REDEFINES グラフ

REDEFINES エイリアスは元フィールドの `"union"` 配列に折り畳まれます。
兄弟フィールドとして独立して出現することはありません。エイリアスは対象と
同じ `"offset"` を共有します（同じストレージ領域を指すため）。

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
    "offset": 0,
    "bytes": 8,
    "union": [
      { "name": "AMOUNT-PACKED", "type": "packed-decimal", "precision": 9, "scale": 2, "offset": 0, "bytes": 6, "usage": "COMP-3" },
      { "name": "AMOUNT-BINARY", "type": "binary", "length": 9, "offset": 0, "bytes": 4, "usage": "COMP" }
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

## デコード（コーデック層）

`parse()` で得た `DataItem` ツリー（offset/bytes 算出済み）を使って、実際のレコード
バイト列を Python の値にデコードできます。

```python
from cobol_data_parser import parse, decode_record, iter_records

items = parse(cobol_source)
record = items[0]

with open("customer.dat", "rb") as f:
    raw = f.read()

decode_record(record, raw)                          # 1レコード分の dict
decode_record(record, raw, encoding="cp037")         # 既定は cp037（EBCDIC US/Canada）
decode_record(record, raw, byte_order="little")      # COMP-5 等で native binary が little-endian の場合

list(iter_records(record, file_bytes))               # 固定長ファイル全体を1レコードずつデコード
```

### 対応フォーマット

| 種別 | デコード方法 |
|---|---|
| DISPLAY テキスト（`string`/`alphabetic`/編集項目） | 指定エンコーディング（既定 `cp037`）でデコードし、末尾スペースを除去 |
| DISPLAY 数値（ゾーン10進数） | 下位ニブル = 桁。符号付きは最終バイトのゾーンニブル（`0xC`/`0xF`=正、`0xD`/`0xB`=負）で符号判定 |
| `COMP-3` / `PACKED-DECIMAL`（パック10進数） | BCD ニブル展開。小数点は `Decimal` で正確に配置（浮動小数点誤差なし） |
| `COMP` / `COMP-4` / `COMP-5` / `BINARY` | 2/4/8 バイトの符号付き・符号なし整数。`byte_order="big"`（既定）/ `"little"` |

`COMP-1` / `COMP-2`（浮動小数点）と `INDEX` / `POINTER` は未対応で、`NotImplementedError`
を送出します。

### REDEFINES

REDEFINES されたフィールドは、JSON スキーマの `"union"` とは異なり、同じバイト列を
**両方の解釈でデコードして、両方とも兄弟キーとして** 返します。どちらの解釈が有効かは
（通常は別フィールドの判別値などから）呼び出し側が判断してください。

### OCCURS DEPENDING ON（動的解決）

静的なオフセット計算（`parse()` 時点）では、ODO フィールドより後ろのオフセットは
実データがないと確定できないため `None` になります（前述）。しかしデコード時には
既にデコード済みの兄弟フィールドの値（実際の件数）を使って実際の長さを解決できるため、
ODO より後ろのフィールドも正しくデコードされます。これが型ロワリング／AST 正規化の
静的レイヤーに対して、コーデック層が実データを使って実現する価値です。

## 開発

```bash
pip install -e ".[dev]"
pytest
```

## FUTURE WORK

- **DB スキーマ生成** — `01` レベルレコードから SQL DDL（`CREATE TABLE`）を出力。
- **TypeScript 型生成** — モダンバックエンドで直接使える `interface` / `type` 宣言を出力。
- **OpenAPI コンポーネント生成** — REST API ドキュメント向けに `components/schemas` エントリを出力。
- **`COMP-1` / `COMP-2` 浮動小数点デコード** — IEEE754 または IBM 16進浮動小数点でのデコード対応。
- **`SIGN IS SEPARATE` 句対応** — 符号を別バイトとして持つ DISPLAY 数値のパース・デコード。
- **レベル 66（`RENAMES`）対応** — RENAMES 句で作成されるフィールドエイリアスのモデル化。
- **フルプログラム入力対応** — COBOL ソースファイル全体から DATA DIVISION を自動的に抽出（FILE SECTION の FD 記述子を含む）。
- **エンコード（値 → バイト列）** — 現在はデコード（バイト列 → 値）のみ対応。逆方向の書き出しは未実装。

## ライセンス

MIT
