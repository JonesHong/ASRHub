#!/usr/bin/env python3
"""
檢查 requirements.txt 中所有套件的安裝狀態和版本號
並生成帶版本號的 requirements.txt
"""

import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple
import re

def parse_requirement(line: str) -> Tuple[str, Optional[str]]:
    """解析 requirement 行，返回套件名稱和版本限制"""
    # 移除註解
    if '#' in line:
        line = line[:line.index('#')]
    line = line.strip()
    
    if not line or line.startswith('#'):
        return None, None
    
    # 處理帶有額外選項的套件（如 uvicorn[standard]）
    match = re.match(r'^([a-zA-Z0-9_-]+(?:\[[^\]]+\])?)(.*)', line)
    if match:
        package_name = match.group(1)
        version_spec = match.group(2).strip()
        
        # 提取基本套件名稱（用於 pip show）
        base_package = package_name.split('[')[0]
        return base_package, version_spec
    
    return None, None

def get_installed_version(package_name: str) -> Optional[str]:
    """使用 pip show 獲取已安裝的版本"""
    try:
        result = subprocess.run(
            ['pip', 'show', package_name],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if line.startswith('Version:'):
                    return line.split(':', 1)[1].strip()
    except Exception as e:
        print(f"  錯誤檢查 {package_name}: {e}", file=sys.stderr)
    return None

def check_requirements():
    """檢查所有 requirements"""
    requirements_file = Path('requirements.txt')
    if not requirements_file.exists():
        print("❌ requirements.txt 不存在！")
        return
    
    print("🔍 檢查 requirements.txt 中的套件...\n")
    print(f"{'套件名稱':<30} {'安裝版本':<15} {'要求版本':<15} {'狀態'}")
    print("-" * 80)
    
    results = []
    missing_packages = []
    installed_packages = []
    
    with open(requirements_file, 'r', encoding='utf-8') as f:
        for line in f:
            original_line = line.strip()
            package_name, version_spec = parse_requirement(line)
            
            if not package_name:
                if original_line and not original_line.startswith('#'):
                    results.append(original_line)  # 保留原始行（如空行或註解）
                continue
            
            installed_version = get_installed_version(package_name)
            
            if installed_version:
                status = "✅ 已安裝"
                installed_packages.append((package_name, installed_version))
                # 如果原始行有特殊格式（如 [standard]），保留它
                if '[' in original_line:
                    base_name = original_line.split('>')[0].split('<')[0].split('=')[0].strip()
                    results.append(f"{base_name}=={installed_version}")
                else:
                    results.append(f"{package_name}=={installed_version}")
            else:
                status = "❌ 未安裝"
                missing_packages.append(package_name)
                results.append(f"# {original_line}  # 未安裝")
            
            # 格式化輸出
            display_name = original_line.split('#')[0].strip() if '#' in original_line else original_line
            display_name = display_name if display_name else package_name
            
            print(f"{display_name:<30} {installed_version or 'N/A':<15} {version_spec or 'any':<15} {status}")
    
    # 檢查可能遺漏的常用套件
    print("\n" + "=" * 80)
    print("🔍 檢查可能遺漏的套件...\n")
    
    # 建議檢查的額外套件
    suggested_packages = [
        'watchdog',      # 文件監控（ConfigManager 使用）
        'redis',         # Redis 客戶端（如果沒有透過 redis-toolkit 安裝）
        'requests',      # HTTP 請求
        'tqdm',          # 進度條
        'schedule',      # 定時任務
        'reactivex',     # 響應式編程（PyStoreX 依賴）
        'immutables',    # 不可變資料結構（PyStoreX 使用）
        'wave',          # 音訊處理
    ]
    
    missing_suggested = []
    for package in suggested_packages:
        if package not in [p[0] for p in installed_packages]:
            version = get_installed_version(package)
            if version:
                print(f"  💡 {package}=={version} (已安裝但未在 requirements.txt 中)")
                missing_suggested.append(f"{package}=={version}")
            else:
                print(f"  ⚠️  {package} (未安裝)")
    
    # 生成帶版本號的 requirements.txt
    print("\n" + "=" * 80)
    print("📝 生成 requirements_with_versions.txt...")
    
    output_file = Path('requirements_with_versions.txt')
    with open(output_file, 'w', encoding='utf-8') as f:
        # 寫入標題
        f.write("# ASR Hub 依賴套件（含版本號）\n")
        f.write(f"# 生成時間: {subprocess.run(['date'], capture_output=True, text=True).stdout.strip()}\n\n")
        
        # 寫入原始 requirements.txt 的內容（含版本）
        current_section = None
        for line in results:
            # 保持區段註解
            if line.startswith('#') and not line.startswith('# '):
                f.write(f"\n{line}\n")
                current_section = line
            else:
                f.write(f"{line}\n")
        
        # 如果有建議的遺漏套件，添加到最後
        if missing_suggested:
            f.write("\n# 建議添加的套件（已安裝但未在 requirements.txt 中）\n")
            for package in missing_suggested:
                f.write(f"{package}\n")
    
    print(f"✅ 已生成 {output_file}")
    
    # 總結
    print("\n" + "=" * 80)
    print("📊 總結:")
    print(f"  ✅ 已安裝套件: {len(installed_packages)} 個")
    print(f"  ❌ 未安裝套件: {len(missing_packages)} 個")
    print(f"  💡 建議添加: {len(missing_suggested)} 個")
    
    if missing_packages:
        print(f"\n⚠️  以下套件需要安裝:")
        for package in missing_packages:
            print(f"    pip install {package}")
    
    if missing_suggested:
        print(f"\n💡 建議將以下已安裝的套件加入 requirements.txt:")
        for package in missing_suggested:
            print(f"    {package}")

if __name__ == "__main__":
    check_requirements()