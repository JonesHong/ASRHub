import os
from huggingface_hub import HfFolder, hf_hub_download
import gradio as gr
import json
import pandas as pd
import collections
import scipy.signal
import numpy as np
from functools import partial
from openwakeword.model import Model

from openwakeword.utils import download_models
download_models()

# 用 Secret token 從 HF Model Hub 下載私有模型
hf_token = os.environ.get("HF_TOKEN") or HfFolder.get_token()

if hf_token:
    print("載入 KMU 模型...")
    model_path = hf_hub_download(
        repo_id="JTBTechnology/kmu_wakeword",
        filename="hi_kmu_0721.onnx",
        token=hf_token,
        repo_type="model"
    )

# 直接用下載的模型路徑載入
model = Model(wakeword_models=[model_path], inference_framework="onnx")

# Define function to process audio
# def process_audio(audio, state=collections.defaultdict(partial(collections.deque, maxlen=60))):
def process_audio(audio, state=None):
    if state is None:
        state = collections.defaultdict(partial(collections.deque, maxlen=60))
    
    
    # Resample audio to 16khz if needed
    if audio[0] != 16000:
        data = scipy.signal.resample(audio[1], int(float(audio[1].shape[0])/audio[0]*16000))
    else:
        data = audio[1]
    
    # 確保數據是 float32 格式
    if data.dtype != np.float32:
        data = data.astype(np.float32)
    
    # Get predictions
    for i in range(0, data.shape[0], 1280):
        if len(data.shape) == 2 or data.shape[-1] == 2:
            chunk = data[i:i+1280][:, 0]  # just get one channel of audio
        else:
            chunk = data[i:i+1280]

        if chunk.shape[0] == 1280:
            prediction = model.predict(chunk)
            for key in prediction:
                #Fill deque with zeros if it's empty
                if len(state[key]) == 0:
                    state[key].extend(np.zeros(60))
                    
                # Add prediction
                state[key].append(prediction[key])
    
    # Make line plot
    dfs = []
    for key in state.keys():
        df = pd.DataFrame({"x": np.arange(len(state[key])), "y": state[key], "Model": key})
        dfs.append(df)
    
    df = pd.concat(dfs)

    plot = gr.LinePlot(
        value=df,
        x='x',
        y='y',
        color="Model",
        y_lim=(0,1),
        tooltip="Model",
        width=600,
        height=300,
        x_title="Time (frames)",
        y_title="Model Score",
        color_legend_position="bottom"
    )
    # 1. 將 state 轉成可 JSON 序列化格式（dict of lists）
    serializable_state = {k: [float(x) for x in v] for k, v in state.items()}

    # 2. 回傳 serializable_state 給 Gradio
    return plot, serializable_state

# Create Gradio interface and launch

desc = """
這是 [openWakeWord](https://github.com/dscripka/openWakeWord) 最新版本預設模型的小工具示範。
請點一下下面的「開始錄音」按鈕，就能直接用麥克風測試。
系統會即時把每個模型的分數用折線圖秀出來，你也可以把滑鼠移到線上看是哪一個模型。
每一個模型都有自己專屬的喚醒詞或指令句（更多可以參考 [模型說明](https://github.com/dscripka/openWakeWord/tree/main/docs/models)）。
如果偵測到你講了對的關鍵詞，圖上對應模型的分數會突然變高。你可以試著講下面的範例語句試試看：
| 模型名稱          | 建議語句   |
| ------------- | ------ |
| hi_kmu_0721 | 「嗨，高醫」 |
"""

gr_int = gr.Interface(
    title = "語音喚醒展示",
    description = desc,
    css = ".flex {flex-direction: column} .gr-panel {width: 100%}",
    fn=process_audio,
    inputs=[
        gr.Audio(sources=["microphone"], type="numpy", streaming=True, show_label=False), 
        "state"
    ],
    outputs=[
        gr.LinePlot(show_label=False),
        "state"
    ],
    live=True)

gr_int.launch()