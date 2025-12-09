/**
 * Polling utilities for tracking job progress
 */

/**
 * Poll a job status endpoint until completion
 *
 * @param endpoint - API endpoint to poll
 * @param onProgress - Callback function called with each progress update
 * @param options - Configuration options for polling
 * @returns Promise that resolves with final job data when complete
 */
export async function pollJobStatus<T>(
  endpoint: string,
  onProgress: (data: T) => void,
  options: {
    interval?: number;  // ms between polls (default: 2500)
    timeout?: number;   // max time to poll in ms (default: 300000 = 5 min)
  } = {}
): Promise<T> {
  const { interval = 2500, timeout = 300000 } = options;
  const startTime = Date.now();

  return new Promise((resolve, reject) => {
    const poll = async () => {
      try {
        // Check timeout
        if (Date.now() - startTime > timeout) {
          reject(new Error('Job polling timeout'));
          return;
        }

        const response = await fetch(endpoint);
        if (!response.ok) {
          throw new Error(`Failed to fetch job status: ${response.status}`);
        }

        const data: T = await response.json();
        onProgress(data);

        // Check if job is complete
        const status = (data as any).status;
        if (status === 'completed' || status === 'failed' || status === 'cancelled') {
          resolve(data);
          return;
        }

        // Continue polling
        setTimeout(poll, interval);
      } catch (error) {
        reject(error);
      }
    };

    poll();
  });
}


/**
 * Format job progress for display
 *
 * @param job - Job status object with progress information
 * @returns Formatted progress string for UI display
 */
export function formatJobProgress(job: any): string {
  if (!job) return 'Unknown';

  const status = job.status;
  const progress = job.progress;

  if (status === 'completed') {
    return 'Complete';
  } else if (status === 'failed') {
    return `Failed: ${job.error || 'Unknown error'}`;
  } else if (status === 'pending') {
    return 'Queued...';
  }

  // For running jobs, show detailed progress
  let message = '';

  // Crawl job progress
  if ('datasets_discovered' in job) {
    message = `${job.datasets_discovered} datasets`;
    // Don't show service estimate if it's clearly wrong (no progress yet)
    if (job.total_services && job.datasets_discovered > 0) {
      message += ` (~${job.services_processed || 0}/${job.total_services} svcs)`;
    }
  }
  // Download job progress
  else if ('features_downloaded' in job) {
    const stage = job.current_stage || 'processing';
    if (job.total_features) {
      const count = job.current_stage === 'storing'
        ? job.features_stored
        : job.features_downloaded;
      message = `${Math.round(progress || 0)}% (${count.toLocaleString()}/${job.total_features.toLocaleString()} features)`;
    } else {
      message = `${Math.round(progress || 0)}%`;
    }
    message = `${stage}: ${message}`;
  }
  // Generic progress
  else if (progress !== null && progress !== undefined) {
    message = `${Math.round(progress)}%`;
  } else {
    message = 'Processing...';
  }

  return message;
}
