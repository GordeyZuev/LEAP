"""Audio compression and processing"""

import asyncio
from pathlib import Path

from logger import get_logger

logger = get_logger()


class AudioCompressor:
    """Audio compression and file splitting"""

    def __init__(
        self,
        target_bitrate: str = "64k",
        target_sample_rate: int = 16000,
        max_file_size_mb: int = 25,
    ):
        self.target_bitrate = target_bitrate
        self.target_sample_rate = target_sample_rate
        self.max_file_size_mb = max_file_size_mb
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024

    async def compress_audio(self, input_path: str, output_path: str | None = None) -> str:
        """
        Compress audio file.

        Args:
            input_path: Path to original audio file
            output_path: Path to save compressed file (if None, it is created automatically)

        Returns:
            Path to compressed file
        """
        if not Path(input_path).exists():
            raise FileNotFoundError(f"Audio file not found: {input_path}")

        # Check size of original file
        file_size = Path(input_path).stat().st_size
        file_size_mb = file_size / (1024 * 1024)

        logger.info(f"Original file: size={file_size_mb:.2f}MB", size_mb=file_size_mb)

        # If file is already smaller than limit, we can return original path
        # But it is better to compress to optimal parameters anyway
        if file_size <= self.max_file_size_bytes and file_size_mb < 10:
            logger.info("File is already small, but we compress it for optimization")

        # Define path for output file
        if output_path is None:
            input_path_obj = Path(input_path)
            output_path = str(input_path_obj.parent / f"{input_path_obj.stem}_compressed.mp3")

        # Create directory if needed
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # FFmpeg command for compression
        cmd = [
            "ffmpeg",
            "-i",
            input_path,
            "-vn",  # Without video
            "-acodec",
            "libmp3lame",  # MP3 codec
            "-ab",
            self.target_bitrate,  # Bitrate
            "-ar",
            str(self.target_sample_rate),  # Sample rate
            "-ac",
            "1",  # Mono (enough for speech)
            "-y",  # Overwrite file if it exists
            output_path,
        ]

        try:
            logger.info(f"Compressing audio: path={input_path}", path=input_path)
            logger.info(
                f"Parameters: bitrate={self.target_bitrate} | freq={self.target_sample_rate}Hz | channels=mono",
                bitrate=self.target_bitrate,
                sample_rate=self.target_sample_rate,
                channels=1
            )

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            _stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                raise RuntimeError(f"Error compressing audio: {error_msg}")

            if not Path(output_path).exists():
                raise RuntimeError(f"Compressed file was not created: {output_path}")

            # Check size of compressed file
            compressed_size = Path(output_path).stat().st_size
            compressed_size_mb = compressed_size / (1024 * 1024)

            logger.info(f"Audio compressed: size={compressed_size_mb:.2f}MB", size_mb=compressed_size_mb)

            if compressed_size > self.max_file_size_bytes:
                logger.warning(
                    f"Compressed file exceeds limit: size={compressed_size_mb:.2f}MB | limit={self.max_file_size_mb}MB",
                    size_mb=compressed_size_mb,
                    limit_mb=self.max_file_size_mb
                )
                # We can try to compress more, but for now let's leave it as is

            return output_path

        except Exception as e:
            logger.error(f"Error compressing audio: error={e}", error=str(e))
            raise

    async def get_audio_info(self, audio_path: str) -> dict:
        """Get audio file information"""
        import json

        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            audio_path,
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                raise RuntimeError(f"Error getting audio information: {stderr.decode()}")

            info = json.loads(stdout.decode())
            audio_stream = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)

            if not audio_stream:
                raise RuntimeError("Audio stream not found")

            return {
                "duration": float(info["format"]["duration"]),
                "size": int(info["format"]["size"]),
                "bitrate": int(info["format"].get("bit_rate", 0)),
                "sample_rate": int(audio_stream.get("sample_rate", 0)),
                "channels": int(audio_stream.get("channels", 0)),
                "codec": audio_stream.get("codec_name", "unknown"),
            }

        except Exception as e:
            logger.error(f"Error getting audio info: error={e}", error=str(e))
            raise

    async def split_audio(self, audio_path: str, max_size_mb: float = 20.0, output_dir: str | None = None) -> list[str]:
        """
        Split audio file into parts if it is too large.

        Args:
            audio_path: Path to audio file
            max_size_mb: Maximum size of one part in MB
            output_dir: Directory to save parts (if None, the same directory is used)

        Returns:
            List of paths to parts of the file
        """
        if not Path(audio_path).exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Get audio information
        audio_info = await self.get_audio_info(audio_path)
        duration = audio_info["duration"]
        file_size_mb = Path(audio_path).stat().st_size / (1024 * 1024)

        logger.info(
            f"Splitting audio: size={file_size_mb:.2f}MB | duration={duration:.1f}s",
            size_mb=file_size_mb,
            duration_sec=duration
        )

        # Если файл уже достаточно мал, возвращаем его как есть
        if file_size_mb <= max_size_mb:
            logger.info("File doesn't need splitting")
            return [audio_path]

        # Вычисляем количество частей
        # Оцениваем размер одной секунды аудио
        size_per_second = file_size_mb / duration
        # Вычисляем длительность одной части
        # (без дополнительного запаса, т.к. max_size_mb уже с запасом)
        duration_per_part = max_size_mb / size_per_second

        # Вычисляем минимальное количество частей
        num_parts = int(duration / duration_per_part)
        if num_parts * duration_per_part < duration:
            num_parts += 1

        actual_duration_per_part = duration / num_parts
        estimated_size_per_part = actual_duration_per_part * size_per_second

        logger.info(
            f"Splitting into parts: count={num_parts} | duration_per_part={actual_duration_per_part:.1f}s | size_per_part={estimated_size_per_part:.1f}MB",
            parts=num_parts,
            duration_per_part=actual_duration_per_part,
            size_per_part=estimated_size_per_part
        )

        # Определяем директорию для частей
        if output_dir is None:
            output_dir = Path(audio_path).parent
        else:
            Path(output_dir).mkdir(parents=True, exist_ok=True)

        input_path_obj = Path(audio_path)

        # Асинхронная функция для создания одной части
        async def create_part(i: int) -> str:
            """Создание одной части аудио"""
            start_time = i * actual_duration_per_part
            part_duration = actual_duration_per_part

            # Для последней части берем оставшееся время
            if i == num_parts - 1:
                part_duration = duration - start_time

            part_filename = f"{input_path_obj.stem}_part_{i + 1:03d}.mp3"
            part_path = Path(output_dir) / part_filename

            cmd = [
                "ffmpeg",
                "-i",
                audio_path,
                "-ss",
                str(start_time),
                "-t",
                str(part_duration),
                "-vn",
                "-acodec",
                "libmp3lame",
                "-ab",
                self.target_bitrate,
                "-ar",
                str(self.target_sample_rate),
                "-ac",
                "1",
                "-y",
                part_path,
            ]

            try:
                end_time = start_time + part_duration
                logger.info(
                    f"Creating part: number={i + 1}/{num_parts} | time={start_time:.1f}s-{end_time:.1f}s",
                    part=i + 1,
                    total_parts=num_parts,
                    start=start_time,
                    end=end_time
                )

                process = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )

                _stdout, stderr = await process.communicate()

                if process.returncode != 0:
                    error_msg = stderr.decode() if stderr else "Неизвестная ошибка"
                    raise RuntimeError(f"Ошибка создания части {i + 1}: {error_msg}")

                if not Path(part_path).exists():
                    raise RuntimeError(f"Часть {i + 1} не была создана: {part_path}")

                part_size_mb = Path(part_path).stat().st_size / (1024 * 1024)

                # Проверяем, что часть не превышает лимит
                if part_size_mb > self.max_file_size_mb:
                    error_msg = (
                        f"Часть {i + 1}/{num_parts} превышает лимит: "
                        f"{part_size_mb:.2f} МБ > {self.max_file_size_mb} МБ. "
                        f"Попробуйте уменьшить max_size_mb в конфигурации."
                    )
                    logger.error(
                        f"Part exceeds limit: part={i + 1}/{num_parts} | size={part_size_mb:.2f}MB | limit={self.max_file_size_mb}MB",
                        part=i + 1,
                        total_parts=num_parts,
                        size_mb=part_size_mb,
                        limit_mb=self.max_file_size_mb
                    )
                    raise ValueError(error_msg)
                if part_size_mb > self.max_file_size_mb * 0.95:
                    logger.warning(
                        f"Part close to limit: part={i + 1}/{num_parts} | size={part_size_mb:.2f}MB | limit={self.max_file_size_mb}MB",
                        part=i + 1,
                        total_parts=num_parts,
                        size_mb=part_size_mb,
                        limit_mb=self.max_file_size_mb
                    )

                logger.info(
                    f"Part created: number={i + 1}/{num_parts} | size={part_size_mb:.2f}MB",
                    part=i + 1,
                    total_parts=num_parts,
                    size_mb=part_size_mb
                )
                return part_path

            except Exception as e:
                logger.error(
                    f"Error creating part: part={i + 1} | error={e}",
                    part=i + 1,
                    error=str(e)
                )
                raise

        # Создаем все части параллельно
        logger.info(f"Creating parts in parallel: count={num_parts}", parts=num_parts)
        part_tasks = [create_part(i) for i in range(num_parts)]
        part_results = await asyncio.gather(*part_tasks, return_exceptions=True)

        # Проверяем результаты
        parts = []
        errors = []

        for i, result in enumerate(part_results):
            if isinstance(result, Exception):
                errors.append((i + 1, result))
            else:
                parts.append(result)

        # Если были ошибки, удаляем созданные части и выбрасываем исключение
        if errors:
            logger.error(
                f"Errors creating parts: failed={len(errors)} | total={num_parts}",
                failed=len(errors),
                total=num_parts
            )
            # Удаляем все созданные части
            for part in parts:
                try:
                    Path(part).unlink()
                except Exception as e:
                    logger.warning(f"Ignored exception: {e}")
            # Выбрасываем первую ошибку
            raise RuntimeError(f"Ошибки при создании частей: {errors[0][1]}") from errors[0][1]

        # Сортируем части по номеру (на случай, если порядок нарушен)
        parts.sort()

        logger.info(f"Audio split completed: parts={len(parts)} | mode=parallel", parts=len(parts))
        return parts
