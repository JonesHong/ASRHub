## 🔖 核心原則（10 項）

1. **KISS（Keep It Simple, Stupid）**

   * 程式碼簡潔易讀，避免不必要的抽象或複雜化。
   * 每次新增功能前，詢問自己：這是**必要的**嗎？

2. **YAGNI（You Aren’t Gonna Need It）**

   * 聚焦解決「80% 最常見場景」，勿因邊緣的 20% 情境提前過度設計。

3. **SoC（Separation of Concerns，關注點分離）**

   * 在系統層級（Presentation／Business／Data）與模組間，透過清晰介面劃分不同 Concern。
   * 每個模組或元件僅負責高度相關的一組功能。

4. **SOLID 原則**

   * **SRP（Single Responsibility Principle）**：每個類別、元件或函式只應有一個「改變理由」。
   * **OCP（Open–Closed Principle）**：對擴展開放、對修改封閉。
   * **LSP（Liskov Substitution Principle）**：子型別能安全替換父型別且行為一致。
   * **ISP（Interface Segregation Principle）**：不依賴不使用的介面。
   * **DIP（Dependency Inversion Principle）**：高／低階模組皆依賴抽象。

5. **DRY（Don’t Repeat Yourself）**

   * 避免重複程式碼，將共用邏輯抽出以降低後續維護成本。

6. **設計模式 & 善用現成函式庫**

   * 適時運用設計模式（Factory、Strategy、Decorator、Observer…）增進可擴充性。
   * **優先使用成熟函式庫**，避免「重複造輪子」。只有在函式庫無法滿足需求或有安全／效能疑慮時，才自行實作。

7. **文件與溝通**

   * 架構先行，透過設計文件、介面規格（API 定義）與範例程式碼，確保團隊對方向一致。
   * 定期進行 Code Review，讓新舊成員都能順利接手與維護。

8. **可觀察性（Observability）**

   * **Docstring 說明預期行為**：在函式、類別或模組開頭明確描述「目標」、「輸入」、「輸出」與「潛在異常」。
   * **使用 pretty-loguru**：在執行關鍵流程時，以 [`pretty-loguru`](https://pypi.org/project/pretty-loguru/)（基於 Loguru 並整合 Rich 與 Art） 輸出格式化日誌，清楚呈現變數狀態、執行結果與錯誤堆疊。

9. **測試與品質保證**

   * 高覆蓋率的單元測試與整合測試，自動化納入 CI/CD。
   * 每次提交均須通過安全性、效能與相依性檢查。

10. **持續重構（Continuous Refactoring）**

    * 隨需求演進，定期檢視並重構複雜度過高或耦合度深的程式區塊，保持代碼健康。

11. **配置管理（Configuration Management）**

    * 採用 YAML 作為設定檔格式，以提升可讀性與可維護性。
    * 設定檔完成後，必須使用 [`yaml2py`](https://pypi.org/project/yaml2py/) CLI 工具自動轉換為 Python dataclass（`ConfigManager`），程式可從中直接取得設定值，確保型別安全。

---

## ✅ 自我檢查清單（Check List）

開發或修改程式碼前後，皆可檢視：

| 編號 | 檢查內容                               | 符合 |
| -- | ---------------------------------- | -- |
| 1  | 此功能是否足夠簡單直觀，不多餘？（KISS）             | ☐  |
| 2  | 有無為了尚未發生的需求提前設計？（YAGNI）            | ☐  |
| 3  | 各模組是否都有明確的職責與邊界？（SoC）              | ☐  |
| 4  | SOLID 原則是否都有遵循？                    | ☐  |
|    | – SRP、OCP、LSP、ISP、DIP              | ☐  |
| 5  | 重複的邏輯或程式碼是否已抽取？（DRY）               | ☐  |
| 6  | 有無先考慮引用現有函式庫或套件？                   | ☐  |
| 7  | 文件是否清晰、介面定義是否完整？                   | ☐  |
| 8  | **可觀察性**：                          |    |
|    | – 是否在所有公開函式／模組都有詳盡 Docstring？      | ☐  |
|    | – 關鍵流程的日誌是否使用 pretty-loguru 格式化輸出？ | ☐  |
| 9  | 單元測試與整合測試覆蓋率是否充分？                  | ☐  |
|    | CI/CD 是否能自動驗證品質？                   | ☐  |
| 10 | 定期進行重構以改善結構與可讀性？                   | ☐   |
| 11 | 是否採用 YAML 作為設定檔格式？ | ☐ |
| 12 | 設定檔完成後是否使用 yaml2py 自動轉換為 ConfigManager dataclass？ | ☐ |
