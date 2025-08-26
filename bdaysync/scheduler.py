"""
Scheduling service for periodic sync operations
"""

import time
import signal
import logging
from datetime import datetime, timedelta
from croniter import croniter
from config import get_scheduler_config

logger = logging.getLogger(__name__)

class SchedulerService:
    """Service to handle scheduling sync operations"""
    
    def __init__(self, sync_func, diagnostic_func):
        self.sync_func = sync_func
        self.diagnostic_func = diagnostic_func
        self.running = True
        
        # Load scheduler configuration
        config = get_scheduler_config()
        self.sync_schedule = config['sync_schedule']
        self.diagnostic_schedule = config['diagnostic_schedule']
        self.sync_interval_hours = config['sync_interval_hours']
        self.startup_delay = config['startup_delay']
        
        self.last_sync = None
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
    
    def _next_sync_time(self, schedule):
        """Calculate next sync time based on cron schedule"""
        try:
            cron = croniter(schedule, datetime.now())
            return cron.get_next(datetime)
        except Exception as e:
            logger.error(f"Invalid cron schedule '{schedule}': {e}")
            # Fallback to hourly
            return datetime.now() + timedelta(hours=1)
    
    def _should_sync_interval(self):
        """Check if we should sync based on interval"""
        if self.sync_interval_hours <= 0:
            return False
        if self.last_sync is None:
            return True
        return datetime.now() - self.last_sync >= timedelta(hours=self.sync_interval_hours)
    
    def _should_sync_cron(self, schedule):
        """Check if we should sync based on cron schedule"""
        try:
            cron = croniter(schedule, datetime.now() - timedelta(minutes=1))
            next_time = cron.get_next(datetime)
            return next_time <= datetime.now()
        except:
            return False
    
    def _perform_sync(self, diagnostic=False):
        """Perform the actual sync operation"""
        try:
            logger.info(f"Starting {'diagnostic' if diagnostic else 'sync'} operation...")
            
            if diagnostic:
                # Run diagnostic
                success = self.diagnostic_func()
            else:
                # Run main sync
                success = self.sync_func()
                if success:
                    self.last_sync = datetime.now()
            
            if success:
                logger.info(f"{'Diagnostic' if diagnostic else 'Sync'} operation completed successfully")
            else:
                logger.warning(f"{'Diagnostic' if diagnostic else 'Sync'} operation completed with errors")
                
            return success
        except Exception as e:
            logger.error(f"{'Diagnostic' if diagnostic else 'Sync'} operation failed: {e}")
            return False
    
    def _wait_with_interrupt_check(self, seconds):
        """Wait for specified seconds while checking for interrupts"""
        end_time = time.time() + seconds
        while time.time() < end_time and self.running:
            time.sleep(min(1, end_time - time.time()))
    
    def _get_next_schedule_info(self):
        """Get information about the next scheduled events"""
        try:
            sync_next = self._next_sync_time(self.sync_schedule)
            diag_next = self._next_sync_time(self.diagnostic_schedule)
            
            return {
                'sync_next': sync_next,
                'diagnostic_next': diag_next,
                'sync_schedule': self.sync_schedule,
                'diagnostic_schedule': self.diagnostic_schedule
            }
        except:
            return None
    
    def run_daemon(self):
        """Run as daemon with scheduled syncs"""
        logger.info("Starting birthday sync daemon...")
        logger.info(f"Sync schedule: {self.sync_schedule}")
        logger.info(f"Diagnostic schedule: {self.diagnostic_schedule}")
        
        if self.sync_interval_hours > 0:
            logger.info(f"Sync interval: every {self.sync_interval_hours} hours")
        
        # Show next scheduled times
        schedule_info = self._get_next_schedule_info()
        if schedule_info:
            logger.info(f"Next sync: {schedule_info['sync_next'].strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"Next diagnostic: {schedule_info['diagnostic_next'].strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Initial startup delay
        if self.startup_delay > 0:
            logger.info(f"Waiting {self.startup_delay} seconds before starting...")
            self._wait_with_interrupt_check(self.startup_delay)
        
        if not self.running:
            logger.info("Shutdown requested during startup delay")
            return
        
        # Run initial sync
        logger.info("Running initial sync...")
        self._perform_sync()
        
        # Main scheduling loop
        loop_count = 0
        while self.running:
            try:
                loop_count += 1
                
                # Check if it's time for a sync
                sync_needed = False
                diagnostic_needed = False
                
                if self.sync_interval_hours > 0:
                    sync_needed = self._should_sync_interval()
                else:
                    sync_needed = self._should_sync_cron(self.sync_schedule)
                
                diagnostic_needed = self._should_sync_cron(self.diagnostic_schedule)
                
                if diagnostic_needed:
                    self._perform_sync(diagnostic=True)
                elif sync_needed:
                    self._perform_sync()
                
                # Log status every 60 loops (60 minutes) to show we're alive
                if loop_count % 60 == 0:
                    logger.info("Scheduler daemon running - waiting for next scheduled operation")
                    schedule_info = self._get_next_schedule_info()
                    if schedule_info:
                        logger.info(f"Next sync: {schedule_info['sync_next'].strftime('%Y-%m-%d %H:%M:%S')}")
                
                # Sleep for a minute before next check
                self._wait_with_interrupt_check(60)
                
            except Exception as e:
                logger.error(f"Error in scheduling loop: {e}")
                self._wait_with_interrupt_check(60)
        
        logger.info("Scheduler daemon stopped")
    
    def run_once(self):
        """Run sync once and exit"""
        logger.info("Running single sync operation...")
        success = self._perform_sync()
        return 0 if success else 1
