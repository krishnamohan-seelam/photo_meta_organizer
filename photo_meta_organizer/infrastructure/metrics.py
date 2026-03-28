"""Metrics and Progress Reporting.

This module provides tools for monitoring progress, tracking performance metrics,
and reporting statistics during large indexing jobs.

It uses `tqdm` for real-time progress bars and `collections.Counter` to track
system statistics like error counts and processed formats.
"""

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

logger = logging.getLogger(__name__)


@dataclass
class IndexingStatistics:
    """Statistics collected during an indexing job."""
    
    total_files_discovered: int = 0
    total_files_processed: int = 0
    total_errors: int = 0
    total_size_bytes: int = 0
    
    # Track file formats and MIME types
    mime_type_counts: Counter = field(default_factory=Counter)
    error_types: Counter = field(default_factory=Counter)
    
    # Benchmark stats
    start_time: float = 0.0
    end_time: float = 0.0
    
    @property
    def duration_seconds(self) -> float:
        """Total time taken in seconds."""
        if self.end_time > 0 and self.start_time > 0:
            return self.end_time - self.start_time
        return 0.0

    @property
    def throughput_images_per_minute(self) -> float:
        """Average images processed per minute."""
        minutes = self.duration_seconds / 60.0
        if minutes > 0:
            return self.total_files_processed / minutes
        return 0.0


class ProgressReporter:
    """Provides real-time feedback and metrics tracking during indexing.
    
    If `tqdm` is installed, it displays a progress bar on the console.
    Otherwise, it logs progress periodically to standard logging.
    """
    
    def __init__(self, total_files: Optional[int] = None, disable_bar: bool = False) -> None:
        """Initialize progress reporting.
        
        Args:
            total_files: Expected number of files to process (for ETA calculation).
            disable_bar: If True, do not show the tqdm progress bar even if installed.
        """
        self.stats = IndexingStatistics()
        self._pbar: Optional[Any] = None
        self._disable_bar = disable_bar
        
        if total_files:
            self.stats.total_files_discovered = total_files
            
    def start(self, total: Optional[int] = None, desc: str = "Indexing Photos") -> None:
        """Start the progress tracker."""
        import time
        self.stats.start_time = time.time()
        
        if total is not None:
            self.stats.total_files_discovered = total
            
        use_bar = tqdm is not None and not self._disable_bar
        if use_bar:
            self._pbar = tqdm(
                total=self.stats.total_files_discovered,
                desc=desc,
                unit="img",
                dynamic_ncols=True,
                smoothing=0.1
            )
        else:
            logger.info("Starting task '%s' (Total items: %s)", desc, self.stats.total_files_discovered)
            
    def update(self, n: int = 1, metadata: Optional[Any] = None) -> None:
        """Report progress of a chunk of processing.
        
        Args:
            n: Number of items processed since last update.
            metadata: ImageMetadata object (if successful) to track stats.
        """
        self.stats.total_files_processed += n
        
        if metadata is not None:
            try:
                # Assuming ImageMetadata structure from Phase 1
                if hasattr(metadata, 'file_info'):
                    self.stats.total_size_bytes += getattr(metadata.file_info, 'size_bytes', 0)
                    mime = getattr(metadata.file_info, 'mime_type', 'unknown')
                    self.stats.mime_type_counts[mime] += 1
            except Exception as e:
                logger.debug("Failed to track metrics for metadata: %s", e)
                
        if self._pbar is not None:
            self._pbar.update(n)
        elif self.stats.total_files_processed % 100 == 0:
            # Fallback progress logging
            logger.info("Processed %d / %s files", 
                        self.stats.total_files_processed, 
                        self.stats.total_files_discovered or '?')
            
    def record_error(self, error_type: str = "unknown") -> None:
        """Track an error during processing."""
        self.stats.total_errors += 1
        self.stats.error_types[error_type] += 1
        
        if self._pbar is not None:
            self._pbar.set_postfix_str(f"Errors: {self.stats.total_errors}", refresh=False)
            
    def stop(self) -> IndexingStatistics:
        """Stop tracking and finalize statistics."""
        import time
        self.stats.end_time = time.time()
        
        if self._pbar is not None:
            self._pbar.close()
            
        logger.info("Task completed. Throughput: %.2f imgs/min", self.stats.throughput_images_per_minute)
        return self.stats
