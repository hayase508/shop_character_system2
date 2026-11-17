# shop_character_system2
顔認証により、初来店者を区別して接客するシステム

Webカメラ → 顔特徴量 → SQLite照合 → 来店・特典判定 → 定型接客 → 接客後だけ自動発話検知 → ローカル音声認識 → FAQまたは固定案内 → 録音済み四国めたん音声、という一連の処理を実行します。FAQ外をGeminiへ渡す従来経路も設定で選択できます。
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
   python -m tools.prepare_whisper
   ```

   `prepare_whisper`は初回だけWhisperの`base`モデルをダウンロードし、以後ローカルで再利用できるようにします。モデル取得にはインターネット接続と数分程度の時間が必要です。実行しなくてもサーバーは起動しますが、最初の質問時にモデル取得が発生します。

   **dlibのビルドで失敗する場合：** MicrosoftのVisual Studio Build Toolsで「C++によるデスクトップ開発」（MSVC、Windows SDK、CMakeツール）を導入し、ターミナルを開き直して再実行してください。CMakeが見つからなければ仮想環境で `python -m pip install cmake`、その後 `python -m pip install dlib --verbose` でエラー詳細を確認します。出所不明のwheelは不要です。
   face_recognitionはWindowsを公式サポート対象としていませんが、この実装ではWindows向けカメラ処理とPython 3.10での動作確認を行っています。環境ごとのビルド確認は必要です。根拠：[face_recognition公式](https://github.com/ageitgey/face_recognition#installation)、[dlibのビルド手順](https://dlib.net/compile.html)。

4. 設定をコピーします。

   ```bat
   copy .env.example .env
   notepad .env
   ```

   PowerShellなら `Copy-Item .env.example .env` です。通常は `CAMERA_ENABLED=true`、`DEBUG_MODE=false`、`QUESTION_UNKNOWN_POLICY=staff` のままで使います。この高速モードではGemini APIキーは不要です。FAQ外もGeminiで自由回答させる場合だけ、`QUESTION_UNKNOWN_POLICY=gemini`へ変更し、Google AI Studioで取得したキーを`.env`の`GEMINI_API_KEY`へ記入します。`.env`はGit対象外です。環境変数を別途設定した場合は、環境変数が.envより優先されます。変更後はサーバーを再起動してください。

   標準の高速モードで使う質問回答音声は、VOICEVOXの四国めたんで事前生成済みです。音声を再生成する場合やGemini自由回答モードを利用する場合はWindows版VOICEVOXをインストールしてください。通常の場所へインストールしておけば、`start_shop.bat`が同梱エンジンを自動起動します。標準以外へインストールした場合は、起動前に`VOICEVOX_ENGINE_EXE`環境変数へ`vv-engine\run.exe`の絶対パスを設定してください。

5. 動画を確認します。

   待機中は軽量版の `static/videos/idle_optimized.mp4`、接客中は `static/videos/yobidashi_mobile.mp4` を使います。ファイルがない場合でもサーバーは起動し、画面には「鬼」の代替表示と字幕が出ます。

6. DBを初期化してサーバーを起動します。

   ```bat
   python -m app.manage init-db
   python -m app
   ```

   DBは初回起動時にも自動作成されます。別の起動方法は `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1` です。
   カメラと接客状態を1プロセスで管理するため、**複数workersや、営業中の--reloadは使わないでください**。

7. [接客画面](http://127.0.0.1:8000/) をEdgeまたはChromeで開き、**「接客を開始（音声を有効にする）」** を押します。マイク使用確認が表示されたら「許可」を選びます。「全画面」またはF11でディスプレイ表示にし、音量とマイク入力を確認してください。マイクを拒否しても従来の顔認証接客は利用できます。サーバー停止はターミナルでCtrl+Cです。

   開始ボタンを押す前は顧客を登録しません。最初に開始した1画面だけが接客を担当し、他の画面から接客を終了できません。画面を閉じたら接客を中断してIDLEへ戻ります。再接続した同じ画面は自動復帰し、ページ再読み込み後は開始ボタンを押し直します。

## カメラなしの動作確認

.envで次の2項目を変更し、起動します。

```dotenv
CAMERA_ENABLED=false
DEBUG_MODE=true
```

接客画面で開始ボタンを押してマイクを許可したあと、別タブで [開発テスト画面](http://127.0.0.1:8000/debug) を開いて、初来店・再来店・60日ちょうど・61日経過を試してください。定型案内が終わると「質問があれば、そのままお話しください」へ変わり、マイクに話しかけてVAD・Whisper・回答音声を確認できます。開発画面の文字入力ではFAQ／固定スタッフ案内をマイクなしで確認できます。「Geminiを明示してテスト（開発用）」はAPIキー設定時に実APIを呼ぶ可能性があるため、必要なときだけ使用してください。接客中の追加イベントはHTTP 409です。

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
| CHARACTER_VIDEO_SPEAKING_INTRO | /static/videos/shinfurimuki_optimized.mp4 | 音声開始前に1回だけ最後まで再生する軽量版の振り向き動画 |
| CHARACTER_VIDEO_SPEAKING_LOOP | /static/videos/yobidashi_mobile.mp4 | 振り向き終了後に音声を開始し、音声終了まで繰り返す動画 |
| QUESTION_ENABLED | true | 顔認証後の自動質問受付を有効化 |
| QUESTION_READY_TIMEOUT_SECONDS | 30 | 発話がないREADY状態の上限 |
| QUESTION_RECORDING_MAX_SECONDS | 15 | 1回の録音上限 |
| QUESTION_SESSION_TIMEOUT_SECONDS | 60 | 連続質問を含むセッション全体の上限 |
| QUESTION_SPEAKING_TIMEOUT_SECONDS | 45 | 回答再生が完了しない場合の上限 |
| QUESTION_AUDIO_BITRATE | 128000 | 質問録音のOpusビットレート。認識品質を保つ初期値 |
| QUESTION_UNKNOWN_POLICY | staff | `staff`はFAQ外を固定音声でスタッフ案内。`gemini`は従来の自由回答 |
| QUESTION_INPUT_MODE | microphone | `microphone`は音声質問、`touch`は別タッチパネル、`both`は両方を利用 |
| MICROPHONE_DEVICE_LABEL | 空欄 | 空欄は既定マイク。`USB Condenser Microphone`など製品名の一部を指定すると、その入力を優先 |
| WHISPER_MODEL / DEVICE / COMPUTE_TYPE | base / cpu / int8 | ローカル音声認識モデルと実行方式 |
| WHISPER_TIMEOUT_SECONDS | 30 | 音声認識の上限時間 |
| WHISPER_BEAM_SIZE / MAX_NEW_TOKENS | 3 / 80 | 速度を保ちながら3候補から認識結果を選ぶ設定 |
| WHISPER_INITIAL_PROMPT / HOTWORDS | 会話文脈／店舗語彙 | 鬼・豚汁・たまご定食・QRコードなどの誤認識を減らす語彙 |
| WHISPER_DOMAIN_CORRECTIONS | true | 「お兄さん→鬼さん」など繰り返し起きる店舗固有語の誤認識を補正 |
| WHISPER_NO_SPEECH_THRESHOLD | 0.45 | 無音らしさが高い認識区間を破棄する閾値 |
| WHISPER_MIN_AVG_LOGPROB | -0.8 | 信頼度が低い認識区間を破棄する閾値 |
| WHISPER_VAD_FILTER | true | Whisper前段のSilero VADで人の声がない録音を破棄 |
| WHISPER_VAD_MIN_SPEECH_MS | 400 | Silero VADが音声として採用する最短時間 |
| WHISPER_VAD_MIN_SILENCE_MS | 350 | Silero VADの無音区間判定 |
| WHISPER_VAD_SPEECH_PAD_MS | 200 | 音声の語頭・語尾を守る余白 |
| VAD_START_THRESHOLD | 0.025 | 発話開始とみなすRMS音量の最低値 |
| VAD_START_DURATION_MS | 350 | 動的閾値を超え続ける必要時間 |
| VAD_END_SILENCE_MS | 450 | 発話終了とみなす無音時間。応答速度を優先した初期値 |
| VAD_MIN_SPEECH_MS | 500 | これより短い音を破棄 |
| VAD_RESUME_DELAY_MS | 800 | 鬼の回答終了からマイク再開までの残響待ち |
| VAD_PREROLL_MS | 450 | メモリ内だけで保持する発話確定前バッファ |
| VAD_CALIBRATION_MS | 1200 | マイク再開時に周囲の環境音を測定する時間 |
| VAD_NOISE_MULTIPLIER | 1.8 | 環境音レベルに掛けて動的開始閾値を決める倍率 |
| VAD_NOISE_MARGIN | 0.006 | 環境音より最低限必要な音量差 |
| GEMINI_ENABLED | true | `QUESTION_UNKNOWN_POLICY=gemini`時だけGemini利用を許可 |
| GEMINI_MODEL | gemini-3.5-flash-lite | Google公式の低コスト安定版モデル |
| GEMINI_MAX_REQUESTS_PER_SESSION | 3 | 1接客でのGemini API上限。FAQは数えない |
| GEMINI_CACHE_TTL_SECONDS | 3600 | 同じ自由質問への回答キャッシュ時間 |
| GEMINI_THINKING_LEVEL | minimal | 短い接客回答を優先する低遅延思考設定 |
| GEMINI_PRELOAD | true | SDKと再利用クライアントを起動時に準備し、初回質問の待ち時間を短縮 |
| GEMINI_WARMUP | true | 課金対象の文章生成をせずモデル情報を取得し、起動時にDNS/TLS接続を準備 |
| VOICEVOX_ENABLED | true | Gemini自由回答時や固定音声欠落時に四国めたんで合成 |
| VOICEVOX_SPEAKER_ID | 2 | 四国めたん（ノーマル）のスタイルID |
| VOICEVOX_CACHE_ENTRIES | 64 | 同じ回答の合成済み音声をメモリ内で再利用する件数 |
| VOICEVOX_SPEED_SCALE | 1.08 | 動的回答の話速 |
| VOICEVOX_TIMEOUT_SECONDS / PRELOAD | 15 / true | 合成上限と起動時の話者先読み |

HTTPとWebSocketは同じPCのlocalhost/127.0.0.1で使う構成です。別ホストへの公開や認証付き遠隔管理は実装していません。ブラウザ側タイムアウトはサーバー側より短くしてください。

### 質問タッチパネル

`.env`で`QUESTION_INPUT_MODE=touch`にすると、音声認識を使わず、別画面の定型質問から選択できます。

- 鬼店員ディスプレイ：`http://127.0.0.1:8000/`
- 質問タッチパネル：`http://127.0.0.1:8000/touch`

同じPCの小型タッチディスプレイなら、ブラウザをもう1つ開いて`/touch`を全画面表示してください。別PCやタブレットから利用する場合は、店舗内LAN向けのホスト設定・ファイアウォール設定・アクセス制御を別途設計してください。タッチパネルは顔認証後の案内が終了してREADYになった間だけ操作でき、回答中の連打は409で拒否されます。回答には`static/audio/faq/`の事前生成済み音声を使うため、Whisper・Gemini・動的VOICEVOXを待ちません。

## 動画・音声の変更

動画パスは.envの3項目でまとめて管理し、`/api/config` 経由で画面へ渡します。

```dotenv
CHARACTER_VIDEO_IDLE=/static/videos/idle_optimized.mp4
CHARACTER_VIDEO_WELCOME=/static/videos/welcome.mp4
CHARACTER_VIDEO_RETURNING=/static/videos/returning.mp4
CHARACTER_AUDIO_WELCOME=/static/audio/first-visit.wav
CHARACTER_AUDIO_RETURNING=/static/audio/returning.wav
CHARACTER_AUDIO_RETURNING_DISCOUNT=/static/audio/returning-discount.wav
```

対応ファイルをstatic/videosへ配置してください。初期状態では待機中に軽量化済みの `idle_optimized.mp4`、話し始めに `shinfurimuki_optimized.mp4`、接客中に `yobidashi_mobile.mp4` を使います。MP4/H.264など対象ブラウザで再生できる形式を使います。待機動画は常時ループし、接客動画は鬼の音声が続いている間だけ繰り返して、音声終了時に停止します。元動画の音は消して、読み上げとの重複を防ぎます。

初来店時は `static/audio/first-visit.wav` を再生し、再生できない場合はブラウザのSpeechSynthesisへ自動的に切り替わります。この音声は「VOICEVOX:四国めたん」を使用しています。元の `.vvproj` には飲み物の旧価格（300円）と豚汁を含まない旧案内が残っているため、再生成時はVOICEVOXエンジンを起動し、`python -m tools.export_voicevox_project <project.vvproj> static/audio/first-visit.wav --cues-output static/audio/first-visit.cues.json --replace-text "300円=500円" --replace-text "たまごとご飯はお代わり自由です。=豚汁とたまごとご飯は、すべてお代わり自由です。"` を実行してください。元プロジェクトを直接変更せず、音声と字幕を現行内容へ揃えられます。

初来店案内中は、鬼店員を中央にして、左側へ`static/images/usage-guide.png`、右側へ`static/images/checkout-machine.png`を表示します。再来店案内・質問受付・待機中には両方の案内画像を表示しません。

再来店時は `returning.wav`、60日以内の特典対象者には `returning-discount.wav` を再生します。特典対象者には「QRコードを精算機にかざすと、豚汁たまご定食が500円になる」ことを音声と字幕で案内します。音声ファイルが再生できない場合は、動的なメッセージ全体をSpeechSynthesisで読み上げます。

録音音声の字幕は同名の `*.cues.json` に開始・終了時刻を保存し、音声の再生位置に合わせて切り替えます。画面には最大2行だけ表示します。`.vvproj`から音声と字幕を再生成するときは `--cues-output` でJSONの保存先を指定してください。

読み上げは `static/script.js` の `speak(text)` に分離されています。事前録音またはVOICEVOXのWAVを優先し、取得できない場合は日本語のSpeechSynthesisへ切り替えます。文章を句点などで区切って字幕と音声を順次切り替え、読み上げに失敗した文は読める時間だけ字幕を残します。
SpeechSynthesisの利用方法は [MDN](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis) を参照してください。

## 接客後の自動質問機能

定型案内中はマイクを停止し、鬼自身の声を質問として拾いません。案内が正常終了し、ブラウザでマイクが許可されている場合だけ`GREETING → READY`へ移ります。質問セッションの状態は`READY / LISTENING / TRANSCRIBING / THINKING / SPEAKING`です。これらの間は新しい顔認証接客を重ねません。異常時やセッション期限後は必ずIDLEへ戻ります。

READY開始時は、まず1,200msだけWeb Audio APIのRMS音量から周囲の環境音を測定します。発話開始閾値は0.025を最低値とし、測定した環境音の1.8倍または環境音+0.006のうち最も高い値へ自動調整します。この動的閾値を350ms超え続けた場合だけ発話開始です。AudioContextは開始ボタンを押したユーザー操作中に起動し、GREETING後も停止状態にならないよう再利用します。MediaRecorderは音量が閾値を超えた発話候補からだけ128kbpsで録音し、確定前音声も質問へ含めます。短い音はメモリ上で即時破棄し、READYで待っている間の音声は保存しません。音声はファイル保存せず、450msの無音または15秒の上限で終了し、500ms未満の短い物音はサーバーへ送りません。マイクには`echoCancellation`と`noiseSuppression`を要求し、静かな環境音を発話レベルまで増幅しないよう`autoGainControl`は無効化します。TRANSCRIBING以降と鬼の回答中はマイクストリーム自体を停止し、回答後も800ms待ってから環境音を再測定します。

質問音声はローカルのfaster-whisperへ渡し、日本語として認識します。カメラ運用時はサーバー起動後にモデルをバックグラウンドで先読みし、最初の質問でのロード待ちを減らします。モデルはプロセス内で再利用します。ブラウザ側の高速VADに加えてWhisper前段のSilero VADでも人の声を確認し、3候補の低遅延デコード、短い会話文脈、店舗語彙のhotwordsを使用します。無音確率または平均対数確率から信頼度の低い区間を除外し、無音で生じやすい定型的な誤認識と質問文に見えない背景音由来の文章も破棄します。さらに「トンジル→豚汁」「お兄さん→鬼さん」など、この店舗で繰り返し起きる保守的な表記補正を行います。音声はGeminiへ送りません。認識結果はまずローカルFAQへ照合し、料金、お代わり、配膳、再来店特典、現在セッションの割引対象質問はAPIを使わず回答します。特典に関する回答ではQRコードを精算機にかざす手順も案内します。認識失敗・空文字・短すぎる結果では回答音声を流さずREADYへ戻り、Geminiも呼びません。

標準の`QUESTION_UNKNOWN_POLICY=staff`では、FAQに一致しない質問へ「お答えできません。詳しくはスタッフにお尋ねください。」という録音済み音声を即時返します。この経路ではGeminiも実行時VOICEVOX合成も呼ばないため、回答生成の待ち時間・API費用・外部送信がありません。

従来の自由回答が必要な場合だけ`QUESTION_UNKNOWN_POLICY=gemini`へ変更します。この場合、FAQとキャッシュに一致しない自由質問を、`GEMINI_ENABLED=true`、APIキー設定済み、1セッション3回未満の条件でGeminiへ送ります。送るのは質問、鬼の話し方、公開済み店舗情報だけです。顔画像、特徴量、customer_id、来店履歴、DB、音声は送信しません。同時リクエストは1件です。Gemini障害、429、タイムアウト、キー未設定時は店員への確認を促すローカル文へ切り替わります。有料サービスへ自動切替しません。

実装時点の公式SDKは[Google Gen AI SDK](https://ai.google.dev/gemini-api/docs/libraries)です。初期モデルの`gemini-3.5-flash-lite`はGoogle公式が案内する安定版・低コストモデルです。無料枠や料金条件はアカウント・地域・時期で変わるため、[公式モデル一覧](https://ai.google.dev/gemini-api/docs/models)とGoogle AI Studioの使用量を確認してください。API利用を完全に止める場合は`GEMINI_ENABLED=false`にします。

FAQ、FAQ外のスタッフ案内、各種障害案内は `static/audio/faq/` に四国めたんのWAVを事前生成し、質問時の音声合成を省略します。鬼店員の字幕・固定音声・Gemini回答は丁寧な「です・ます調」に統一しています。`python -m tools.generate_faq_audio` でVOICEVOXから再生成できます。標準モードの回答待ちは、ほぼVADの無音判定とWhisper認識だけです。`QUESTION_UNKNOWN_POLICY=gemini`を選んだ場合のみ、Gemini回答をVOICEVOXで動的合成します。VOICEVOXに失敗した場合はSpeechSynthesis、それも失敗した場合は字幕だけを表示します。回答終了後800ms待ち、環境音を1,200ms測定してから追加質問を受け付けます。各処理時間は`[PERFORMANCE]`ログで確認できます。

## 顔認証・来店・特典の仕様

1. カメラ専用スレッドでフレームを読み、間引きと縮小後にHOGで顔を検出します。複数人が写った場合は一番大きい顔を優先します。
2. face_recognition/dlibが128次元の顔特徴量を生成します。指定時間内で近い特徴量が複数回得られた場合に確定します。写真やフレーム画像は保存しません。
3. SQLite内の特徴量とのユークリッド距離を比較し、閾値内で最も近い顧客を選びます。一致がなければ `customer_000001` 形式のIDで登録し、visit_countを1にします。
4. 一致した顧客は、DBトランザクション内で更新前のlast_seen_atを読みます。経過時間が60分以下なら同一来店、60分超ならvisit_countを1増やします。接客中・クールダウン中も既知の顔のlast_seen_atは更新します。
5. **新しい来店**のとき、更新前のlast_seen_atから60×24時間以内なら特典対象です。60日ちょうどは対象、60日と1秒は対象外です。表示用の日数の切り捨て値では判定しません。対象者には、来店時に渡されたQRコードを精算機へかざすと豚汁たまご定食が500円になることを案内します。
6. その来店の基準日時と特典結果を追加列 `visit_previous_seen_at`、`visit_discount_eligible` に保存します。初来店中の再検知を2回目の来店とみなさず、61日ぶりの人が数秒後に再検知されても特典が有効になりません。再起動後も結果は維持されます。
7. IDLEかつクールダウン経過済みならGREETINGに移り、接客中または質問セッション中の別人の新規登録・接客は保留します。画面がない場合は登録・接客を開始しません。途中で通り過ぎた別人を後から呼び出すキューはありません。

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

画面は動画と音声の両方の終了後、`greeting_finished` と同じgreeting_idを返します。質問可能ならREADY、マイク利用不可なら従来通りIDLEへ移ります。質問には接客ごとの`question_session_id`と発話ごとの`question_id`を付け、遅れて届いた古い認識結果・別画面の通知は無視します。接続断・再生失敗・各段階の無応答タイムアウトにも復帰経路があります。
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
| 質問待ちにならない | 開始ボタンでマイクを許可したか、QUESTION_ENABLED、VAD_ENABLED、ブラウザのサイト権限、/healthのquestions欄 |
| 声を検知しない／環境音で反応する | まず周囲の音が静かな状態でREADYへ入り直して自動測定させる。誤反応時はVAD_START_THRESHOLD、VAD_NOISE_MULTIPLIER、VAD_START_DURATION_MSを上げ、反応しにくい場合は少しずつ下げる |
| Whisperが遅い | `python -m tools.prepare_whisper`を一度実行。WHISPER_MODEL=base、DEVICE=cpu、COMPUTE_TYPE=int8を確認 |
| FAQ外でスタッフ案内になる | 標準の高速動作です。自由回答が必要な場合だけ`QUESTION_UNKNOWN_POLICY=gemini`とGemini設定を確認 |
| 回答がSpeechSynthesisになる | VOICEVOXのインストール、`http://127.0.0.1:50021/version`、VOICEVOX_ENABLED、サーバーの`[VOICEVOX]`ログを確認。標準外の場所ならVOICEVOX_ENGINE_EXEを設定 |

## ファイル構成・今後の拡張

- app/config.py：環境変数と検証
- app/camera.py、face_service.py：カメラ・顔特徴量・複数観測の確認
- app/database.py、models.py、customer_service.py：永続化・照合・来店・特典・セリフ
- app/reception.py、websocket_manager.py：接客状態・クールダウン・表示権
- app/question_service.py：ローカルFAQ、個別特典回答、FAQ外の固定案内、任意のGemini経路
- app/speech_service.py、voicevox_service.py：ローカルWhisper認識・VOICEVOX四国めたん合成
- app/main.py、__main__.py：FastAPI・起動・API・障害時の復帰
- app/manage.py：DB初期化・バックアップ付きリセット
- static/：全画面向け表示・字幕・動画・音声アダプター
- tests/、tools/：カメラなしテスト・VADテスト・診断・Whisperモデル準備

顔照合は確率的で、同一人物でも照明等により一致しない場合があります。現段階は近い1人を接客する構成で、複数人の追跡、なりすまし判定、顧客別削除UI、保存期限による自動削除、特徴量の暗号化、大量顧客の高速検索は未実装です。導入前に店舗で顔データ利用を案内し、保存期間・削除窓口を決めてください。DBを外部へ送信する処理はありません。
質問音声と質問文は永続保存せず、顧客情報とも紐付けません。今後は状況別動画、照合候補の差分検証、検出領域の指定、再訪ごとの履歴テーブルを追加できます。
