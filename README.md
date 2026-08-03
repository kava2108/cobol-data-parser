# cobol-data-parser

COBOL の DATA DIVISION と PROCEDURE DIVISION を解析するツール群。

COBOL モダナイゼーションの第一歩は、データ構造とロジックの把握です。本パッケージは
2つのツールで構成されます。

- **`cobol-data-parser`** — DATA DIVISION の `01` / `05` / `10` ... レベル階層を読み取り、
  **PIC/USAGE から物理バイト長を算出し**、**各フィールドにバイトオフセットを付与した**上で、
  スキーマ生成・API 設計・LLM を用いた移行ワークフローで活用できる JSON 表現を出力します。
  さらに、そのオフセット情報を使って**実際の EBCDIC/COMP-3/バイナリのレコードをデコード**
  し、逆に Python の値からレコードバイト列へ**エンコード**することもできます。デコード後の
  値の形をそのまま **SQL DDL / TypeScript / OpenAPI スキーマ**としても出力できます。
- **`cobol-proc-parser`** — PROCEDURE DIVISION の SECTION・段落構造を読み取り、
  `PERFORM` による**制御フローグラフ**（`IF`/`EVALUATE` の分岐条件付き）と `CALL` による
  **プログラム間依存関係グラフ**を JSON / Graphviz DOT / SQL / Python の各形式で出力します。

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

# データ項目定義書（Markdown表）として出力
cobol-data-parser --format markdown customer.cob

# SQL DDL（CREATE TABLE）として出力
cobol-data-parser --format sql-ddl customer.cob

# TypeScript interface として出力
cobol-data-parser --format typescript customer.cob

# OpenAPI components/schemas として出力
cobol-data-parser --format openapi customer.cob
```

`sql-ddl` / `typescript` / `openapi` は `emit()` の JSON メタデータ形状ではなく、
`decode_record()` が実際に返す**デコード後の値の形**を反映します（詳細は後述の
「SQL DDL / TypeScript / OpenAPI 生成」を参照）。

### Python API

```python
from cobol_data_parser import parse, emit, to_json, to_markdown_table, decode_record, encode_record, iter_records

with open("customer.cob") as f:
    text = f.read()

items    = parse(text)                              # list[DataItem]（offset/bytes 算出済み）
items    = parse(text, copybook_dirs=["./cpy"])     # COPYBOOK 展開あり
data     = emit(items)                             # dict（JSON シリアライズ可能）
json_str = to_json(items)                          # str
doc      = to_markdown_table(items)                # データ項目定義書（Markdown表）

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
| DISPLAY + `SIGN IS ... SEPARATE` | 桁数 + 1（符号が独立した文字バイトになるため） |
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
| レベル 66（`RENAMES`） | エイリアスとして `"renames"` キー付きで出力（後述） |
| レベル 77（独立項目） | トップレベルのエントリとして出力 |
| `SIGN IS LEADING/TRAILING [SEPARATE]` | 符号位置・独立バイトの有無を解析し、バイト長・デコードに反映 |

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

### レベル 66（RENAMES）

`66 <name> RENAMES <target> [THRU <target2>].` は、既存フィールド（の範囲）を
別名で参照するエイリアスです。単一ターゲットの場合は対象と同じ `"offset"`/
`"bytes"`/型を継承し、`THRU` で範囲指定した場合は対象範囲を合算した
`"bytes"` のみ持ちます（複数の異種フィールドにまたがるため単一の型は
表現できません）。

```cobol
05 FIELD-A PIC X(5).
05 FIELD-B PIC 9(3).
66 ALIAS-A   RENAMES FIELD-A.
66 COMBINED  RENAMES FIELD-A THRU FIELD-B.
```

```json
{
  "FIELD-A": { "type": "string", "length": 5, "offset": 0, "bytes": 5 },
  "FIELD-B": { "type": "numeric", "length": 3, "offset": 5, "bytes": 3 },
  "ALIAS-A": { "type": "string", "length": 5, "offset": 0, "bytes": 5, "renames": "FIELD-A" },
  "COMBINED": { "offset": 0, "bytes": 8, "renames": ["FIELD-A", "FIELD-B"] }
}
```

デコード（`decode_record()`）は単一ターゲットの RENAMES のみ値を返します
（`THRU` で範囲指定したものは異種ストレージの合成のため、デコード結果には
含まれません — レイアウト情報としては引き続き JSON/データ項目定義書に出力されます）。

### COPYBOOK 展開

```bash
# ディレクトリ内の .cpy / .cob / .CBL ファイルを検索して自動展開
cobol-data-parser --copybook-dir ./copybooks main.cob
```

`REPLACING` 句（擬似テキスト `==...== BY ==...==` および単語置換）に対応しています。  
ネストした COPY（コピーブック内の COPY）も再帰的に展開します。

## データ項目定義書

`--format markdown`（または `to_markdown_table()`）で、コピー本の物理レイアウトを
Markdown 表として出力できます。JSON 出力（`emit()`）は API 消費者向けに FILLER や
88レベルを除外しますが、こちらはレイアウト定義書として **すべてのバイトを説明する**
ため、FILLER・レベル66（RENAMES）・レベル88（条件名）も含めて全項目を出力します。

```bash
cobol-data-parser --format markdown customer.cob
```

```markdown
| Level | 項目名 | PIC | USAGE | 桁数 | バイト数 | オフセット | REDEFINES | OCCURS |
|---|---|---|---|---|---|---|---|---|
| 01 | CUSTOMER-REC |  |  |  | 34 | 0 |  |  |
| 　　05 | CUST-ID | 9(5) |  | 5 | 5 | 0 |  |  |
| 　　05 | CUST-NAME |  |  |  | 20 | 5 |  |  |
| 　　　　10 | FIRST-NAME | X(10) |  |  | 10 | 5 |  |  |
| 　　　　10 | LAST-NAME | X(10) |  |  | 10 | 15 |  |  |
| 　　05 | BALANCE | S9(7)V99 |  | 7,2 | 9 | 25 |  |  |
```

階層はレベル列のインデント（全角スペース）で表現されます。オフセット/バイト数が
静的に確定できないフィールド（OCCURS DEPENDING ON より後ろ、前述）は空欄になります。

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
| DISPLAY 数値（ゾーン10進数） | 下位ニブル = 桁。符号付きは符号位置バイト（既定は末尾、`SIGN IS LEADING` で先頭）のゾーンニブル（`0xC`/`0xF`=正、`0xD`/`0xB`=負）で符号判定 |
| DISPLAY 数値 + `SIGN IS ... SEPARATE` | 符号は独立した `'+'`/`'-'` 文字バイト（先頭/末尾）。残りは通常のゾーン10進数として解釈 |
| `COMP-3` / `PACKED-DECIMAL`（パック10進数） | BCD ニブル展開。小数点は `Decimal` で正確に配置（浮動小数点誤差なし） |
| `COMP` / `COMP-4` / `COMP-5` / `BINARY` | 2/4/8 バイトの符号付き・符号なし整数。`byte_order="big"`（既定）/ `"little"` |
| `COMP-1` / `COMP-2` | IEEE754 単精度（4バイト）/倍精度（8バイト）浮動小数点。`byte_order` 対応 |

`INDEX` / `POINTER` は未対応で、`NotImplementedError` を送出します。

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

## エンコード（値 → バイト列）

`encode_record()` は `decode_record()` の逆方向です。`decode_record()` と同じ形の
`dict` を受け取り、実際のレコードバイト列に書き戻します。

```python
from decimal import Decimal
from cobol_data_parser import parse, encode_record, decode_record

items = parse(cobol_source)
record = items[0]

values = {"CUST-ID": 12345, "CUST-NAME": "ALICE", "BALANCE": Decimal("-123.45")}
raw = encode_record(record, values)                 # bytes
decode_record(record, raw) == values                # 対称（round-trip）
```

対応する型はデコードと同じです（DISPLAY テキスト・ゾーン10進数・`SIGN IS ...
SEPARATE`・`COMP-3`/`PACKED-DECIMAL`・`COMP`系バイナリ・`COMP-1`/`COMP-2`）。
`INDEX`/`POINTER` は未対応で `NotImplementedError` を送出します。

- **REDEFINES**: 同じスロットに base フィールドとエイリアスの両方の値を渡すことはできません
  （物理的に同じバイト列を書くため）。`values` に base フィールド名があればそちらを優先し、
  なければ見つかったエイリアスの値を書き込みます。
- **OCCURS DEPENDING ON**: 件数はリストの長さから自動算出せず、`depending_on` が指す
  フィールド自身の値（`values` に含まれる件数）をそのまま使います。呼び出し側でリストの
  長さと件数の整合性を保つ必要があります。
- **レベル 66（RENAMES）**: `values` に渡しても無視されます。同じストレージを指す
  実体フィールド側に値を渡してください。

## SQL DDL / TypeScript / OpenAPI 生成

`--format sql-ddl` / `--format typescript` / `--format openapi`（または `to_sql_ddl()` /
`to_typescript()` / `to_openapi_schema()`）は、`emit()` が作る JSON メタデータ形状では
なく、`decode_record()` が実際に返す**デコード後の値の形**を反映したスキーマを生成します。
この2つが異なるのは REDEFINES の扱いです: `emit()` はエイリアスを `"union"` 配列に
畳み込みますが、`decode_record()` は base フィールドとすべてのエイリアスを**独立に
デコードして兄弟キーとして返します**。ツール全体の一貫性のため、これらの生成物も
REDEFINES を兄弟として扱います。

```python
from cobol_data_parser import parse, to_sql_ddl, to_typescript, to_openapi_schema

items = parse(cobol_source)
print(to_sql_ddl(items))          # CREATE TABLE 文（レコードごとに1つ）
print(to_typescript(items))       # export interface 宣言（レコードごとに1つ）
print(to_openapi_schema(items))   # {"components": {"schemas": {...}}}
```

### 型マッピング

| PIC カテゴリ | デコード時のPython型 | SQL型 | TypeScript型 | OpenAPI型 |
|---|---|---|---|---|
| STRING/ALPHABETIC/編集型 | `str` | `VARCHAR(n)` | `string` | `string` |
| NUMERIC/SIGNED_NUMERIC | `int` | `INTEGER`/`BIGINT`/`NUMERIC(n)` | `number` | `integer` |
| DECIMAL/SIGNED_DECIMAL/PACKED_DECIMAL（V句あり＝小数部あり） | `Decimal` | `NUMERIC(p,s)` | `string`（浮動小数点誤差を避けるため文字列表現） | `string`（同左） |
| PACKED_DECIMAL（V句なし＝小数部なし） | `int` | `INTEGER`/`BIGINT` | `number` | `integer` |
| `COMP`/`COMP-4`/`COMP-5`/`BINARY` | `int` | `SMALLINT`/`INTEGER`/`BIGINT`（バイト長で判定） | `number` | `integer` |
| `COMP-1`/`COMP-2` | `float` | `FLOAT`/`DOUBLE PRECISION` | `number` | `number` |

`PIC 9(5) COMP-3` のように V 句のない PACKED-DECIMAL は `decode_record()` が `int` を
返す（`Decimal` にはならない）ため、整数として生成されます。

### 構造の扱い

- **グループ項目**（OCCURSなし）: SQL は親からのパスを `_` でフラット化した列名
  （`CUST-NAME.FIRST-NAME` → `CUST_NAME_FIRST_NAME`）。TypeScript/OpenAPI はネストした
  オブジェクトとして表現します。
- **OCCURS**（固定・`DEPENDING ON` 問わず）: SQL は `<テーブル>__<フィールド>` という
  子テーブルを生成し、`ID`（合成主キー）・`_PARENT_ID`（親テーブルへのFKのプレース
  ホルダ、実際の制約は未配線）・`_OCCURS_INDEX` 列を付与します。OCCURS の中に
  さらに OCCURS がネストする場合も、各階層が自分自身の `ID`/`_PARENT_ID` を持つため
  そのまま連鎖します。TypeScript/OpenAPI はネイティブな配列（`Array<T>` /
  `{"type":"array","items":{...}}`）として表現し、OpenAPI には `OccursClause` から
  `minItems`/`maxItems` を付与します。
- **REDEFINES**: 前述の通り base フィールドとエイリアスは兄弟として出力されます。SQL
  では同じ物理バイト範囲を指す2つの nullable な列になるため、生成された DDL には
  その旨のコメントが付きます（どちらが有効かはアプリ側の判別値で判断してください）。
- **RENAMES（レベル66）**: 単一ターゲットのもの（`THRU` なし）のみ、対象の複製として
  出力されます（`decode_record()` と同じ）。`THRU` 範囲指定のものは対象外です。
- **フィールド名**: SQL のテーブル・列名は `-` を `_` に置換した上で大文字化します
  （有効な SQL 識別子にするため）。TypeScript の `interface` 名・OpenAPI のスキーマ名
  のみ COBOL 名から PascalCase 化しますが（有効な識別子にするため）、フィールド自体の
  キーは元の COBOL 名をそのまま使います（TypeScript ではクォート付き文字列キー）—
  `emit()` の JSON 出力キーと一貫性を保つためです。
- `FILLER` とレベル88（条件名）は除外されます（`emit()` と同じ）。

## PROCEDURE DIVISION 解析（`cobol-proc-parser`）

`cobol-proc-parser` は PROCEDURE DIVISION の SECTION・段落を読み取り、`PERFORM` の
**制御フローグラフ**と `CALL` の**依存関係グラフ**、そして構造的な**プログラム仕様書**を
出力します。

対応しているのは以下の構文です（COBOL の完全な文法ではなく、実務でよく使われる形に絞っています）:

| 文 | 対応範囲 |
|---|---|
| `PERFORM <para>` | 単純な呼び出し |
| `PERFORM <para> THRU <para2>` | 範囲呼び出し。ソース中の物理的な段落の並びに従って A〜B の全段落へのエッジに展開（COBOL の実行意味論どおり） |
| `PERFORM <para> VARYING <id> ... UNTIL ...` | `VARYING` の識別子は取得。`UNTIL` はループの有無のみ記録し、条件式そのものは解析しません（COBOL式文法のフルパースはスコープ外） |
| `CALL '<lit>'` / `CALL <id>` | 静的リテラル呼び出し / 動的呼び出し（`DYNAMIC:<識別子>` として依存関係グラフに表現） |
| `CALL ... USING [BY REFERENCE/CONTENT/VALUE] ...` | 引数の識別子一覧を取得（`BY` 修飾子は読み飛ばし） |
| `CALL ... RETURNING <id>` | 戻り値の格納先識別子を取得 |
| `GO TO <para>` | 単一ターゲットのみ対応。`GO TO a b c DEPENDING ON x` の複数ターゲット形式は未対応 |
| `IF <cond> [ELSE] END-IF` / `EVALUATE ... WHEN [OTHER] ... END-EVALUATE` | 明示的なスコープターミネータ（`END-IF`/`END-EVALUATE`）付きの形式のみ対応。内側の `PERFORM`/`CALL`/`GO TO` に、どの `IF`/`ELSE`/`WHEN` 分岐に属するかを示す `branch_path` を付与（条件式・WHEN値はテキストとしてそのまま記録するだけで、式文法としては解析しません） |

**スコープ外**: ピリオド終端の旧来形式（`END-IF`/`END-EVALUATE` を省略する暗黙スコープ）
は分岐境界として認識されません — 閉じないブロックはそのまま最後まで入れ子として扱われます
（例外は出さずベストエフォートで処理を続けます）。`WHEN 1 2 3` や `WHEN 1 THRU 5` のような
複合WHEN値は、個別の値に分解せずテキストのままラベル化されます。

### CLI

```bash
# 制御フロー・依存関係を含むJSON全体を出力
cobol-proc-parser main.cob

# PERFORM の制御フローグラフを Graphviz DOT で出力
cobol-proc-parser --format dot --graph flow main.cob | dot -Tpng -o flow.png

# CALL の依存関係グラフを SQL INSERT 文で出力
cobol-proc-parser --format sql --graph call main.cob

# Python の pprint 形式で出力
cobol-proc-parser --format python main.cob

# プログラム仕様書（Markdown）として出力
cobol-proc-parser --format spec main.cob
```

### Python API

```python
from cobol_data_parser.proc import parse, build_flow_graph, build_flow_graph_detailed, build_call_graph, to_json, to_markdown_spec

proc = parse(cobol_source)          # ProcedureDivision（program_id/sections/paragraphs）
flow_edges = build_flow_graph(proc)  # [(呼び出し元段落, PERFORM/GO TO先段落), ...]（分岐情報なし）
detailed = build_flow_graph_detailed(proc)  # [FlowEdge(source, target, kind, branch_path), ...]
call_edges = build_call_graph(proc)  # [(program_id, CALL先), ...]  動的CALLは "DYNAMIC:<識別子>"
json_str = to_json(proc)
spec_md = to_markdown_spec(proc)     # 段落一覧・制御フロー・外部依存をまとめたMarkdown仕様書
```

`PerformStmt`/`CallStmt`/`GoToStmt` はそれぞれ `branch_path: list[BranchCond]` を持ち、
`IF`/`ELSE`/`EVALUATE`/`WHEN`/`WHEN OTHER` のどの分岐に属するか（外側から順に）を記録します
（無条件の文は空リスト）。`to_json()`/`to_python()` はこれを `"branch_path"` として出力し
（無条件の場合はキー自体を省略）、`to_markdown_spec()` は `CASE-ONE [WHEN: WS-CODE = 1]`
のようにセルへ注記し、`to_dot(graph="flow")` は条件付きエッジに DOT の `label` を付与します。

### プログラム仕様書生成

`to_markdown_spec()`（CLI: `--format spec`）は、段落一覧（PERFORM/CALL/GO TO付き）・
制御フローグラフ・CALL依存関係グラフをまとめた構造的なMarkdown文書を生成します。
どのデータ項目を読み書きしているかまでは追跡していないため、自然文によるIPO
（Input-Process-Output）の説明文書ではなく、**構造の一覧**である点に注意してください。

## 開発

```bash
pip install -e ".[dev]"
pytest
```

## FUTURE WORK

- **暗黙スコープのIF/EVALUATE対応** — 分岐条件付きCFGは `END-IF`/`END-EVALUATE`
  付きの明示的スコープ形式のみ対応。ピリオド終端の旧来形式は非対応（閉じないブロックとして
  ベストエフォートで処理されるだけ）。
- **`PERFORM ... UNTIL` の条件式パース** — 現在はUNTIL句の有無のみ記録し、条件式本体は未解析。
- **`GO TO a b c DEPENDING ON x`（複数ターゲット）対応** — 現在は単一ターゲットのGO TOのみ対応。
- **自然文IPO仕様書生成** — `to_markdown_spec()` は構造（段落・制御フロー・CALL依存）の一覧に
  留まる。データ項目の読み書き追跡を伴う自然文の処理概要・IPO文書化は別途大きな機能。
- **フルプログラム入力対応** — COBOL ソースファイル全体から DATA DIVISION を自動的に抽出（FILE SECTION の FD 記述子を含む）。
- **IBM 16進浮動小数点** — `COMP-1`/`COMP-2` は現在 IEEE754 のみ対応。IBM 独自の16進浮動小数点形式は未対応。
- **SQL DDL の子テーブルFK配線** — OCCURS由来の子テーブルの `_PARENT_ID` は現状プレース
  ホルダで、実際の外部キー制約や実行時の値の紐付けは呼び出し側の責務。
- **INDEX/POINTER の SQL/TS/OpenAPI 対応** — `decode_record()` 同様、現状は非対応。

## ライセンス

MIT
