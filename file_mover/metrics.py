import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class FileOperationMetric:
    """Represents a single file operation metric"""
    timestamp: str
    filename: str
    file_size_bytes: int
    operation_duration_seconds: float
    success: bool
    error_message: Optional[str] = None


@dataclass
class SystemMetrics:
    """System-level metrics"""
    timestamp: str
    cpu_percent: float
    memory_percent: float
    disk_free_gb: float
    concurrent_operations: int


class MetricsCollector:
    """Collects and manages application metrics"""
    
    def __init__(self, metrics_file: Path = None):
        self.metrics_file = metrics_file or Path("file_mover_metrics.json")
        self.file_operations: List[FileOperationMetric] = []
        self.system_metrics: List[SystemMetrics] = []
        self.max_metrics_age_days = 30
        
    def record_file_operation(
        self, 
        filename: str, 
        file_size_bytes: int, 
        duration_seconds: float, 
        success: bool,
        error_message: Optional[str] = None
    ):
        """Record a file operation metric"""
        metric = FileOperationMetric(
            timestamp=datetime.now().isoformat(),
            filename=filename,
            file_size_bytes=file_size_bytes,
            operation_duration_seconds=duration_seconds,
            success=success,
            error_message=error_message
        )
        self.file_operations.append(metric)
        self._cleanup_old_metrics()
        
    def record_system_metrics(self, cpu_percent: float, memory_percent: float, 
                            disk_free_gb: float, concurrent_operations: int):
        """Record system metrics"""
        metric = SystemMetrics(
            timestamp=datetime.now().isoformat(),
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            disk_free_gb=disk_free_gb,
            concurrent_operations=concurrent_operations
        )
        self.system_metrics.append(metric)
        
    def _cleanup_old_metrics(self):
        """Remove metrics older than max_metrics_age_days"""
        cutoff_date = datetime.now() - timedelta(days=self.max_metrics_age_days)
        cutoff_iso = cutoff_date.isoformat()
        
        self.file_operations = [
            m for m in self.file_operations 
            if m.timestamp >= cutoff_iso
        ]
        self.system_metrics = [
            m for m in self.system_metrics 
            if m.timestamp >= cutoff_iso
        ]
        
    def get_performance_summary(self, hours: int = 24) -> Dict:
        """Get performance summary for the last N hours"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        cutoff_iso = cutoff_time.isoformat()
        
        recent_ops = [op for op in self.file_operations if op.timestamp >= cutoff_iso]
        
        if not recent_ops:
            return {"error": "No operations in the specified time period"}
            
        successful_ops = [op for op in recent_ops if op.success]
        failed_ops = [op for op in recent_ops if not op.success]
        
        total_bytes = sum(op.file_size_bytes for op in successful_ops)
        total_duration = sum(op.operation_duration_seconds for op in successful_ops)
        
        avg_speed_mbps = 0
        if total_duration > 0:
            avg_speed_mbps = (total_bytes / (1024 * 1024)) / total_duration
            
        return {
            "time_period_hours": hours,
            "total_operations": len(recent_ops),
            "successful_operations": len(successful_ops),
            "failed_operations": len(failed_ops),
            "success_rate_percent": (len(successful_ops) / len(recent_ops)) * 100,
            "total_bytes_processed": total_bytes,
            "total_mb_processed": total_bytes / (1024 * 1024),
            "average_speed_mbps": avg_speed_mbps,
            "average_operation_duration": total_duration / len(successful_ops) if successful_ops else 0
        }
        
    def save_metrics(self):
        """Save metrics to file"""
        try:
            data = {
                "file_operations": [asdict(op) for op in self.file_operations],
                "system_metrics": [asdict(sm) for sm in self.system_metrics],
                "last_updated": datetime.now().isoformat()
            }
            with self.metrics_file.open('w') as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Metrics saved to {self.metrics_file}")
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")
            
    def load_metrics(self):
        """Load metrics from file"""
        try:
            if not self.metrics_file.exists():
                return
                
            with self.metrics_file.open('r') as f:
                data = json.load(f)
                
            self.file_operations = [
                FileOperationMetric(**op) for op in data.get("file_operations", [])
            ]
            self.system_metrics = [
                SystemMetrics(**sm) for sm in data.get("system_metrics", [])
            ]
            logger.info(f"Loaded {len(self.file_operations)} file operations and "
                       f"{len(self.system_metrics)} system metrics from {self.metrics_file}")
        except Exception as e:
            logger.error(f"Failed to load metrics: {e}") 