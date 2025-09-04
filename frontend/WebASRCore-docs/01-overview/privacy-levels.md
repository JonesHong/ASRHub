# ASR Provider 隱私分級

## 隱私級別定義

```typescript
export enum PrivacyLevel {
  LOCAL = 'local',        // 完全本地處理
  CLOUD_PROXY = 'cloud'   // 使用雲端服務  
}
```

## Provider 隱私配置

```typescript
export const PROVIDER_PRIVACY = {
  whisper: {
    level: PrivacyLevel.LOCAL,
    notice: '音訊完全在您的裝置上處理',
    dataRetention: 'none',
    encryption: 'not-applicable'
  },
  webSpeech: {
    level: PrivacyLevel.CLOUD_PROXY,
    notice: '音訊將上傳至 Google/Apple 伺服器',
    dataRetention: 'varies-by-provider',
    encryption: 'in-transit'
  }
};
```

## 用戶選擇機制

### 初始化時提示

```typescript
// 初始化時提示用戶
if (!config.provider) {
  const choice = await showProviderSelectionDialog();
  config.provider = choice;
}
```

### 隱私選擇對話框

```typescript
async function showProviderSelectionDialog(): Promise<ProviderType> {
  const dialog = createPrivacyDialog({
    title: '選擇語音識別方式',
    options: [
      {
        provider: 'whisper',
        title: '本地處理（推薦）',
        description: '較慢但完全私密，音訊不離開您的裝置',
        icon: '🔐',
        privacy: PROVIDER_PRIVACY.whisper
      },
      {
        provider: 'webSpeech',
        title: '雲端處理',
        description: '快速但需要網路，音訊將傳送至雲端',
        icon: '☁️',
        privacy: PROVIDER_PRIVACY.webSpeech
      }
    ]
  });
  
  return await dialog.show();
}
```

## 隱私通知顯示

```typescript
class PrivacyNotifier {
  static show(provider: string) {
    const privacy = PROVIDER_PRIVACY[provider];
    
    if (privacy.level === PrivacyLevel.CLOUD_PROXY) {
      this.showWarning({
        message: privacy.notice,
        icon: '⚠️',
        duration: 5000
      });
    }
    
    // 記錄用戶選擇
    localStorage.setItem('webasr-privacy-choice', JSON.stringify({
      provider,
      timestamp: Date.now(),
      accepted: true
    }));
  }
}
```

## GDPR 合規考量

```typescript
interface GDPRCompliance {
  // 獲得明確同意
  getUserConsent(): Promise<boolean>;
  
  // 提供資料可攜權
  exportUserData(): Promise<Blob>;
  
  // 清除所有資料
  deleteAllData(): Promise<void>;
  
  // 資訊透明度
  getPrivacyPolicy(): string;
}
```

## 安全建議

1. **預設使用本地處理**：除非用戶明確選擇，否則使用 Whisper
2. **清晰標示**：在 UI 上明確顯示當前使用的處理方式
3. **會話隔離**：每個會話的音訊資料應該獨立處理
4. **定期清理**：自動清理暫存的音訊資料

```typescript
// 自動清理策略
class AudioDataCleaner {
  private cleanupInterval = 60000; // 1 分鐘
  
  startAutoCleaning() {
    setInterval(() => {
      this.cleanupExpiredData();
    }, this.cleanupInterval);
  }
  
  private cleanupExpiredData() {
    // 清理超過 5 分鐘的音訊緩存
    const expirationTime = Date.now() - 5 * 60 * 1000;
    audioCache.clearBefore(expirationTime);
  }
}
```