請根據我提供的內容整理一下變成一份相對正式的 SRS.md

我要設計一款命名為"ASR_Hub"的 ASR Proxy概念整合不同ASR Provider的系統（如：FunASR, local Whisper, Vosk, Google STT API, OpenAI API...等），首先是允許多通訊架構，HTTP, WebSocket, Socket.io, gRPC, Redis，接收聲音檔案的 transcibe、接收聲音 Buffer的 transcribe_stream...等方法，聲音進來以後可選是否要前處理（類似RxJS架構）整合降噪、人聲分離、格式轉換、Sample rate調整...等不同的 Operator讓使用者自行組合 Pipeline以及我們可以提供預設的 Pipeline，最後由使用者不管用任何通訊協定方法，都要可以檢查當前 Provider列表（各Provider優缺描述）、設定檔狀況，並讓使用者自行選定Provider去轉譯或者串流轉譯，若無特別指定系統會有預設的 Provider，使用 yaml作為設定檔並使用yaml2py轉換成 py data class，另外 pretty-loguru記錄所有的 log狀況。

要有喚醒詞模組有 openWakeWord這種 RNN模型的方法和 ASR關鍵字（包含拼音、近似音、同音異字）的比對法