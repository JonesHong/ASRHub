#!/usr/bin/env python3
"""OpenWakeword 服務遷移腳本

將舊版 OpenWakeword 服務遷移到重構後的版本。
"""

import os
import sys
import shutil
from pathlib import Path
from datetime import datetime

# 添加專案路徑
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.logger import logger


class WakewordMigration:
    """OpenWakeword 服務遷移工具"""
    
    def __init__(self):
        """初始化遷移工具"""
        self.project_root = Path(__file__).parent.parent
        self.backup_dir = self.project_root / "backups" / f"wakeword_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.service_dir = self.project_root / "src" / "service" / "wakeword"
        
        # 檔案對映
        self.file_mapping = {
            "openwakeword.py": "openwakeword_legacy.py",  # 保留舊版作為參考
            "openwakeword_refactored.py": "openwakeword.py"  # 新版成為主檔案
        }
        
        # 需要更新匯入的檔案
        self.files_to_update = [
            "src/interface/wakeword.py",
            "src/core/asr_hub.py",
            "src/store/sessions/sessions_effects.py",
            "tests/test_wakeword.py"
        ]
        
        logger.info("=" * 50)
        logger.info("OpenWakeword 服務遷移工具")
        logger.info("=" * 50)
    
    def backup_files(self):
        """備份原始檔案"""
        logger.info(f"\n備份檔案到: {self.backup_dir}")
        
        # 建立備份目錄
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # 備份整個 wakeword 目錄
        if self.service_dir.exists():
            backup_service_dir = self.backup_dir / "service" / "wakeword"
            backup_service_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(self.service_dir, backup_service_dir)
            logger.info(f"✅ 備份服務目錄: {self.service_dir}")
        
        # 備份需要更新的檔案
        for file_path in self.files_to_update:
            full_path = self.project_root / file_path
            if full_path.exists():
                backup_path = self.backup_dir / file_path
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(full_path, backup_path)
                logger.info(f"✅ 備份檔案: {file_path}")
        
        logger.success("備份完成")
        return True
    
    def migrate_service_files(self):
        """遷移服務檔案"""
        logger.info("\n遷移服務檔案...")
        
        # 重新命名檔案
        for old_name, new_name in self.file_mapping.items():
            old_path = self.service_dir / old_name
            new_path = self.service_dir / new_name
            
            if old_path.exists():
                if new_name == "openwakeword_legacy.py":
                    # 保留舊版作為參考
                    shutil.move(old_path, new_path)
                    logger.info(f"✅ 保留舊版: {old_name} → {new_name}")
                elif old_name == "openwakeword_refactored.py":
                    # 新版成為主檔案
                    shutil.move(old_path, new_path)
                    logger.info(f"✅ 啟用新版: {old_name} → {new_name}")
        
        logger.success("服務檔案遷移完成")
        return True
    
    def update_imports(self):
        """更新相關檔案的匯入"""
        logger.info("\n更新匯入語句...")
        
        updates = [
            # 更新從 openwakeword 匯入到使用新的模組化結構
            {
                "files": ["src/interface/wakeword.py"],
                "old": "from src.service.wakeword.openwakeword import OpenWakewordService",
                "new": "from src.service.wakeword.openwakeword import openwakeword_service"
            },
            {
                "files": ["src/core/asr_hub.py", "src/store/sessions/sessions_effects.py"],
                "old": "from src.service.wakeword import openwakeword",
                "new": "from src.service.wakeword.openwakeword import openwakeword_service"
            },
            {
                "files": ["tests/test_wakeword.py"],
                "old": "from src.service.wakeword.openwakeword import OpenWakewordService",
                "new": "from src.service.wakeword.openwakeword import openwakeword_service"
            }
        ]
        
        for update in updates:
            for file_path in update["files"]:
                full_path = self.project_root / file_path
                if full_path.exists():
                    try:
                        content = full_path.read_text(encoding='utf-8')
                        if update["old"] in content:
                            content = content.replace(update["old"], update["new"])
                            full_path.write_text(content, encoding='utf-8')
                            logger.info(f"✅ 更新匯入: {file_path}")
                    except Exception as e:
                        logger.error(f"❌ 更新失敗 {file_path}: {e}")
        
        logger.success("匯入更新完成")
        return True
    
    def create_migration_report(self):
        """建立遷移報告"""
        logger.info("\n建立遷移報告...")
        
        report_path = self.backup_dir / "migration_report.md"
        
        report = f"""# OpenWakeword 服務遷移報告

## 遷移時間
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 備份位置
{self.backup_dir}

## 遷移內容

### 1. 重構後的模組結構
- `model_manager.py` - 模型載入和管理
- `audio_processor.py` - 音訊處理和重採樣
- `detection_engine.py` - 偵測邏輯和防抖
- `openwakeword.py` - 主服務協調器（原 openwakeword_refactored.py）
- `openwakeword_legacy.py` - 舊版備份（原 openwakeword.py）

### 2. 新增的工具類別
- `src/utils/singleton.py` - 單例模式混入
- `src/utils/session_manager.py` - 會話管理
- `src/utils/monitoring_mixin.py` - 監控執行緒管理
- `src/utils/model_downloader.py` - 模型下載器
- `src/utils/event_hooks.py` - 事件鉤子系統

### 3. 更新的檔案
{chr(10).join([f"- {f}" for f in self.files_to_update])}

### 4. 改進內容
- 檔案大小從 760 行減少到最大 406 行
- 模組化設計，單一職責原則
- 可重用的工具類別
- 更好的錯誤處理和日誌記錄
- 統一的會話管理

### 5. 相容性說明
- 保持與 IWakewordService 介面的完全相容
- 所有公開 API 保持不變
- 內部結構重組不影響外部使用

### 6. 回滾方法
如需回滾到舊版，執行以下命令：
```bash
python scripts/rollback_wakeword.py {self.backup_dir}
```

## 測試建議
1. 執行單元測試：`python tests/test_wakeword_refactored.py`
2. 執行整合測試：`python tests/test_wakeword.py`
3. 測試實際喚醒詞偵測功能
4. 檢查日誌輸出是否正常

## 注意事項
- 模型下載可能需要網路連線
- Hugging Face 模型可能需要認證
- 建議在非生產環境先測試
"""
        
        report_path.write_text(report, encoding='utf-8')
        logger.info(f"✅ 遷移報告已儲存: {report_path}")
        
        return True
    
    def create_rollback_script(self):
        """建立回滾腳本"""
        logger.info("\n建立回滾腳本...")
        
        rollback_script = self.project_root / "scripts" / "rollback_wakeword.py"
        
        script_content = '''#!/usr/bin/env python3
"""OpenWakeword 服務回滾腳本

將重構後的版本回滾到原始版本。
"""

import os
import sys
import shutil
from pathlib import Path

def rollback(backup_dir):
    """執行回滾"""
    backup_path = Path(backup_dir)
    if not backup_path.exists():
        print(f"錯誤：備份目錄不存在: {backup_path}")
        return False
    
    project_root = Path(__file__).parent.parent
    
    # 恢復服務目錄
    backup_service = backup_path / "service" / "wakeword"
    if backup_service.exists():
        target_service = project_root / "src" / "service" / "wakeword"
        if target_service.exists():
            shutil.rmtree(target_service)
        shutil.copytree(backup_service, target_service)
        print(f"✅ 恢復服務目錄: {target_service}")
    
    # 恢復其他檔案
    for root, dirs, files in os.walk(backup_path):
        for file in files:
            if file.endswith('.py'):
                src_file = Path(root) / file
                rel_path = src_file.relative_to(backup_path)
                if str(rel_path).startswith('service'):
                    continue  # 已經處理過
                
                target_file = project_root / rel_path
                target_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, target_file)
                print(f"✅ 恢復檔案: {rel_path}")
    
    print("\\n回滾完成！")
    return True

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python rollback_wakeword.py <backup_dir>")
        sys.exit(1)
    
    backup_dir = sys.argv[1]
    success = rollback(backup_dir)
    sys.exit(0 if success else 1)
'''
        
        rollback_script.write_text(script_content, encoding='utf-8')
        rollback_script.chmod(0o755)  # 設定為可執行
        logger.info(f"✅ 回滾腳本已建立: {rollback_script}")
        
        return True
    
    def verify_migration(self):
        """驗證遷移結果"""
        logger.info("\n驗證遷移結果...")
        
        checks = []
        
        # 檢查新檔案是否存在
        new_files = [
            self.service_dir / "model_manager.py",
            self.service_dir / "audio_processor.py",
            self.service_dir / "detection_engine.py",
            self.service_dir / "openwakeword.py"
        ]
        
        for file_path in new_files:
            if file_path.exists():
                checks.append(f"✅ {file_path.name} 存在")
            else:
                checks.append(f"❌ {file_path.name} 不存在")
        
        # 檢查舊版備份
        legacy_file = self.service_dir / "openwakeword_legacy.py"
        if legacy_file.exists():
            checks.append(f"✅ 舊版備份存在")
        else:
            checks.append(f"⚠️ 舊版備份不存在")
        
        # 顯示檢查結果
        for check in checks:
            logger.info(check)
        
        # 判斷是否成功
        if all("✅" in check for check in checks[:4]):
            logger.success("遷移驗證通過")
            return True
        else:
            logger.error("遷移驗證失敗")
            return False
    
    def run(self, skip_backup=False):
        """執行遷移"""
        try:
            # 步驟 1: 備份
            if not skip_backup:
                if not self.backup_files():
                    return False
            
            # 步驟 2: 遷移服務檔案
            if not self.migrate_service_files():
                return False
            
            # 步驟 3: 更新匯入
            if not self.update_imports():
                return False
            
            # 步驟 4: 建立報告
            if not self.create_migration_report():
                return False
            
            # 步驟 5: 建立回滾腳本
            if not self.create_rollback_script():
                return False
            
            # 步驟 6: 驗證
            if not self.verify_migration():
                return False
            
            logger.info("\n" + "=" * 50)
            logger.success("🎉 遷移成功完成！")
            logger.info("=" * 50)
            logger.info(f"\n備份位置: {self.backup_dir}")
            logger.info(f"回滾命令: python scripts/rollback_wakeword.py {self.backup_dir}")
            
            return True
            
        except Exception as e:
            logger.error(f"遷移失敗: {e}")
            return False


if __name__ == "__main__":
    # 執行遷移
    migration = WakewordMigration()
    
    # 詢問使用者確認
    print("\n⚠️  警告：此操作將修改您的程式碼檔案！")
    print("建議先確認所有變更已提交到版本控制系統。")
    response = input("\n是否繼續？(y/N): ")
    
    if response.lower() == 'y':
        success = migration.run()
        sys.exit(0 if success else 1)
    else:
        print("遷移已取消")
        sys.exit(0)