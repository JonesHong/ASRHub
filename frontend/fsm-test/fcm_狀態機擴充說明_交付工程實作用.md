# FCM 狀態機擴充 — 精簡工程說明

*版本：v1.1（2025‑08‑12）*

> 目標：在 **batch / non‑streaming / streaming** 架構下，加入 **BUSY** 與 **INTERRUPT\_REPLY**，支援「回覆可被打斷」、保持喚醒視窗（連續對話）、以及 LLM/TTS 分散式接手的等待機制。**不改動原三策略**，以**通用規則**前置處理；實作細節保留彈性。

---

## 1) 狀態（States）

`IDLE`｜`LISTENING`｜`ACTIVATED`（喚醒視窗）｜`RECORDING`（非串流）｜`STREAMING`（ASR 串流）｜`TRANSCRIBING`｜`PROCESSING`（批次）｜``（系統回覆中：LLM 生成／TTS 播放）｜`ERROR`｜`RECOVERING`

> 不合併狀態；透過 **auto‑chaining** 實現「喚醒後立即收音/串流」。

---

## 2) 事件（Events）與方向（Direction）

### Inbound（外部→FSM）

- `LLM_REPLY_STARTED`｜`LLM_REPLY_FINISHED`
- `TTS_PLAYBACK_STARTED`｜`TTS_PLAYBACK_FINISHED`
- `INTERRUPT_REPLY { sessionId, source: 'UI'|'VISION'|'VOICE', target: 'TTS'|'LLM'|'BOTH', origin, meta? }`
- `END_RECORDING`｜`END_ASR_STREAMING`（ASR provider 串流結束；建議帶 `endTrigger`）

### Internal（ASRHub 內部）

- `WAKE_TRIGGERED`（關鍵字/裝置側喚醒）
- `START_RECORDING`｜`START_ASR_STREAMING`（auto‑chaining）
- `TRANSCRIPTION_DONE`｜`UPLOAD_*`｜`BEGIN_TRANSCRIPTION`｜`RESET`｜`ERROR`｜`RECOVER`

### Outbound（FSM→外部）

- `ASR_CAPTURE_STARTED { sessionId, mode: 'recording'|'streaming'|'wakeOnly', origin }`
- `ASR_CAPTURE_ENDED { sessionId, reason, endTrigger? }`

> 提示音/燈效由訂閱者處理；FSM 僅發布語義事件。

#### 2.1 Audio 事件歸屬原則

- **預設**：Audio 成本高，與音訊擷取/傳輸/終止相關之事件皆屬 **ASRHub Internal**（`WAKE_TRIGGERED`、`INTERRUPT_REPLY(VOICE)`、`END_RECORDING`、`START/END_ASR_STREAMING`）。
- **例外**：若喚醒/錄音在 Web 前端完成，該端可作為 **Inbound** 將事件與音訊送入 ASRHub（責任邊界清楚標記）。

---

## 3) 通用轉換規則（優先序）

`RESET` ＞ `ERROR/RECOVER` ＞ `TIMEOUT` ＞ 回覆開始/結束 ＞ 其餘策略事件。

1. **回覆開始 →** **`BUSY`**：任何非錯誤狀態，收 `LLM_REPLY_STARTED` 或 `TTS_PLAYBACK_STARTED` → `BUSY`（enter‑hook 暫停 ASR）。
2. **BUSY 收斂**：
   - `INTERRUPT_REPLY`：立即 → `ACTIVATED`（若偵測已在說話，可直跳 `RECORDING/STREAMING`）。
   - `TTS_PLAYBACK_FINISHED`：→ `ACTIVATED`（可配置回 `LISTENING`）。
   - `LLM_REPLY_FINISHED` + `ttsClaimTtl` 逾時無 TTS 接手：→ `ACTIVATED`。
3. **ACTIVATED 降階**：`awakeTimeoutMs` 逾時 → `LISTENING`。

---

## 4) 三種模式流程（最小必需）

### Non‑Streaming

`… → WAKE_TRIGGERED → ACTIVATED`（auto‑chaining）`→ START_RECORDING → RECORDING → END_RECORDING → TRANSCRIBING → TRANSCRIPTION_DONE` →

- 等 `llmClaimTtl`（預設 3s）：
  - 有 `LLM_REPLY_STARTED` → ``
  - 無 → `ACTIVATED`
- `BUSY（LLM）`：`LLM_REPLY_FINISHED` → 等 `ttsClaimTtl`（預設 3s）
  - 有 `TTS_PLAYBACK_STARTED` → 持續 `BUSY`
  - 無 → `ACTIVATED`
- `BUSY（TTS）`：`TTS_PLAYBACK_FINISHED` → `ACTIVATED`

### Streaming

`… → WAKE_TRIGGERED → ACTIVATED`（auto‑chaining）`→ START_ASR_STREAMING → STREAMING → END_ASR_STREAMING` → 後續**同 Non‑Streaming**（等 LLM → BUSY → 等 TTS → BUSY → 完畢回 `ACTIVATED`）。

### Batch

不引入 LLM/TTS 回覆事件；流程結束 → `IDLE`。未來若需口語回覆再開 `BUSY`。

---

## 5) 計時器與等待

- **保留**：

  - `awakeTimeoutMs`（`ACTIVATED` 喚醒視窗；超時→`LISTENIG`）
  - `maxRecordingMs`（於 `RECORDING`）：VAD 靜音收斂與上限。
  - `maxStreamingMs`（於 `STREAMING`）：串流靜音收斂與上限。
  - `llmClaimTtl`（轉譯後等待 LLM 接手）
  - `ttsClaimTtl`（LLM 完成後等待 TTS 接手）
  - `sessionIdleTimeoutMs`（全域長時無互動→`IDLE`）

- **無上限**：`maxRecordingMs`、`maxStreamingMs` 支援 **-1 = 無上限**；建議加 watchdog/遙測與 UI 停止作保險。

- **Orchestrator**：若能預告「本輪無 LLM/TTS」，則**跳過等待**直接轉下一狀態。

---

## 6) Auto‑chaining（建議）

- `autoCaptureOnWake=true`：
  - Non‑Streaming：`WAKE_TRIGGERED → ACTIVATED`（0\~300ms）`→ START_RECORDING`
  - Streaming：`WAKE_TRIGGERED → ACTIVATED`（0\~300ms）`→ START_ASR_STREAMING`
- 進入 `RECORDING/STREAMING` 時發布 `ASR_CAPTURE_STARTED`；離開時發布 `ASR_CAPTURE_ENDED`。

---

## 7) Hooks 與協調

- `onBusyEnter`：`pauseASR(sessionId)`（半雙工預設；可設 `minTTSBargeInDelayMs`）。
- `onBusyExit`：`resumeASR(sessionId)`。
- `onInterrupt`：依 `target` 執行 `stopTTS()`／`cancelLLMStream()`；若 VOICE 且已在說話 → 直跳 `RECORDING/STREAMING`。

---

## 8) 預設配置（可改）

```text
autoCaptureOnWake = true
awakeTimeoutMs = 8000
llmClaimTtl = 3000
ttsClaimTtl = 3000
keepAwakeAfterReply = true          # BUSY 收斂預設回 ACTIVATED
returnAfterCapture = 'activated'    # 或 'listening'
allowBargeIn = true
maxRecordingMs = -1
maxStreamingMs = -1
playCues = true                     # 發布 ASR_CAPTURE_* 供提示音訂閱
cueDebounceMs = 500
cueWakeOnlySuppressionMs = 300
sessionIdleTimeoutMs = 600000
```

---

## 9) 驗收測試（最小集）

1. **自然回覆**：`TRANSCRIPTION_DONE → (LLM) BUSY → (TTS) BUSY → TTS_PLAYBACK_FINISHED → ACTIVATED`。
2. **無 LLM**：`TRANSCRIPTION_DONE` + `llmClaimTtl` 逾時 → `ACTIVATED`。
3. **無 TTS**：`LLM_REPLY_FINISHED` + `ttsClaimTtl` 逾時 → `ACTIVATED`。
4. **打斷**：BUSY 中 `INTERRUPT_REPLY` → 停 TTS/取消 LLM → `ACTIVATED`（或 barge‑in 直跳收音）。
5. **喚醒視窗**：`ACTIVATED` 超時 → `LISTENING`；無上限錄音/串流時 watchdog 可告警收斂。

---

### TL;DR（工程師重點）

- 新增：`BUSY`、`LLM_REPLY_*`、`TTS_PLAYBACK_*`、`INTERRUPT_REPLY`；Outbound `ASR_CAPTURE_*`。
- 非/串流：轉譯或結束串流後 **等 3 秒** 看 LLM 接手；LLM 結束 **再等 3 秒** 看 TTS 接手；TTS 完畢或逾時回 `ACTIVATED`；`ACTIVATED` 超時回 `LISTENING`。
- 刪除靜音計時器；`max*Ms` 支援 `-1`；其餘以事件驅動收斂；Orchestrator 可跳過等待。

