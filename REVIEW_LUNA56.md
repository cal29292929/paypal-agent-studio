<!-- Reviewed by OpenAI Codex (gpt-6-luna) | Session ID: 01a17dc3-8fba-7481-92f8-1c1224c588b4 | Timestamp: 2026-10-27T23:29:51+09:00 -->

# Architecture & Security Review — PayPal Agentic Commerce Studio

**対象:** `DESIGN_OPUS55.md` v1.0  
**レビュー日:** 2026-10-27  
**判定:** **現状のままでは実装開始不可。** 主張する「調達から決済・履行までの自律購買」と、PayPal APIが実際に実行する取引の間に重大な不一致がある。特に、PayPal Orders と Invoicing を外部販売者への購買手段として扱っている点は、製品の中核を成立させない。まず取引モデルとデモの主張を修正し、その後に API 契約、承認、永続化、セキュリティ境界を固める必要がある。

## 1. アーキテクチャ妥当性

### P0 — PayPal決済が、検索した販売者への購買になっていない

設計では Channel3 で見つけた商品を選び、その価格を `POST /v2/checkout/orders` に渡して PayPal Order を作成する。しかし、この API は自分の PayPal merchant アカウントが受け取る checkout payment を作成する。Channel3 の販売者への注文・決済・在庫引当・配送依頼は発生しない。商品名、SKU、URLを PayPal Order に記録しても、販売者への購入にはならない。

したがって、現在のフローは「商品検索後、Studioに対するPayPal決済を作る」構成であり、「外部販売者から商品を購入する」構成ではない。`CAPTURED → FULFILLING → CLOSED` と配送追跡を表示する根拠もない。

**必須の設計判断:** 実際に接続する販売者の checkout / purchase API と決済フローを追加するか、スコープを「購買候補の調査・承認・PayPal請求／決済デモ」に限定すること。実在しない販売者注文や配送イベントを、実取引のように表示してはならない。

### P0 — Invoicing v2 は仕入先への支払手段ではない

`create_and_send_invoice()` は請求書を作成して受取人に送る操作であり、仕入先への送金や net-terms の購買ではない。提示されたコードでは、Sandbox buyer に請求するため、購買者に請求書を送る流れになっている。これを「supplier billing」「Settlement」「仕入先への支払」と表現するのは不正確である。

**必須:** Invoice をデモに残す場合は、請求書の発行者・受取人・金銭の流れを明記し、`INVOICED` を `PAID` や「購買完了」と区別すること。仕入先への支払を主張する場合は、実際にそれを実行する API と認可モデルを設計すること。

### P1 — 永続化モデルが Render 運用要件と整合しない

`RunStore` はプロセス内メモリのみとされる一方、ホストされた Render デモ、Webhook、SSE、複数プロセスを想定している。再起動・再デプロイで run、承認状態、Webhook重複排除、audit chain が失われる。複数インスタンスでは、Webhookを受けたプロセスと run を持つプロセスが異なる可能性がある。

**必須:** 永続ストアを選び、run state・PayPal ID・idempotency key・webhook event ID・audit entries をトランザクション可能な形で保存すること。メモリ保存を採用するなら、ホストデモでの再起動・単一インスタンス制約とデータ消失を明示し、永続性を示唆する表現を外すこと。

### P1 — モジュール境界と実行モデルが未定義

`POST /api/runs` が同期で `RunResult` を返す一方、SSE stage events、10分ポーリング、複数外部API呼び出しも定義されている。同期リクエストではタイムアウト・二重送信・クライアント切断後の処理が不明である。実行中 run のキャンセル、再開、並行実行、ステージごとの再試行も仕様化されていない。

**必須:** run 作成を `202 Accepted` と run ID 返却にし、ワーカー／ジョブモデルまたは明示的な短時間同期モデルを定義する。SSE再接続時の cursor / `Last-Event-ID`、イベント順序、重複配信、終了条件を定義する。

## 2. ハッカソン要件・賞トラック

評価軸のマッピングは方向性として有用だが、受賞可能性を裏付ける証拠と提出物が不足している。

- 「公式賞金」「締切」「スポンサー賞の有無」は変わり得る情報であり、この設計書だけでは検証できない。確定情報として扱わず、公式 Devpost の現行ページに照合すること。
- 「Best Use of APIMatic」でContext Pluginを開発中に使うことと、提出作品におけるAPIMatic活用の評価は別である。SDKを任意利用するだけで要件を満たすとは限らない。実装での使用箇所、再現可能な証拠、提出時の説明を用意すること。
- 「KERNEL」「Channel3」等の API path / schema は未検証と明記されている。ライブ連携を審査上の動作実績として主張する前に、スポンサーの現行仕様で疎通を確認すること。
- Devpost の提出物が「動画とURL」程度にしか記述されていない。提出フォームの必須項目、公開リポジトリ、説明文、スクリーンショット、デモ動画、使用技術・スポンサー利用説明、動作URL、Sandbox実演手順を具体的な checklist にすること。
- 2:45動画の台本、録画対象、実演用Sandboxアカウント、失敗時の切替、字幕・音声、公開リンクが未定義。期限直前のPayPal Sandbox障害や資格情報失効時に提出可能な代替デモを用意すること。
- Bryntum、AG Grid、Elastic、Zapier、Postman の統合範囲がUI要件の列挙に留まる。各製品の実使用、ライセンス、SDK/API条件、提出で必要な証明を確認すること。ドラッグによる日程変更後の「policy re-check」仕様もない。
- Astropodsを「未統合」とする判断は、賞要件を公式ページで確認した後に確定すること。未確認のスポンサー統合を、賞の有無だけで優先度判断しない。

## 3. API契約・データモデル

### PayPal Orders v2

- 注文作成例のレスポンスは `status: PAYER_ACTION_REQUIRED` と `links[].rel: payer-action` を示す一方、シーケンスでは `CREATED` を示している。期待値を実際の API 応答に合わせ、status/link relation を複数の有効状態で処理すること。
- 注文作成例は物理商品なのに `shipping_preference: NO_SHIPPING` を指定している。配送先・送料・税・配送要件があるシナリオと矛盾する。配送を実装しないなら物理商品の配送を主張しないこと。
- 注文合計が商品小計と同額で、税・送料・割引・価格変動の扱いがない。購買予算は商品小計だけで判定せず、通貨・税・送料・手数料・PayPal側の最終金額との差を検証すること。
- 注文を作成した時点で「承認待ち」とする要件、buyer action の実際の URL、戻り先での注文 ID照合が曖昧。ブラウザの `return_url` だけで承認済みと判断してはならない。PayPal APIで注文状態を再取得して確認すること。
- `create_order()` は任意の `Offer` と `qty` を受け取るが、選択された `ScoredOffer` の検証状態、決定時価格、通貨、上限額との整合を検証する仕様がない。支払い直前に価格・在庫を再確認し、差異があれば承認を無効化して再評価すること。
- `INSTRUMENT_DECLINED` の「retry-with-new-approval」は、旧注文をどう扱うか、二重注文を防ぐか、再承認をどう結び付けるかが不明。状態遷移と監査イベントを定義すること。
- `PayPal-Request-Id` の有効期間と再試行時の同一 payload 要件が未記載。run ID由来のキーだけでなく、操作ごとの一意性・永続化・再起動後の再利用を定義すること。

### Invoicing v2

- `generate-next-invoice-number` と請求書作成の間で競合が起きる可能性がある。複数run同時実行時の重複・番号再取得・失敗後の扱いを定義すること。
- Invoice APIの create / send 応答を `href` だけで扱うのは不足。ID抽出、status、エラー応答、`202` の非同期完了、再送時の重複防止を仕様化すること。
- Sandbox recipient allow-list は請求先メールだけに適用され、誤送信を完全には防げない。送信先・発行者・通貨・金額・請求内容を送信直前に再検証し、許可された固定Sandboxアカウント以外へ送らないこと。
- `INVOICING.INVOICE.PAID` を受信しただけでrunを `PAID` にするのは危険。対象invoice ID、merchant account、金額、通貨、event重複、現在状態を照合する必要がある。

### LLM、検索、検証

- JSON object mode はJSON Schema準拠や意味的正当性を保証しない。未知キー拒否はよいが、型・サイズ・Unicode・日付・制御文字・過剰ネストの上限をすべての入力境界で定義すること。
- `deadline >= today` は日付境界で結果が変わる。時計を注入するだけでなく、タイムゾーンを固定し、テスト用clockを全ロジックで共有すること。
- `Offer` のURL検証が `https` のみでは不十分。userinfo、IP literal、localhost、private/link-local IP、DNS rebinding、リダイレクト先を制限しないと、KERNEL browser経由のSSRFにつながる。
- KERNELの価格抽出でJSON-LD → OpenGraph → regexを使うが、通貨・数量単位・バリエーション・価格帯・会員価格・税込/税別・非表示DOM・在庫文言の誤判定が未定義。抽出値の出典、信頼度、通貨一致条件、失敗状態を明確にし、低信頼度の検証結果は購入候補から除外すること。
- `confidence` をスコアに使うが、校正方法・閾値・証拠の保存方針がない。スクリーンショットやページ内容に個人情報・認証情報が含まれ得るため、保存・削除・アクセス制御を定義すること。
- 商人名・商品説明・Webページ本文はprompt injectionの入力面である。Web由来の指示を命令として実行しない分離、LLMへの最小データ渡し、ツール権限制御、出力検証を明記すること。
- Channel3の実際の検索 schema、pagination、rate limits、商品価格の意味、affiliate / attribution 条件が設計にない。内部正規化 fixture だけでなく、実レスポンス契約と異常レスポンスを検証すること。
- 価格通貨がRequisitionと異なるOfferをどう扱うか不明。為替換算レート・取得時刻・丸め規則がないなら通貨不一致候補を拒否すること。

## 4. エラー処理・再試行・フォールバック

- `_http()` は3回の指数バックオフを規定するが、上限を含めると最悪待ち時間・全体deadline・同時実行数が不明。run全体の時間予算と各依存先の個別timeoutを定義すること。
- `Retry-After` が30秒を超えた場合の挙動、`429` の provider quota、`Retry-After` の日付形式、`urllib` のHTTPError応答body処理がない。再試行しない場合は明示的な `RATE_LIMITED` などのエラーを返すこと。
- すべてのPOSTを「idempotency keyがあれば再試行可能」とするのは危険。PayPalの対象APIでキーがサポートされること、同一キー・同一payloadの再送条件、応答喪失後の照合手順をAPI単位で指定すること。
- TLS/接続例外とAPIの業務エラー、JSON parse error、schema mismatch、部分成功を異なる型に分類していない。UI、MCP、監査ログに内部例外・token・HTTP bodyを漏らさず、回復可能性を含む安定した error code を返すこと。
- Nebiusの「schema違反時1回再試行」は、timeout、429、認証失敗、空応答、内容ポリシー拒否まで同じ再試行に見える。エラー分類ごとに再試行可否を定義し、料金・遅延・上限を制御すること。
- KERNEL Playwright未導入時の自動sim fallbackは、入力ごとに一部live・一部simとなり得る。検証結果が実測と誤認されないよう、run全体にprovider modeを記録し、購入判断に必要なproviderがsimならlive purchaseを停止するポリシーを設けること。
- EventSinkの「must never raise」は実装契約だけでは保証されない。sink例外を業務処理から隔離し、失敗率・再送・永続キュー・監査上の扱いを定義すること。
- Elastic / Zapier は外部送信先である。機密情報、メール、商品ページ全体、PayPal応答を送らず、イベントごとの許可フィールドを明示すること。

## 5. セキュリティ・プライバシー

### P0 — `/api` と `/mcp` の認証・認可が定義されていない

HMACを任意設定できる記述はあるが、REST API、承認、capture、run閲覧、audit閲覧、SSE、Webhook以外のルートに認証・認可がない。公開Render URLであれば、第三者が注文作成・capture・run列挙・個人情報閲覧を実行できる可能性がある。

**必須:** 各ルートの認証方式、ユーザー／tenant境界、承認権限、rate limit、CORS、CSRF防御、秘密情報管理を定義すること。MCPのtoolごとに権限を分け、`create_purchase` と `capture` を無条件に外部エージェントへ公開しないこと。

### HMACの再送・鍵管理

HMAC署名にtimestampを含めるだけでは、timestamp許容幅、nonce / replay cache、HTTP method・path・bodyの正規化、鍵ローテーション、定数時間比較、署名対象の文字コードが必要である。PayPal webhook verification と `/mcp` のHMACは別の認証境界として実装すること。Webhook event IDによる重複排除も必要。

### PayPal承認とcallback

- `/approve/return?run=&token=` は推測可能なrun IDや改ざんされたtokenを受け付け得る。ランダムな一回限りstate、ユーザーセッションへの結合、CSRF防御、有効期限を設けること。
- 戻りURLの任意host、open redirect、外部参照、ログへのquery token露出を防ぐこと。
- PayPalの承認画面で人がクリックすることは有効な購入者アクションだが、アプリ側の「誰が何をいくらで承認したか」の監査要件を満たさない。承認者・承認対象・金額・価格確認時刻・policy versionを保存し、変更時は承認を失効させること。

### SSRF・ブラウザ隔離

KERNEL browserは外部URLへ接続するため、URL allow-list、DNS/IP検証、redirect再検証、localhost/private network拒否、ダウンロード無効化、認証情報・Cookie隔離、最大ページサイズ、ナビゲーション時間上限が必要である。商品ページ起因の悪意ある内容をLLMへ渡す場合も信頼境界を保つこと。

### 秘密情報・ログ

OAuth tokenをメモリ保持する設計は妥当だが、例外本文、HTTP debug log、traceback、`paypal-debug-id` に付随する応答、SSE、audit payload、Postman environmentに秘密が漏れない保証がない。秘密のredaction、ログ保持期間、Sandbox credentialと本番 credentialの分離を定義すること。`PAYPAL_BASE_URL` がSandbox以外を拒否する検査は、scheme/host/port/pathを正規化して検証し、redirect先も検査すること。

### 監査ログの限界

Hash chainは改ざん検知を補助するが、同一プロセスで全ログを再生成できる攻撃者に対する真正性や外部保全を保証しない。`payload_digest` の対象、canonical JSON規則、時刻源、chainの永続化、key / genesis管理、検証API、改ざん検知後の対応を定義すること。個人情報・支払情報はhash chainに直接保存しないこと。

## 6. テスト可能性・決定性

「60+ tests」「byte-identical artifacts」「socket is never opened」は目標の記載で、受入条件として具体化されていない。テスト追加を実装完了条件にすること。

**必要な決定的テスト:**

- `Decimal` の丸め、JPY等の小数桁、数量乗算、税・送料、負値、巨大値、通貨不一致、float拒否。
- 全状態遷移、二重approve/capture、未承認capture、Webhook重複・順序逆転、期限切れ、部分失敗、再起動後の復元。
- PayPalの `PAYER_ACTION_REQUIRED`、`CREATED`、`COMPLETED`、`ORDER_NOT_APPROVED`、`INSTRUMENT_DECLINED`、429、各5xx、timeout後の応答喪失、invalid JSON、API error body。
- Invoicingの番号競合、create成功後の応答喪失、send重複、非同期status、未許可recipient拒否。
- Channel3とKERNELの実レスポンス fixture、価格なし・通貨違い・在庫不明・redirect・不正URL・SSRＦ拒否。
- LLMのmalformed JSON、schema違反、prompt injection文、過大出力、429、タイムアウト、フォールバック。LLM出力が価格・権限・recipientを上書きできないこと。
- `Retry-After`、指数バックオフ、jitterを注入可能なclock/randomでテストし、CIではsleep・外部ネットワークなしで実行すること。
- 同じ入力・seedでrun ID、audit、metrics、ledger、timelineが同一になること。現在の設計では現在時刻・外部API順序・latency分布・provider modeが決定性を崩し得るため、固定clockとfixtureを含めること。
- HTTP境界のサイズ制限、JSON深度、認証失敗、HMAC replay、CSRF、CORS、rate limit、秘密情報redaction、tenant越境拒否。
- Render上の再起動・複数ワーカー・Webhook再送に対する永続性と整合性。

## 7. Mandatory Fixes for Implementation (Sakura `preview/Kimi-K2.7-Code`)

以下は実装開始前に仕様へ反映し、コードと受入テストで強制すること。

- [ ] **取引モデルを修正する。** PayPal Ordersが検索先merchantへの発注ではない点、Invoiceが仕入先支払ではない点を反映し、実際のmerchant purchase integrationを追加するか、製品説明・状態・デモを実行可能なスコープへ縮小する。
- [ ] **Settlement状態を正確に分ける。** `ORDER_CREATED`、`AWAITING_BUYER_APPROVAL`、`CAPTURED`、`INVOICE_SENT`、`INVOICE_PAID`、`FULFILLMENT_CONFIRMED` を区別し、実イベントなしに配送・完了を表示しない。
- [ ] **承認ポリシーを明文化する。** `STUDIO_AUTO_APPROVE_LIMIT` の名前と動作を整合させる。PayPal buyer approvalはアプリの承認者認可と区別し、価格・数量・recipient・通貨が変わったら承認を失効させる。
- [ ] **PayPal契約を実レスポンス基準に直す。** Ordersの状態・approval link・shipping設定・税送料・capture応答・各エラーを正式なAPI schemaに合わせ、契約fixtureを用意する。
- [ ] **Invoicingの金銭の流れを直す。** 発行者／受取人／請求目的を明示し、Sandbox allow-listを送信直前にも強制する。請求書送信を支払・購買完了と扱わない。
- [ ] **ライブ／シミュレーション境界を安全側にする。** 購買に必要なproviderがsimならliveの支払操作を禁止する。全API応答・UI・提出デモでmodeと実測／合成データを表示する。
- [ ] **API認証・認可を追加する。** REST、MCP、SSE、承認、capture、auditにアクセス制御を設け、公開デモ向けrate limitとCORS/CSRF対策を定義する。HMACにはtimestamp許容幅・replay防御・鍵ローテーションを含める。
- [ ] **Webhookを堅牢化する。** PayPal署名検証後にevent IDを永続的に重複排除し、run・order/invoice ID・merchant・amount・currency・状態を照合する。順序逆転と再送をテストする。
- [ ] **SSRFとprompt injectionを防ぐ。** 商品URLのIP/redirect検査、KERNEL browser隔離、ページ由来指示の非信頼化、LLMの権限分離、送信データ最小化を実装する。
- [ ] **永続化と非同期処理を決める。** Render再起動後もrun・idempotency・Webhook・監査状態を復旧できる構成にする。SSE再接続、イベント重複、run timeout、キャンセル、worker失敗を仕様化する。
- [ ] **再試行をAPI単位で制御する。** 全体deadline、429/`Retry-After`、POSTごとのidempotency保証、timeout後の照合、最大遅延を定義し、非冪等操作の二重実行をテストする。
- [ ] **金額・候補検証を厳密化する。** `Decimal`・通貨桁・税送料・為替・在庫・価格変動の規則を定義し、決済直前に予算・通貨・商品・数量を再検証する。
- [ ] **監査・ログの保護を実装する。** canonical hash規則、永続化、検証、PII最小化、secret redaction、保持期間、外部sinkへの許可フィールドを決める。
- [ ] **決定的受入テストを用意する。** 固定clock/random、ネットワーク禁止、API fixture、再試行・失敗系・状態遷移・認可・金額・Webhookを含め、同一入力とseedで成果物が同一になることをCIで検証する。
- [ ] **提出物を完成条件に含める。** Devpost現行フォームの必須項目を確認し、README、公開可能なリポジトリ、スクリーンショット、短いデモ動画、動作URL、Sandbox手順、スポンサー利用の根拠、障害時の代替デモを期限前に揃える。
- [ ] **賞・スポンサー/API要件を再確認する。** 賞金、対象トラック、スポンサーAPI契約、クレジット、提出要件を公式情報で確認し、未検証の統合や受賞要件を確定情報として記述しない。

## 8. 最終評価

この設計には、決定的シミュレーション、policy engine、外部API境界の集約、監査記録という良い基盤案がある。しかし、現状のPayPal取引フローは「販売者の商品を購入・決済・履行する」という中心的主張を満たしていない。さらに、公開デモに必要な認証・永続化・Webhook重複排除も未完成である。

最優先は、**何を誰から購入し、PayPalのどの操作で誰に支払うのか**を一本の実行可能なフローとして定義し直すこと。その契約が確定するまで、9段階の「完了」表示、実購買・配送の主張、ライブ自律決済の実装へ進むべきではない。
