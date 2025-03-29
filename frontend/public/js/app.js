document.addEventListener('DOMContentLoaded', function () {
    // Backend API URL - connect directly to Flask backend
    const API_URL = 'http://localhost:5000';

    // Connect to Socket.IO server
    const socket = io(API_URL);

    // Elements
    const archiveForm = document.getElementById('archive-form');
    const inputMethods = document.querySelectorAll('input[name="inputMethod"]');
    const usernameSection = document.getElementById('username-section');
    const fileSection = document.getElementById('file-section');
    const folderSection = document.getElementById('folder-section');
    const userFileInput = document.getElementById('userFile');
    const fileUsersSection = document.getElementById('file-users');
    const userCountSpan = document.getElementById('user-count');
    const usersPreview = document.querySelector('#file-users .users-preview');
    const folderUsers = document.getElementById('folder-users');
    const activeJobSection = document.getElementById('active-job');
    const stopJobButton = document.getElementById('stop-job');
    const jobStatus = document.getElementById('job-status');
    const jobProgress = document.getElementById('job-progress');
    const jobProgressBar = document.getElementById('job-progress-bar');
    const logMessages = document.getElementById('log-messages');
    const downloadsContainer = document.getElementById('downloads-container');
    const duplicateContainer = document.getElementById('duplicate-container');
    const jobsTableBody = document.getElementById('jobs-table-body');

    // State
    let currentJobId = null;
    let uploadedFilePath = null;
    let activeDownloads = {};
    let duplicateRemovals = {};
    let downloadSpeeds = {}; // Track download speeds

    // Socket.IO event handlers
    socket.on('connect', () => {
        console.log('Connected to backend server');
        addLogMessage(new Date().toISOString(), 'Connected to backend server');
    });

    socket.on('disconnect', () => {
        console.log('Disconnected from backend server');
        addLogMessage(new Date().toISOString(), 'Disconnected from backend server');
    });

    socket.on('connect_error', (error) => {
        console.error('Socket.IO connection error:', error);
        addLogMessage(new Date().toISOString(), `Socket connection error: ${error.message}`);
    });

    socket.on('log_update', (data) => {
        if (data.task_id === currentJobId) {
            addLogMessage(data.timestamp, data.log);
            scrollLogsToBottom();
        }
    });

    socket.on('job_update', (data) => {
        if (data.task_id === currentJobId) {
            updateJobStatus(data);
        }

        // Refresh job list
        fetchJobs();
    });

    socket.on('download_progress', (data) => {
        console.log('Download progress event received:', JSON.stringify(data));

        // Validate data
        if (!data || !data.download_id) {
            console.error('Invalid download data received:', data);
            return;
        }

        if (data.task_id === currentJobId) {
            updateDownloadProgress(data);
        }
    });

    socket.on('duplicate_removal_progress', (data) => {
        if (data.task_id === currentJobId) {
            updateDuplicateProgress(data);
        }
    });

    // Event listeners for form controls
    inputMethods.forEach(input => {
        input.addEventListener('change', () => {
            updateInputSections();
        });
    });

    userFileInput.addEventListener('change', () => {
        uploadUserFile();
    });

    archiveForm.addEventListener('submit', (e) => {
        e.preventDefault();
        startArchive();
    });

    stopJobButton.addEventListener('click', () => {
        stopJob();
    });

    // Function to update input sections based on selected method
    function updateInputSections() {
        const selectedMethod = document.querySelector('input[name="inputMethod"]:checked').value;

        usernameSection.style.display = selectedMethod === 'username' ? 'block' : 'none';
        fileSection.style.display = selectedMethod === 'file' ? 'block' : 'none';
        folderSection.style.display = selectedMethod === 'folders' ? 'block' : 'none';

        if (selectedMethod === 'folders') {
            fetchFolderUsers();
        }
    }

    // Function to upload user file
    function uploadUserFile() {
        if (!userFileInput.files.length) return;

        const formData = new FormData();
        formData.append('userFile', userFileInput.files[0]);

        fetch(`${API_URL}/api/users/file`, {
            method: 'POST',
            body: formData
        })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    alert(`Error: ${data.error}`);
                    return;
                }

                uploadedFilePath = data.filepath;
                const users = data.users || [];

                userCountSpan.textContent = users.length;
                usersPreview.innerHTML = '';

                if (users.length) {
                    users.forEach(user => {
                        usersPreview.innerHTML += `<div>u/${user}</div>`;
                    });
                    fileUsersSection.style.display = 'block';
                } else {
                    fileUsersSection.style.display = 'none';
                }
            })
            .catch(error => {
                console.error('Error uploading file:', error);
                alert('Error uploading file');
            });
    }

    // Function to fetch users from folders
    function fetchFolderUsers() {
        folderUsers.innerHTML = 'Loading...';

        fetch(`${API_URL}/api/users/folders`)
            .then(response => response.json())
            .then(users => {
                folderUsers.innerHTML = '';

                if (users.length) {
                    users.forEach(user => {
                        folderUsers.innerHTML += `<div>u/${user}</div>`;
                    });
                } else {
                    folderUsers.innerHTML = 'No user folders found';
                }
            })
            .catch(error => {
                console.error('Error fetching folder users:', error);
                folderUsers.innerHTML = 'Error loading users';
            });
    }

    // Function to start archive process
    function startArchive() {
        const selectedMethod = document.querySelector('input[name="inputMethod"]:checked').value;
        const limit = document.getElementById('limit').value;
        const concurrent = document.getElementById('concurrent').value;

        let data = {
            inputMethod: selectedMethod,
            limit: parseInt(limit, 10),
            concurrent: parseInt(concurrent, 10)
        };

        if (selectedMethod === 'username') {
            data.username = document.getElementById('username').value.trim();
            if (!data.username) {
                alert('Please enter a username');
                return;
            }
        } else if (selectedMethod === 'file') {
            if (!uploadedFilePath) {
                alert('Please upload a file with usernames');
                return;
            }
            data.filepath = uploadedFilePath;
        }

        fetch(`${API_URL}/api/archive/start`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    alert(`Error: ${data.error}`);
                    return;
                }

                currentJobId = data.task_id;

                // Reset containers
                logMessages.innerHTML = '';
                downloadsContainer.innerHTML = '';
                duplicateContainer.innerHTML = '';
                activeDownloads = {};
                duplicateRemovals = {};
                downloadSpeeds = {};

                // Show active job section
                activeJobSection.style.display = 'block';
                jobStatus.textContent = 'Running';
                jobProgress.textContent = '0/0';
                jobProgressBar.style.width = '0%';

                // Add initial log message
                addLogMessage(new Date().toISOString(), data.message);
                scrollLogsToBottom();

                // Fetch initial job status
                fetchJobStatus();
            })
            .catch(error => {
                console.error('Error starting archive:', error);
                alert('Error starting archive process');
            });
    }

    // Function to stop job
    function stopJob() {
        if (!currentJobId) return;

        fetch(`${API_URL}/api/archive/stop/${currentJobId}`, {
            method: 'POST'
        })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    alert(`Error: ${data.error}`);
                    return;
                }

                jobStatus.textContent = 'Stopping...';
                addLogMessage(new Date().toISOString(), 'Stopping job...');
                scrollLogsToBottom();
            })
            .catch(error => {
                console.error('Error stopping job:', error);
                alert('Error stopping job');
            });
    }

    // Function to fetch job status
    function fetchJobStatus() {
        if (!currentJobId) return;

        fetch(`${API_URL}/api/archive/status/${currentJobId}`)
            .then(response => response.json())
            .then(data => {
                updateJobStatus(data);
            })
            .catch(error => {
                console.error('Error fetching job status:', error);
            });
    }

    // Function to update job status
    function updateJobStatus(data) {
        if (!data) return;

        jobStatus.textContent = data.status || 'Unknown';

        const processed = data.processed_users || 0;
        const total = data.total_users || 0;
        jobProgress.textContent = `${processed}/${total}`;

        if (total > 0) {
            const percentage = Math.round((processed / total) * 100);
            jobProgressBar.style.width = `${percentage}%`;
        }

        // If job is completed, failed, or canceled, refresh job list and hide active job section
        if (['completed', 'failed', 'canceled'].includes(data.status)) {
            fetchJobs();

            // Wait a short time to let user see final status before hiding
            setTimeout(() => {
                // Hide the active job section
                activeJobSection.style.display = 'none';

                // Reset current job ID
                currentJobId = null;

                // Clear containers for next job
                logMessages.innerHTML = '';
                downloadsContainer.innerHTML = '';
                duplicateContainer.innerHTML = '';
                activeDownloads = {};
                duplicateRemovals = {};
                downloadSpeeds = {};

                // Add log message about completion
                addLogMessage(new Date().toISOString(), `Job ${data.status}. Check history for details.`);
            }, 3000); // Wait 3 seconds before hiding
        }
    }

    // Function to add log message
    function addLogMessage(timestamp, message) {
        const time = new Date(timestamp).toLocaleTimeString();
        const logElement = document.createElement('div');
        logElement.className = 'log-message';
        logElement.innerHTML = `<span class="log-time">[${time}]</span> ${message}`;
        logMessages.appendChild(logElement);
    }

    // Function to scroll logs to bottom
    function scrollLogsToBottom() {
        const logContainer = document.getElementById('log-container');
        logContainer.scrollTop = logContainer.scrollHeight;
    }

    // Function to calculate download speed
    function calculateSpeed(downloadId, currentBytes, timestamp) {
        if (!downloadSpeeds[downloadId]) {
            downloadSpeeds[downloadId] = {
                lastBytes: 0,
                lastTimestamp: timestamp || Date.now(),
                speed: 0
            };
            return 0;
        }

        const now = timestamp || Date.now();
        const timeDiff = (now - downloadSpeeds[downloadId].lastTimestamp) / 1000; // in seconds

        if (timeDiff > 0) {
            const bytesDiff = currentBytes - downloadSpeeds[downloadId].lastBytes;
            const speed = bytesDiff / timeDiff; // bytes per second

            // Update values for next calculation
            downloadSpeeds[downloadId].lastBytes = currentBytes;
            downloadSpeeds[downloadId].lastTimestamp = now;
            downloadSpeeds[downloadId].speed = speed;

            return speed;
        }

        return downloadSpeeds[downloadId].speed;
    }

    // Function to format speed
    function formatSpeed(bytesPerSecond) {
        return `${formatBytes(bytesPerSecond)}/s`;
    }

    // Function to update download progress
    function updateDownloadProgress(data) {
        // Debug log with complete data
        console.log(`Processing download update: ${data.filename}, Status: ${data.status}, Bytes: ${data.current_bytes}/${data.total_bytes}`, data);

        // Get valid byte counts
        const currentBytes = parseInt(data.current_bytes, 10) || 0;
        const totalBytes = parseInt(data.total_bytes, 10) || 0;

        // Calculate percentage safely
        let percentage = 0;
        if (data.status === 'completed') {
            percentage = 100;
        } else if (totalBytes > 0) {
            percentage = Math.min(100, Math.floor((currentBytes / totalBytes) * 100));
        } else if (data.status === 'progress') {
            // Use indeterminate percentage for unknown size in-progress downloads
            percentage = Math.min(99, Math.floor(Math.random() * 30) + 10);
        }

        // Create or update download element
        const downloadId = data.download_id.replace(/[^a-zA-Z0-9]/g, '-');
        let downloadEl = document.getElementById(`download-${downloadId}`);

        if (!downloadEl) {
            console.log(`Creating new download element for ${data.download_id}`);
            downloadEl = document.createElement('div');
            downloadEl.className = 'download-item';
            downloadEl.id = `download-${downloadId}`;

            // Display appropriate size text
            let sizeText = totalBytes > 0 ? `Size: ${formatBytes(totalBytes)}` : "Size: Unknown";

            downloadEl.innerHTML = `
                <div class="download-filename">${data.filename || 'Unknown file'}</div>
                <div class="progress mb-2">
                    <div class="progress-bar" role="progressbar" style="width: 0%"></div>
                </div>
                <div class="download-status">Starting...</div>
                <div class="download-details">
                    <span class="download-size">${sizeText}</span>
                    <span class="download-speed">Speed: Calculating...</span>
                </div>
            `;

            // Add to beginning of container if in progress
            if (data.status === 'progress' || data.status === 'started') {
                downloadsContainer.insertBefore(downloadEl, downloadsContainer.firstChild);
            } else {
                downloadsContainer.appendChild(downloadEl);
            }

            activeDownloads[data.download_id] = downloadEl;
        }

        const progressBar = downloadEl.querySelector('.progress-bar');
        const statusEl = downloadEl.querySelector('.download-status');
        const speedEl = downloadEl.querySelector('.download-speed');
        const sizeEl = downloadEl.querySelector('.download-size');

        // Update progress
        progressBar.style.width = `${percentage}%`;

        // Update size display
        if (totalBytes > 0) {
            sizeEl.textContent = `Size: ${formatBytes(totalBytes)}`;
        } else if (data.status === 'completed' && currentBytes > 0) {
            sizeEl.textContent = `Size: ${formatBytes(currentBytes)}`;
        }

        // Calculate and update speed
        if (data.status === 'progress' && currentBytes > 0) {
            const speed = calculateSpeed(data.download_id, currentBytes);
            speedEl.textContent = `Speed: ${formatSpeed(speed)}`;

            // Move active downloads to top
            if (downloadsContainer.firstChild !== downloadEl) {
                downloadsContainer.removeChild(downloadEl);
                downloadsContainer.insertBefore(downloadEl, downloadsContainer.firstChild);
            }
        }

        // Update status text
        if (data.status === 'completed') {
            statusEl.textContent = 'Completed';
            statusEl.style.color = 'green';
            speedEl.textContent = 'Speed: Finished';
            progressBar.style.width = '100%';
            progressBar.classList.add('bg-success');
        } else if (data.status === 'failed') {
            statusEl.textContent = `Failed: ${data.error || 'Unknown error'}`;
            statusEl.style.color = 'red';
            speedEl.textContent = 'Speed: Failed';
            progressBar.classList.add('bg-danger');
        } else {
            // For in-progress downloads
            if (totalBytes > 0) {
                statusEl.textContent = `Downloading: ${formatBytes(currentBytes)} / ${formatBytes(totalBytes)} (${percentage}%)`;
            } else {
                statusEl.textContent = `Downloading: ${formatBytes(currentBytes)} / Unknown size`;
            }
        }
    }

    // Function to update duplicate removal progress
    function updateDuplicateProgress(data) {
        const progressId = `${data.username}`;

        // Create or update duplicate element
        if (!duplicateRemovals[progressId]) {
            const duplicateEl = document.createElement('div');
            duplicateEl.className = 'duplicate-item';
            duplicateEl.id = `duplicate-${progressId.replace(/[^a-zA-Z0-9]/g, '-')}`;

            duplicateEl.innerHTML = `
                <div>Removing duplicates for u/${data.username}</div>
                <div class="progress mb-2">
                    <div class="progress-bar" role="progressbar" style="width: 0%"></div>
                </div>
                <div class="duplicate-status">Starting...</div>
            `;

            // Add active items to the top of the list
            if (data.status === 'running') {
                duplicateContainer.insertBefore(duplicateEl, duplicateContainer.firstChild);
            } else {
                duplicateContainer.appendChild(duplicateEl);
            }

            duplicateRemovals[progressId] = duplicateEl;
        }

        const duplicateEl = duplicateRemovals[progressId];
        const progressBar = duplicateEl.querySelector('.progress-bar');
        const statusEl = duplicateEl.querySelector('.duplicate-status');

        // Calculate percentage, ensuring completed tasks show 100%
        let percentage = data.percentage || 0;
        if (data.status === 'completed') {
            percentage = 100;
        }

        // Update progress bar based on percentage
        progressBar.style.width = `${percentage}%`;

        // If actively running, move to the top of the list
        if (data.status === 'running') {
            if (duplicateContainer.firstChild !== duplicateEl) {
                duplicateContainer.removeChild(duplicateEl);
                duplicateContainer.insertBefore(duplicateEl, duplicateContainer.firstChild);
            }
        }

        // Update status text without showing scanning progress
        if (data.status === 'completed') {
            statusEl.textContent = `Completed: Removed ${data.duplicates_removed} duplicates`;
            statusEl.style.color = 'green';

            // Force progress bar to 100% on completion
            progressBar.style.width = '100%';
            progressBar.classList.add('bg-success');
        } else if (data.status === 'failed') {
            statusEl.textContent = `Failed: ${data.error || 'Unknown error'}`;
            statusEl.style.color = 'red';
            progressBar.classList.add('bg-danger');
        } else {
            // Just show duplicates found without misleading scanning progress
            statusEl.textContent = `Processing: ${data.duplicates_found} duplicates found so far`;
        }
    }

    // Function to fetch job history
    function fetchJobs() {
        fetch(`${API_URL}/api/jobs`)
            .then(response => response.json())
            .then(jobs => {
                if (jobs.length === 0) {
                    jobsTableBody.innerHTML = '<tr><td colspan="5">No jobs completed yet</td></tr>';
                    return;
                }

                jobsTableBody.innerHTML = '';

                jobs.forEach(job => {
                    const startTime = new Date(job.start_time).toLocaleString();
                    const endTime = job.end_time ? new Date(job.end_time).toLocaleString() : '-';

                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td>${job.id.substring(0, 8)}...</td>
                        <td>${job.status}</td>
                        <td>${job.processed_users || 0}/${job.total_users || 0}</td>
                        <td>${startTime}</td>
                        <td>${endTime}</td>
                    `;

                    jobsTableBody.appendChild(row);
                });
            })
            .catch(error => {
                console.error('Error fetching jobs:', error);
            });
    }

    // Helper function to format bytes
    function formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes';

        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];

        const i = Math.floor(Math.log(bytes) / Math.log(k));

        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    }

    // Initial setup
    updateInputSections();
    fetchJobs();
});