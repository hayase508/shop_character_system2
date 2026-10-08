# shop_character_system2
顔認証により、初来店者を区別して接客するシステム

Webカメラ → 顔特徴量 → SQLite照合 → 来店・特典判定 → WebSocket → 鬼動画・字幕・日本語音声、という一連の処理をローカルPCで実行します。
GitHubの調査時点（`441be2a`）ではこの概要READMEのみで、既存アプリはありませんでした。Python/FastAPI/OpenCV/face_recognition/SQLiteと、ビルド不要のHTML/CSS/JavaScriptで実装しています。

## Windowsでの初回起動（Python 3.10・64bit）

初回セットアップ後は、`start_shop.bat`をダブルクリックするとサーバーを起動して接客画面を開けます。PCを再起動した場合も、このファイルから起動してください。

Git、Python 3.10、EdgeまたはChrome、USBカメラを用意してください。以下は **コマンドプロンプト（cmd）** の手順です。OneDrive配下で書き込みエラーが出る場合は、同期対象外の作業フォルダーを使ってください。

1. リポジトリを取得し、フォルダーへ移動します。

   ```bat
   git clone git@github.com:hayase508/shop_character_system2.git
   cd shop_character_system2
   ```

   SSH鍵未設定の場合は `git clone https://github.com/hayase508/shop_character_system2.git` でも取得できます。実装を含むブランチ／配布物を使用してください。

2. Pythonを確認し、仮想環境を作成して有効にします。

   ```bat
   python --version
   python -m venv .venv
   .venv\Scripts\activate
   ```

   Pythonが複数ある場合は作成時に `py -3.10 -m venv .venv` を使います。
   PowerShellでは有効化が `.\.venv\Scripts\Activate.ps1` です。実行ポリシーで止まる場合、設定を変えず、cmdを使うか `.\.venv\Scripts\python.exe` を直接実行できます。

3. ライブラリをインストールします。

   ```bat
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

   **dlibのビルドで失敗する場合：** MicrosoftのVisual Studio Build Toolsで「C++によるデスクトップ開発」（MSVC、Windows SDK、CMakeツール）を導入し、ターミナルを開き直して再実行してください。CMakeが見つからなければ仮想環境で `python -m pip install cmake`、その後 `python -m pip install dlib --verbose` でエラー詳細を確認します。出所不明のwheelは不要です。
   face_recognitionはWindowsを公式サポート対象としていませんが、この実装ではWindows向けカメラ処理とPython 3.10での動作確認を行っています。環境ごとのビルド確認は必要です。根拠：[face_recognition公式](https://github.com/ageitgey/face_recognition#installation)、[dlibのビルド手順](https://dlib.net/compile.html)。

4. 設定をコピーします。

   ```bat
   copy .env.example .env
   notepad .env
   ```

   PowerShellなら `Copy-Item .env.example .env` です。通常は `CAMERA_ENABLED=true`、`DEBUG_MODE=false` のままで使います。環境変数を別途設定した場合は、環境変数が.envより優先されます。変更後はサーバーを再起動してください。

5. 動画を確認します。

   待機中は `static/videos/idle.mp4`、接客中は `static/videos/yobidashi_mobile.mp4` を使います。ファイルがない場合でもサーバーは起動し、画面には「鬼」の代替表示と字幕が出ます。

6. DBを初期化してサーバーを起動します。

   ```bat
   python -m app.manage init-db
   python -m app
   ```

   DBは初回起動時にも自動作成されます。別の起動方法は `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1` です。
   カメラと接客状態を1プロセスで管理するため、**複数workersや、営業中の--reloadは使わないでください**。

7. [接客画面](http://127.0.0.1:8000/) をEdgeまたはChromeで開き、**「接客を開始（音声を有効にする）」** を押します。「全画面」またはF11でディスプレイ表示にします。音量と日本語音声を確認してください。サーバー停止はターミナルでCtrl+Cです。

   開始ボタンを押す前は顧客を登録しません。最初に開始した1画面だけが接客を担当し、他の画面から接客を終了できません。画面を閉じたら接客を中断してIDLEへ戻ります。再接続した同じ画面は自動復帰し、ページ再読み込み後は開始ボタンを押し直します。

## カメラなしの動作確認

.envで次の2項目を変更し、起動します。

```dotenv
CAMERA_ENABLED=false
DEBUG_MODE=true
```

接客画面で開始ボタンを押したあと、別タブで [開発テスト画面](http://127.0.0.1:8000/debug) を開いて、初来店・再来店・60日ちょうど・61日経過を試してください。字幕が変わり、音声と動画の終了後に待機へ戻ります。接客中の追加イベントはHTTP 409です。「接客を中断」でも待機へ戻せます。

顔認証ライブラリのインストール前に画面だけ試す場合は、仮想環境へ `pip install fastapi "uvicorn[standard]" python-dotenv` を入れて上記のカメラ無効設定で起動できます。実カメラ運用前にはrequirements.txtの全ライブラリが必要です。

PowerShellから送る場合：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/debug/new-customer
Invoke-RestMethod -Method Post 'http://127.0.0.1:8000/api/debug/returning-customer?days_since_last_visit=10'
Invoke-RestMethod -Method Post 'http://127.0.0.1:8000/api/debug/returning-customer?days_since_last_visit=60'
Invoke-RestMethod -Method Post 'http://127.0.0.1:8000/api/debug/returning-customer?days_since_last_visit=61'
```

各リクエストは前の接客終了後に実行してください。デバッグイベントは顧客DBを変更せず、手動で繰り返し試せるよう人物・全体クールダウンだけを省略します。GREETINGの排他制御は本番と共通です。本番では `DEBUG_MODE=false` に戻すと、デバッグAPI・画面・APIドキュメントが404になります。

## 設定

| 設定 | 初期値 | 意味 |
|---|---:|---|
| CAMERA_ENABLED | true | falseならカメラや顔認証ライブラリなしでも表示テスト可能 |
| CAMERA_INDEX | 0 | カメラ番号。映らなければ1、2を試す |
| CAMERA_BACKEND | auto | WindowsでDirectShow、失敗時に既定方式。dshow/msmfも指定可能 |
| CAMERA_WIDTH / CAMERA_HEIGHT | 1280 / 720 | 要求するカメラ解像度（機器により異なる） |
| CAMERA_RETRY_SECONDS | 5 | カメラ接続失敗後の再試行間隔 |
| FACE_MATCH_THRESHOLD | 0.5 | 特徴量の距離上限。小さくするほど厳格 |
| FACE_FRAME_SKIP | 5 | 5フレームに1回だけ顔を処理 |
| FACE_IMAGE_SCALE | 0.25 | 顔処理用画像の縦横倍率 |
| FACE_DETECTION_MODEL | hog | CPU向け。cnnも選べるが負荷が増える |
| FACE_CONFIRMATION_COUNT | 2 | 同じ顔と確認する観測回数 |
| FACE_CONFIRMATION_WINDOW_SECONDS | 4 | 複数回の観測をまとめる時間 |
| CAMERA_EVENT_COOLDOWN_SECONDS | 2 | 確認済み顔をバックエンドに渡す最短間隔 |
| PERSON_COOLDOWN_SECONDS | 20 | 同じ人物への接客間隔（前の接客終了から） |
| GLOBAL_COOLDOWN_SECONDS | 5 | 別人物を含む接客間隔（終了から） |
| VISIT_COOLDOWN_MINUTES | 60 | 前回認識からこの時間を**超えたら**新しい来店 |
| DISCOUNT_VALID_DAYS | 60 | 新しい来店での特典期限（日数表示も連動） |
| BROWSER_GREETING_TIMEOUT_SECONDS | 180 | 動画・音声が応答しない場合の画面側上限 |
| GREETING_TIMEOUT_SECONDS | 190 | 終了通知が届かない場合のサーバー側上限 |
| DATABASE_PATH | data/shop.db | 顧客DBの保存先 |
| DEBUG_MODE | false | 開発APIと画面の有効化 |
| LOG_LEVEL | INFO | ログ出力レベル |
| HOST / PORT | 127.0.0.1 / 8000 | 起動アドレス／ポート |

HTTPとWebSocketは同じPCのlocalhost/127.0.0.1で使う構成です。別ホストへの公開や認証付き遠隔管理は実装していません。ブラウザ側タイムアウトはサーバー側より短くしてください。

## 動画・音声の変更

動画パスは.envの3項目でまとめて管理し、`/api/config` 経由で画面へ渡します。

```dotenv
CHARACTER_VIDEO_IDLE=/static/videos/idle.mp4
CHARACTER_VIDEO_WELCOME=/static/videos/welcome.mp4
CHARACTER_VIDEO_RETURNING=/static/videos/returning.mp4
CHARACTER_AUDIO_WELCOME=/static/audio/first-visit.wav
CHARACTER_AUDIO_RETURNING=/static/audio/returning.wav
CHARACTER_AUDIO_RETURNING_DISCOUNT=/static/audio/returning-discount.wav
```

対応ファイルをstatic/videosへ配置してください。初期状態では待機中に `idle.mp4`、初来店・再来店の接客中に `yobidashi_mobile.mp4` を使います。MP4/H.264など対象ブラウザで再生できる形式を使います。待機動画はループ、接客動画は1回再生し、音声が長いときは最後のフレームで待ちます。元動画の音は消して、読み上げとの重複を防ぎます。

初来店時は `static/audio/first-visit.wav` を再生し、再生できない場合はブラウザのSpeechSynthesisへ自動的に切り替わります。この音声は「VOICEVOX:四国めたん」を使用しています。元の `.vvproj` には飲み物の旧価格（300円）が残っているため、再生成時はVOICEVOXエンジンを起動し、`python -m tools.export_voicevox_project <project.vvproj> static/audio/first-visit.wav --cues-output static/audio/first-visit.cues.json --replace-text "300円=500円"` を実行してください。元プロジェクトを直接変更せず、音声と字幕を現行価格へ揃えられます。

再来店時は `returning.wav`、60日以内の特典対象者には特典案内を含む `returning-discount.wav` を再生します。「○日ぶり」は画面に表示しますが、事前生成音声では読み上げません。音声ファイルが再生できない場合は、動的なメッセージ全体をSpeechSynthesisで読み上げます。

録音音声の字幕は同名の `*.cues.json` に開始・終了時刻を保存し、音声の再生位置に合わせて切り替えます。画面には最大2行だけ表示します。`.vvproj`から音声と字幕を再生成するときは `--cues-output` でJSONの保存先を指定してください。

読み上げは `static/script.js` の `speak(text)` に分離されています。日本語音声を選び、文章を句点などで区切って字幕と音声を順次切り替えます。読み上げが失敗した文は読める時間だけ字幕を残します。VOICEVOXに変更する場合はこの関数を「音声再生終了で解決するPromise」に置き換えれば、接客状態管理を再利用できます。
SpeechSynthesisの利用方法は [MDN](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis) を参照してください。

## 顔認証・来店・特典の仕様

1. カメラ専用スレッドでフレームを読み、間引きと縮小後にHOGで顔を検出します。複数人が写った場合は一番大きい顔を優先します。
2. face_recognition/dlibが128次元の顔特徴量を生成します。指定時間内で近い特徴量が複数回得られた場合に確定します。写真やフレーム画像は保存しません。
3. SQLite内の特徴量とのユークリッド距離を比較し、閾値内で最も近い顧客を選びます。一致がなければ `customer_000001` 形式のIDで登録し、visit_countを1にします。
4. 一致した顧客は、DBトランザクション内で更新前のlast_seen_atを読みます。経過時間が60分以下なら同一来店、60分超ならvisit_countを1増やします。接客中・クールダウン中も既知の顔のlast_seen_atは更新します。
5. **新しい来店**のとき、更新前のlast_seen_atから60×24時間以内なら特典対象です。60日ちょうどは対象、60日と1秒は対象外です。表示用の日数の切り捨て値では判定しません。
6. その来店の基準日時と特典結果を追加列 `visit_previous_seen_at`、`visit_discount_eligible` に保存します。初来店中の再検知を2回目の来店とみなさず、61日ぶりの人が数秒後に再検知されても特典が有効になりません。再起動後も結果は維持されます。
7. IDLEかつクールダウン経過済みならGREETINGに移り、接客中の別人の新規登録・接客は保留します。画面がない場合は登録・接客を開始しません。接客中に通り過ぎた別人を後から呼び出すキューはありません。

時刻はタイムゾーン付きUTCで保存します。「○日ぶり」は経過した24時間単位です。設定変更は次の来店判定から反映され、進行中の来店の特典は再計算しません。

## WebSocketと状態管理

`/ws` でブラウザが接続し、音声開始操作のあとに `display_ready` を送ります。サーバーは1画面に接客権を割り当てます。

```json
{
  "type": "customer_detected",
  "customer_type": "returning",
  "customer_id": "customer_000001",
  "visit_count": 2,
  "days_since_last_visit": 10,
  "discount_eligible": true,
  "message": "お久しぶりですね。10日ぶりですね。...",
  "greeting_id": "接客ごとの一意なID"
}
```

画面は動画と音声の両方の終了後、`greeting_finished` と同じgreeting_idを返します。サーバーは送信元画面とIDを検証してIDLEを通知します。古い終了通知・別画面の通知は無視します。接続断・再生失敗・無応答タイムアウトにも復帰経路があります。
通常画面には顧客ID・照合距離・顔画像・DB内容を出しません。状態確認は `/health`、`/api/state`、開発画面は `/debug` です。

## DBの初期化・バックアップ

DBは `data/shop.db`、顔特徴量はcustomersテーブルのBLOBです。必須のid/customer_id/face_encoding/first_seen_at/last_seen_at/visit_count/created_at/updated_atを保持します。顔画像ファイルは作成しないため、通常data/facesの削除は不要です。

サーバーをCtrl+Cで停止し、次を実行すると**全顧客と来店情報を初期化**します。

```bat
python -m app.manage reset-db --yes
```

実行前のDBを `data/backups/shop-日時.db` に保存します。復元する場合はサーバーを停止し、現在のDBを退避してからバックアップをDATABASE_PATHへコピーします。バックアップにも顔特徴量が含まれます。完全消去が必要な場合はバックアップも含めて店舗側で管理してください。.env、DB、バックアップはGit対象外です。

## テストとカメラ診断

```bat
pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q app tools tests
node --check static/script.js
node --check static/debug.js
node --test tests/frontend.test.cjs
```

Node.jsは画面の自動テストにだけ必要で、通常の起動には不要です。Pythonテストは一時DBを使い、本番DBとカメラを変更しません。
任意のブラウザ統合テストは、開発サーバーをPORT=8765で起動し、PlaywrightとEdgeが使える環境で `node tools/browser_check.cjs` を実行します。実動画・WebSocket・4種類の接客・IDLE復帰を検証しますが、音声完了は模擬します。

カメラを他アプリやサーバーで使用していない状態で：

```bat
python -m tools.check_camera --seconds 10 --index 0
```

カメラ起動と顔特徴量生成を診断します。画像や顧客DBへの保存はしません。カメラの前に立ち、confirmed_facesが増えることを確認してください。

## トラブルへの対処

| 症状 | 確認すること |
|---|---|
| カメラを開けない | Windowsのカメラ利用許可、他アプリによる占有、CAMERA_INDEX、CAMERA_BACKEND。サーバーは5秒ごとに再試行 |
| 顔が出ない | 正面の明るさ・距離・逆光。FACE_IMAGE_SCALEを0.5にすると小さい顔を検出しやすくなるが負荷が増える |
| 同じ人が新規登録される | 照明・姿勢・眼鏡等をそろえ、閾値を実環境で調整。閾値を大きくすると別人の誤一致も増える |
| 音が出ない | 開始ボタン、PC/ブラウザの音量、日本語音声のインストール。ブラウザ開発者ツールの[SPEECH]ログも確認 |
| 動画が出ない | 配置名と.envのパス、ブラウザで再生可能なコーデック。欠損時は[VIDEO]ログと代替表示 |
| DBエラー | DATABASE_PATHの保存先権限・空き容量・同期ソフト。初期化失敗時はサーバーを維持して再試行 |
| 接客が始まらない | 接続状態、開始ボタン、別の接客画面が開いていないか、人物/全体クールダウン、/health |
| 接客が終了しない | 音声・動画の長さとタイムアウト値。期限後にはIDLEへ戻る |

## ファイル構成・今後の拡張

- app/config.py：環境変数と検証
- app/camera.py、face_service.py：カメラ・顔特徴量・複数観測の確認
- app/database.py、models.py、customer_service.py：永続化・照合・来店・特典・セリフ
- app/reception.py、websocket_manager.py：接客状態・クールダウン・表示権
- app/main.py、__main__.py：FastAPI・起動・API・障害時の復帰
- app/manage.py：DB初期化・バックアップ付きリセット
- static/：全画面向け表示・字幕・動画・音声アダプター
- tests/、tools/：カメラなしテスト・診断

顔照合は確率的で、同一人物でも照明等により一致しない場合があります。現段階は近い1人を接客する構成で、複数人の追跡、なりすまし判定、顧客別削除UI、保存期限による自動削除、特徴量の暗号化、大量顧客の高速検索は未実装です。導入前に店舗で顔データ利用を案内し、保存期間・削除窓口を決めてください。DBを外部へ送信する処理はありません。
今後はVOICEVOX、状況別動画、照合候補の差分検証、検出領域の指定、再訪ごとの履歴テーブルを追加できます。
