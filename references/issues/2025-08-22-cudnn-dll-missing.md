# 問題標題（簡短扼要）

## 🗓 發生日
2025-08-22

## ❓ 問題描述
- Could not located cublas64_11.dll

## 🔍 嘗試過的解法

## ✅ 最終解法
- 下載(cuDNN v8.1.1 (Feburary 26th, 2021), for CUDA 11.0,11.1 and 11.2)[https://developer.nvidia.com/rdp/cudnn-archive#a-collapse811-111]並將此套件的 DLL 放在與“ctranslate2.dll”相同的資料夾中，用指令` pip show ctranslate2 `取得此資料夾

## 📚 參考資料
- [Github](https://github.com/SYSTRAN/faster-whisper/discussions/715#discussioncomment-10903540)
