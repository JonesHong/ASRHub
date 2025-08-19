"""
音频格式检测工具
提供高级音频格式检测和转换辅助功能
"""

import io
from typing import Optional, Dict, Any, Tuple
from src.audio.models import AudioContainerFormat, AudioSampleFormat, AudioMetadata
from src.utils.logger import logger


class AudioFormatDetector:
    """音频格式检测器"""
    
    @staticmethod
    def detect_format_advanced(data: bytes) -> Dict[str, Any]:
        """
        高级音频格式检测
        
        Args:
            data: 音频数据
            
        Returns:
            检测结果字典，包含格式、编码、是否压缩等信息
        """
        result = {
            'format': AudioContainerFormat.PCM,
            'is_compressed': False,
            'encoding': None,
            'metadata': None,
            'confidence': 0.0
        }
        
        if len(data) < 12:
            result['confidence'] = 0.1
            return result
            
        # WebM/Matroska 格式检测
        if data[:4] == b'\x1a\x45\xdf\xa3':
            result.update({
                'format': AudioContainerFormat.WEBM,
                'is_compressed': True,
                'encoding': 'opus',  # WebM 通常使用 Opus
                'confidence': 0.95
            })
            logger.debug("检测到 WebM/Matroska 格式 (可能包含 Opus)")
            return result
            
        # OGG 格式检测
        if data[:4] == b'OggS':
            result.update({
                'format': AudioContainerFormat.OGG,
                'is_compressed': True,
                'confidence': 0.9
            })
            
            # 检测是否为 Opus
            if b'OpusHead' in data[:100]:
                result['encoding'] = 'opus'
                logger.debug("检测到 OGG Opus 格式")
            else:
                result['encoding'] = 'vorbis'
                logger.debug("检测到 OGG Vorbis 格式")
            return result
            
        # MP3 格式检测
        if (data[:3] == b'ID3' or 
            (len(data) >= 2 and data[:2] in [b'\xff\xfb', b'\xff\xfa'])):
            result.update({
                'format': AudioContainerFormat.MP3,
                'is_compressed': True,
                'encoding': 'mp3',
                'confidence': 0.9
            })
            logger.debug("检测到 MP3 格式")
            return result
            
        # WAV 格式检测
        if data[:4] == b'RIFF' and data[8:12] == b'WAVE':
            result.update({
                'format': AudioContainerFormat.WAV,
                'confidence': 0.95
            })
            
            # 检测 WAV 内部编码
            try:
                if len(data) >= 22:
                    import struct
                    audio_format = struct.unpack('<H', data[20:22])[0]
                    if audio_format == 1:
                        result['is_compressed'] = False
                        result['encoding'] = 'pcm'
                        logger.debug("检测到未压缩 WAV PCM 格式")
                    else:
                        result['is_compressed'] = True
                        result['encoding'] = f'wav_format_{audio_format}'
                        logger.debug(f"检测到压缩 WAV 格式: {audio_format}")
            except Exception as e:
                logger.warning(f"WAV 格式检测详情失败: {e}")
            return result
            
        # M4A/AAC 格式检测
        if len(data) >= 8 and data[4:8] == b'ftyp':
            result.update({
                'format': AudioContainerFormat.M4A,
                'is_compressed': True,
                'encoding': 'aac',
                'confidence': 0.9
            })
            logger.debug("检测到 M4A/AAC 格式")
            return result
            
        # FLAC 格式检测
        if data[:4] == b'fLaC':
            result.update({
                'format': AudioContainerFormat.FLAC,
                'is_compressed': True,
                'encoding': 'flac',
                'confidence': 0.9
            })
            logger.debug("检测到 FLAC 格式")
            return result
            
        # 未知格式的智能推断
        logger.warning("无法通过文件头识别音频格式，尝试智能推断...")
        
        # 基于数据特征的推断
        inferred_format = AudioFormatDetector._infer_format_from_characteristics(data)
        if inferred_format['confidence'] > 0.3:
            logger.info(f"基于特征推断格式: {inferred_format['format']} (confidence: {inferred_format['confidence']})")
            return inferred_format
        
        # 最后假设为 PCM，但标记需要尝试解压缩
        logger.debug("无法识别音频格式，假设为 PCM 但建议尝试解压缩")
        result.update({
            'confidence': 0.3,
            'needs_decompression_attempt': True,  # 新增标记
            'recommended_formats': ['webm', 'ogg']  # 推荐尝试的格式
        })
        return result
    
    @staticmethod
    def _infer_format_from_characteristics(data: bytes) -> Dict[str, Any]:
        """
        基于音频数据特征推断格式
        适用于分块传输后丢失容器头部的情况
        """
        result = {
            'format': AudioContainerFormat.PCM,
            'is_compressed': False,
            'encoding': None,
            'confidence': 0.0
        }
        
        data_size = len(data)
        
        # 特征1: 数据大小分析
        # WebM/Opus 通常较小但包含复杂编码数据
        if data_size < 100000:  # 小于100KB
            # 检查是否有类似压缩数据的特征
            if AudioFormatDetector._has_compressed_audio_patterns(data):
                result.update({
                    'format': AudioContainerFormat.WEBM,
                    'is_compressed': True,
                    'encoding': 'opus',
                    'confidence': 0.6
                })
                logger.info(f"基于压缩特征推断为 WebM/Opus (size: {data_size})")
                return result
        
        # 特征2: 数据分布分析
        # PCM 数据通常有相对均匀的字节分布
        # 压缩数据通常有特定的熵特征
        entropy = AudioFormatDetector._calculate_entropy(data[:4096])  # 只分析前4KB
        logger.debug(f"音频数据熵: {entropy}")
        
        if entropy > 7.0:  # 高熵表明可能是压缩数据
            result.update({
                'format': AudioContainerFormat.WEBM,
                'is_compressed': True,
                'encoding': 'opus',
                'confidence': 0.5
            })
            logger.info(f"基于高熵特征 ({entropy}) 推断为压缩格式")
            return result
        elif entropy < 4.0:  # 低熵可能是 PCM 或静音
            logger.info(f"基于低熵特征 ({entropy}) 推断为 PCM 或静音")
        
        return result
    
    @staticmethod
    def _has_compressed_audio_patterns(data: bytes) -> bool:
        """检查是否有压缩音频的特征模式"""
        if len(data) < 100:
            return False
            
        # 简单的压缩数据特征检查
        # 压缩数据通常有更多的非零字节和复杂模式
        non_zero_count = sum(1 for b in data[:1000] if b != 0)
        zero_runs = 0
        current_run = 0
        
        for b in data[:1000]:
            if b == 0:
                current_run += 1
            else:
                if current_run > 10:  # 长零序列
                    zero_runs += 1
                current_run = 0
        
        # 压缩数据特征：高非零比例，少长零序列
        non_zero_ratio = non_zero_count / min(1000, len(data))
        has_compression_features = non_zero_ratio > 0.8 and zero_runs < 3
        
        logger.debug(f"压缩特征分析: non_zero_ratio={non_zero_ratio}, zero_runs={zero_runs}, has_features={has_compression_features}")
        return has_compression_features
    
    @staticmethod
    def _calculate_entropy(data: bytes) -> float:
        """计算数据的香农熵"""
        if not data:
            return 0.0
            
        # 计算字节频率
        byte_counts = {}
        for byte in data:
            byte_counts[byte] = byte_counts.get(byte, 0) + 1
        
        # 计算熵
        import math
        data_len = len(data)
        entropy = 0.0
        for count in byte_counts.values():
            probability = count / data_len
            if probability > 0:
                entropy -= probability * math.log2(probability)  # 正确的香农熵计算
        
        return entropy
    
    @staticmethod
    def is_format_supported_by_whisper(format_info: Dict[str, Any]) -> bool:
        """
        检查格式是否被 Whisper 直接支持
        
        Args:
            format_info: 格式检测结果
            
        Returns:
            True 如果 Whisper 支持，False 需要转换
        """
        # Whisper 支持的格式
        supported_formats = [
            AudioContainerFormat.WAV,
            AudioContainerFormat.MP3,
            AudioContainerFormat.FLAC,
            AudioContainerFormat.M4A
        ]
        
        # 检查容器格式
        if format_info['format'] not in supported_formats:
            return False
            
        # 对于 WAV，检查是否为未压缩 PCM
        if format_info['format'] == AudioContainerFormat.WAV:
            return format_info.get('encoding') == 'pcm'
            
        return True
    
    @staticmethod
    def needs_decompression(format_info: Dict[str, Any]) -> bool:
        """
        判断是否需要解压缩
        
        Args:
            format_info: 格式检测结果
            
        Returns:
            True 如果需要解压缩
        """
        # WebM/Opus 总是需要解压缩
        if (format_info['format'] == AudioContainerFormat.WEBM and 
            format_info.get('encoding') == 'opus'):
            return True
            
        # OGG Opus 需要解压缩
        if (format_info['format'] == AudioContainerFormat.OGG and 
            format_info.get('encoding') == 'opus'):
            return True
            
        # 智能推断：如果检测器建议尝试解压缩（用于分块传输的音频）
        if format_info.get('needs_decompression_attempt', False):
            logger.info("基于智能推断，建议尝试解压缩处理")
            return True
            
        # 其他压缩格式
        return format_info.get('is_compressed', False)
    
    @staticmethod
    def get_recommended_conversion_params(format_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        根据格式信息推荐转换参数
        
        Args:
            format_info: 格式检测结果
            
        Returns:
            推荐的转换参数
        """
        # 默认参数 - Whisper 最佳兼容性
        params = {
            'sample_rate': 16000,
            'channels': 1,
            'target_format': AudioSampleFormat.FLOAT32,
            'container_format': AudioContainerFormat.PCM
        }
        
        # 根据源格式调整
        if format_info['format'] == AudioContainerFormat.WEBM:
            # WebM/Opus 通常是高质量，可以保持更高采样率后再降采样
            params.update({
                'intermediate_sample_rate': 48000,  # Opus 常用采样率
                'use_high_quality_resampling': True
            })
            
        elif format_info['format'] == AudioContainerFormat.MP3:
            # MP3 可能有各种采样率
            params.update({
                'preserve_quality': True,
                'noise_reduction': False  # MP3 已经有损，不要额外处理
            })
            
        return params


def detect_and_prepare_audio_for_whisper(audio_data: bytes) -> Tuple[bytes, Dict[str, Any]]:
    """
    检测音频格式并准备给 Whisper 使用
    
    Args:
        audio_data: 原始音频数据
        
    Returns:
        (处理后的音频数据, 处理信息)
    """
    from src.audio.converter import AudioConverter
    
    # 检测格式
    format_info = AudioFormatDetector.detect_format_advanced(audio_data)
    
    processing_info = {
        'detected_format': format_info,
        'needs_conversion': False,
        'conversion_steps': [],
        'final_size': len(audio_data)
    }
    
    try:
        # 检查是否需要转换
        if AudioFormatDetector.needs_decompression(format_info):
            logger.info(f"音频需要解压缩: {format_info['format']} ({format_info.get('encoding', 'unknown')})")
            processing_info['needs_conversion'] = True
            processing_info['conversion_steps'].append('decompression')
            
            # 获取推荐参数
            conv_params = AudioFormatDetector.get_recommended_conversion_params(format_info)
            
            # 执行转换
            if (format_info['format'] == AudioContainerFormat.WEBM or 
                format_info.get('needs_decompression_attempt', False)):
                # WebM/Opus 专用转换或智能推断需要尝试的转换
                try:
                    logger.info("尝试 WebM/Opus 格式转换...")
                    audio_data = AudioConverter.convert_webm_to_pcm(
                        audio_data,
                        sample_rate=conv_params['sample_rate'],
                        channels=conv_params['channels']
                    )
                    processing_info['actual_format_used'] = 'webm_opus'
                    logger.info("WebM/Opus 转换成功")
                except Exception as e:
                    logger.warning(f"WebM/Opus 转换失败: {e}")
                    if format_info.get('needs_decompression_attempt', False):
                        # 如果是智能推断，尝试其他格式
                        logger.info("尝试通用音频格式转换...")
                        try:
                            audio_data = AudioConverter.convert_audio_file_to_pcm(
                                audio_data,
                                sample_rate=conv_params['sample_rate'],
                                channels=conv_params['channels'],
                                target_format=AudioSampleFormat.INT16
                            )
                            processing_info['actual_format_used'] = 'generic_conversion'
                            logger.info("通用格式转换成功")
                        except Exception as e2:
                            logger.error(f"所有格式转换都失败: {e2}")
                            raise e  # 抛出原始异常
                    else:
                        raise e  # 非智能推断，直接抛出异常
            else:
                # 通用转换
                audio_data = AudioConverter.convert_audio_file_to_pcm(
                    audio_data,
                    sample_rate=conv_params['sample_rate'],
                    channels=conv_params['channels'],
                    target_format=AudioSampleFormat.INT16  # 先转为 INT16
                )
                processing_info['actual_format_used'] = 'generic_conversion'
                
            processing_info['final_size'] = len(audio_data)
            logger.info(f"音频解压缩完成: {len(audio_data)} bytes")
            
        # 如果不是 Whisper 直接支持的格式，或需要格式标准化
        if (not AudioFormatDetector.is_format_supported_by_whisper(format_info) or
            processing_info['needs_conversion']):
            processing_info['conversion_steps'].append('whisper_preparation')
            # 这里可以添加额外的 Whisper 优化步骤
            
    except Exception as e:
        logger.error(f"音频格式处理失败: {e}")
        processing_info['error'] = str(e)
        raise
        
    return audio_data, processing_info