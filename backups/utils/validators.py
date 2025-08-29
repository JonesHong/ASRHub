"""
ASR Hub Validators
資料驗證相關的工具函式
"""

import re
from typing import Any, Dict, List, Optional, Tuple, Union
from src.core.exceptions import ValidationError


def validate_audio_format(
    sample_rate: int,
    channels: int,
    encoding: str,
    raise_on_error: bool = True
) -> Tuple[bool, Optional[str]]:
    """
    驗證音訊格式參數
    
    Args:
        sample_rate: 取樣率
        channels: 聲道數
        encoding: 編碼格式
        raise_on_error: 是否在錯誤時拋出異常
        
    Returns:
        (是否有效, 錯誤訊息)
        
    Raises:
        ValidationError: 如果 raise_on_error=True 且驗證失敗
    """
    # 驗證取樣率
    valid_sample_rates = [8000, 16000, 22050, 44100, 48000]
    if sample_rate not in valid_sample_rates:
        error_msg = f"無效的取樣率：{sample_rate}。支援的取樣率：{valid_sample_rates}"
        if raise_on_error:
            raise ValidationError(error_msg)
        return False, error_msg
    
    # 驗證聲道數
    if channels < 1 or channels > 8:
        error_msg = f"無效的聲道數：{channels}。必須在 1-8 之間"
        if raise_on_error:
            raise ValidationError(error_msg)
        return False, error_msg
    
    # 驗證編碼格式
    valid_encodings = ["linear16", "linear32", "float32", "mulaw", "alaw"]
    if encoding not in valid_encodings:
        error_msg = f"無效的編碼格式：{encoding}。支援的格式：{valid_encodings}"
        if raise_on_error:
            raise ValidationError(error_msg)
        return False, error_msg
    
    return True, None


def validate_language_code(
    language: str,
    raise_on_error: bool = True
) -> Tuple[bool, Optional[str]]:
    """
    驗證語言代碼
    
    Args:
        language: 語言代碼
        raise_on_error: 是否在錯誤時拋出異常
        
    Returns:
        (是否有效, 錯誤訊息)
        
    Raises:
        ValidationError: 如果 raise_on_error=True 且驗證失敗
    """
    # 支援的語言列表
    supported_languages = [
        "auto",  # 自動偵測
        "zh", "zh-CN", "zh-TW", "zh-HK",  # 中文
        "en", "en-US", "en-GB", "en-AU",  # 英文
        "ja", "ko", "es", "fr", "de",     # 其他常用語言
        "ru", "ar", "hi", "pt", "it",
        "tr", "pl", "nl", "sv", "id",
        "th", "vi", "ms"
    ]
    
    if language not in supported_languages:
        error_msg = f"不支援的語言代碼：{language}"
        if raise_on_error:
            raise ValidationError(error_msg)
        return False, error_msg
    
    return True, None


def validate_session_id(
    session_id: str,
    raise_on_error: bool = True
) -> Tuple[bool, Optional[str]]:
    """
    驗證 Session ID 格式
    
    Args:
        session_id: Session ID
        raise_on_error: 是否在錯誤時拋出異常
        
    Returns:
        (是否有效, 錯誤訊息)
        
    Raises:
        ValidationError: 如果 raise_on_error=True 且驗證失敗
    """
    if not session_id:
        error_msg = "Session ID 不能為空"
        if raise_on_error:
            raise ValidationError(error_msg)
        return False, error_msg
    
    # 檢查長度
    if len(session_id) < 8 or len(session_id) > 64:
        error_msg = f"Session ID 長度必須在 8-64 個字元之間，目前長度：{len(session_id)}"
        if raise_on_error:
            raise ValidationError(error_msg)
        return False, error_msg
    
    # 檢查字元格式（只允許字母、數字、底線、橫線）
    pattern = r'^[a-zA-Z0-9_-]+$'
    if not re.match(pattern, session_id):
        error_msg = "Session ID 只能包含字母、數字、底線和橫線"
        if raise_on_error:
            raise ValidationError(error_msg)
        return False, error_msg
    
    return True, None


def validate_config_schema(
    config: Dict[str, Any],
    schema: Dict[str, Any],
    raise_on_error: bool = True
) -> Tuple[bool, List[str]]:
    """
    驗證配置結構
    
    Args:
        config: 要驗證的配置
        schema: 預期的結構定義
        raise_on_error: 是否在錯誤時拋出異常
        
    Returns:
        (是否有效, 錯誤訊息列表)
        
    Raises:
        ValidationError: 如果 raise_on_error=True 且驗證失敗
    """
    errors = []
    
    def _validate_field(
        value: Any,
        field_schema: Dict[str, Any],
        field_path: str
    ):
        """驗證單個欄位"""
        # 檢查類型
        expected_type = field_schema.get("type")
        if expected_type:
            if expected_type == "int" and not isinstance(value, int):
                errors.append(f"{field_path} 必須是整數")
            elif expected_type == "float" and not isinstance(value, (int, float)):
                errors.append(f"{field_path} 必須是數字")
            elif expected_type == "str" and not isinstance(value, str):
                errors.append(f"{field_path} 必須是字串")
            elif expected_type == "bool" and not isinstance(value, bool):
                errors.append(f"{field_path} 必須是布林值")
            elif expected_type == "dict" and not isinstance(value, dict):
                errors.append(f"{field_path} 必須是字典")
            elif expected_type == "list" and not isinstance(value, list):
                errors.append(f"{field_path} 必須是列表")
        
        # 檢查範圍
        if "min" in field_schema and isinstance(value, (int, float)):
            if value < field_schema["min"]:
                errors.append(f"{field_path} 不能小於 {field_schema['min']}")
        
        if "max" in field_schema and isinstance(value, (int, float)):
            if value > field_schema["max"]:
                errors.append(f"{field_path} 不能大於 {field_schema['max']}")
        
        # 檢查選項
        if "enum" in field_schema:
            if value not in field_schema["enum"]:
                errors.append(
                    f"{field_path} 必須是以下值之一：{field_schema['enum']}"
                )
        
        # 檢查正則表達式
        if "pattern" in field_schema and isinstance(value, str):
            if not re.match(field_schema["pattern"], value):
                errors.append(f"{field_path} 格式不正確")
    
    def _validate_object(
        obj: Dict[str, Any],
        obj_schema: Dict[str, Any],
        path: str = ""
    ):
        """遞迴驗證物件"""
        # 檢查必需欄位
        required_fields = obj_schema.get("required", [])
        for field in required_fields:
            if field not in obj:
                errors.append(f"{path}.{field} 是必需欄位" if path else f"{field} 是必需欄位")
        
        # 驗證每個欄位
        properties = obj_schema.get("properties", {})
        for field, value in obj.items():
            field_path = f"{path}.{field}" if path else field
            
            if field in properties:
                field_schema = properties[field]
                
                # 如果是物件，遞迴驗證
                if field_schema.get("type") == "dict" and isinstance(value, dict):
                    _validate_object(value, field_schema, field_path)
                else:
                    _validate_field(value, field_schema, field_path)
    
    # 開始驗證
    _validate_object(config, schema)
    
    if errors and raise_on_error:
        raise ValidationError(f"配置驗證失敗：{'; '.join(errors)}")
    
    return len(errors) == 0, errors


def validate_file_size(
    size: int,
    max_size: int = 100 * 1024 * 1024,  # 預設 100MB
    raise_on_error: bool = True
) -> Tuple[bool, Optional[str]]:
    """
    驗證檔案大小
    
    Args:
        size: 檔案大小（位元組）
        max_size: 最大允許大小（位元組）
        raise_on_error: 是否在錯誤時拋出異常
        
    Returns:
        (是否有效, 錯誤訊息)
        
    Raises:
        ValidationError: 如果 raise_on_error=True 且驗證失敗
    """
    if size <= 0:
        error_msg = "檔案大小必須大於 0"
        if raise_on_error:
            raise ValidationError(error_msg)
        return False, error_msg
    
    if size > max_size:
        error_msg = (
            f"檔案大小超過限制。"
            f"檔案大小：{size / 1024 / 1024:.2f}MB，"
            f"限制：{max_size / 1024 / 1024:.2f}MB"
        )
        if raise_on_error:
            raise ValidationError(error_msg)
        return False, error_msg
    
    return True, None


def validate_url(
    url: str,
    allowed_schemes: Optional[List[str]] = None,
    raise_on_error: bool = True
) -> Tuple[bool, Optional[str]]:
    """
    驗證 URL 格式
    
    Args:
        url: URL 字串
        allowed_schemes: 允許的協議列表（預設 ["http", "https"]）
        raise_on_error: 是否在錯誤時拋出異常
        
    Returns:
        (是否有效, 錯誤訊息)
        
    Raises:
        ValidationError: 如果 raise_on_error=True 且驗證失敗
    """
    if allowed_schemes is None:
        allowed_schemes = ["http", "https"]
    
    # 基本 URL 格式檢查
    url_pattern = re.compile(
        r'^(?:(' + '|'.join(allowed_schemes) + r')://)'  # 協議
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # 域名
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
        r'(?::\d+)?'  # 端口
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    if not url_pattern.match(url):
        error_msg = f"無效的 URL 格式：{url}"
        if raise_on_error:
            raise ValidationError(error_msg)
        return False, error_msg
    
    return True, None


def validate_timestamp(
    timestamp: Union[int, float],
    min_timestamp: Optional[Union[int, float]] = None,
    max_timestamp: Optional[Union[int, float]] = None,
    raise_on_error: bool = True
) -> Tuple[bool, Optional[str]]:
    """
    驗證時間戳記
    
    Args:
        timestamp: 時間戳記（秒）
        min_timestamp: 最小允許值
        max_timestamp: 最大允許值
        raise_on_error: 是否在錯誤時拋出異常
        
    Returns:
        (是否有效, 錯誤訊息)
        
    Raises:
        ValidationError: 如果 raise_on_error=True 且驗證失敗
    """
    if not isinstance(timestamp, (int, float)):
        error_msg = "時間戳記必須是數字"
        if raise_on_error:
            raise ValidationError(error_msg)
        return False, error_msg
    
    if timestamp < 0:
        error_msg = "時間戳記不能為負數"
        if raise_on_error:
            raise ValidationError(error_msg)
        return False, error_msg
    
    if min_timestamp is not None and timestamp < min_timestamp:
        error_msg = f"時間戳記不能小於 {min_timestamp}"
        if raise_on_error:
            raise ValidationError(error_msg)
        return False, error_msg
    
    if max_timestamp is not None and timestamp > max_timestamp:
        error_msg = f"時間戳記不能大於 {max_timestamp}"
        if raise_on_error:
            raise ValidationError(error_msg)
        return False, error_msg
    
    return True, None


def sanitize_string(
    text: str,
    max_length: Optional[int] = None,
    allowed_chars: Optional[str] = None
) -> str:
    """
    清理和驗證字串
    
    Args:
        text: 要清理的字串
        max_length: 最大長度
        allowed_chars: 允許的字元正則表達式
        
    Returns:
        清理後的字串
    """
    # 移除前後空白
    text = text.strip()
    
    # 限制長度
    if max_length and len(text) > max_length:
        text = text[:max_length]
    
    # 過濾字元
    if allowed_chars:
        pattern = re.compile(f'[^{allowed_chars}]')
        text = pattern.sub('', text)
    
    return text


def validate_json_structure(
    data: Dict[str, Any],
    required_fields: List[str],
    raise_on_error: bool = True
) -> Tuple[bool, List[str]]:
    """
    驗證 JSON 資料結構
    
    Args:
        data: JSON 資料
        required_fields: 必需欄位列表
        raise_on_error: 是否在錯誤時拋出異常
        
    Returns:
        (是否有效, 缺少的欄位列表)
        
    Raises:
        ValidationError: 如果 raise_on_error=True 且驗證失敗
    """
    missing_fields = []
    
    for field in required_fields:
        # 支援巢狀欄位檢查（使用點符號）
        parts = field.split('.')
        current = data
        
        for i, part in enumerate(parts):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                missing_fields.append(field)
                break
    
    if missing_fields and raise_on_error:
        raise ValidationError(f"缺少必需欄位：{', '.join(missing_fields)}")
    
    return len(missing_fields) == 0, missing_fields