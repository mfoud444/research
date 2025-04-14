let currentTaskId = null;
let currentEventSource = null;

document.addEventListener('DOMContentLoaded', function() {
    // Form submission handler
    const form = document.getElementById('paperForm');
    form.addEventListener('submit', startGeneration);

    // Abort button handler
    const abortBtn = document.getElementById('abortBtn');
    abortBtn.addEventListener('click', abortGeneration);

    // Structure controls
    const structureRadios = document.querySelectorAll('input[name="structure"]');
    const automaticOptions = document.getElementById('automaticOptions');

    // References controls
    const includeReferences = document.getElementById('includeReferences');
    const citationStyle = document.getElementById('citationStyle');
    const citationStyleContainer = citationStyle.parentElement;

    // Chapter count controls
    const chapterCountTypeRadios = document.querySelectorAll('input[name="chapterCountType"]');
    const chapterCountSelect = document.getElementById('chapterCount');
    const customChapterCount = document.getElementById('customChapterCount');
    const chapterCountContainer = chapterCountSelect.parentElement;

    // Word count controls
    const wordCountTypeRadios = document.querySelectorAll('input[name="wordCountType"]');
    const wordCountSelect = document.getElementById('wordCount');
    const customWordCount = document.getElementById('customWordCount');
    const wordCountContainer = wordCountSelect.parentElement;

    // Initialize UI state
    initializeControls();

    // Set up event listeners
    setupEventListeners();

    function initializeControls() {
        // Structure options
        automaticOptions.style.display = 
            document.querySelector('input[name="structure"]:checked').value === 'automatic' 
                ? 'block' 
                : 'none';

        // Citation style
        citationStyleContainer.style.display = includeReferences.checked ? 'block' : 'none';
        citationStyle.disabled = !includeReferences.checked;

        // Chapter count
        const chapterCountType = document.querySelector('input[name="chapterCountType"]:checked').value;
        chapterCountContainer.style.display = chapterCountType === 'manual' ? 'flex' : 'none';
        chapterCountSelect.disabled = chapterCountType !== 'manual';

        // Word count
        const wordCountType = document.querySelector('input[name="wordCountType"]:checked').value;
        wordCountContainer.style.display = wordCountType === 'manual' ? 'flex' : 'none';
        wordCountSelect.disabled = wordCountType !== 'manual';

        // Add custom options
        if (!chapterCountSelect.querySelector('option[value="custom"]')) {
            chapterCountSelect.innerHTML += '<option value="custom">Custom...</option>';
        }
        if (!wordCountSelect.querySelector('option[value="custom"]')) {
            wordCountSelect.innerHTML += '<option value="custom">Custom...</option>';
        }
    }

    function setupEventListeners() {
        // Structure radio changes
        structureRadios.forEach(radio => {
            radio.addEventListener('change', function() {
                automaticOptions.style.display = this.value === 'automatic' ? 'block' : 'none';
            });
        });

        // References checkbox
        includeReferences.addEventListener('change', function() {
            citationStyleContainer.style.display = this.checked ? 'block' : 'none';
            citationStyle.disabled = !this.checked;
        });

        // Chapter count type
        chapterCountTypeRadios.forEach(radio => {
            radio.addEventListener('change', function() {
                const isManual = this.value === 'manual';
                chapterCountContainer.style.display = isManual ? 'flex' : 'none';
                chapterCountSelect.disabled = !isManual;
                customChapterCount.classList.add('hidden');
                chapterCountSelect.classList.remove('hidden');
            });
        });

        // Chapter count select
        chapterCountSelect.addEventListener('change', function() {
            if (this.value === 'custom') {
                this.classList.add('hidden');
                customChapterCount.classList.remove('hidden');
            }
        });

        // Word count type
        wordCountTypeRadios.forEach(radio => {
            radio.addEventListener('change', function() {
                const isManual = this.value === 'manual';
                wordCountContainer.style.display = isManual ? 'flex' : 'none';
                wordCountSelect.disabled = !isManual;
                customWordCount.classList.add('hidden');
                wordCountSelect.classList.remove('hidden');
            });
        });

        // Word count select
        wordCountSelect.addEventListener('change', function() {
            if (this.value === 'custom') {
                this.classList.add('hidden');
                customWordCount.classList.remove('hidden');
            }
        });
    }
});

function startGeneration(event) {
    event.preventDefault();
    
    const form = event.target;
    const abortBtn = document.getElementById('abortBtn');
    const startBtn = document.getElementById('startBtn');
    const progressContainer = document.getElementById('progressContainer');
    const resultContainer = document.getElementById('resultContainer');
    const errorContainer = document.getElementById('errorContainer');
    
    // Show/hide appropriate elements
    startBtn.style.display = 'none';
    abortBtn.style.display = 'block';
    progressContainer.classList.remove('hidden');
    resultContainer.classList.add('hidden');
    errorContainer.classList.add('hidden');

    // Get form data
    const formData = new FormData(form);
    const queryParams = new URLSearchParams(formData);

    // Create SSE connection
    currentEventSource = new EventSource(`/api/stream?${queryParams.toString()}`);
    
    currentEventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        
        if (data.task_id) {
            currentTaskId = data.task_id;
        }
        
        if (data.status === 'aborted') {
            handleAbort();
        }
        
        if (data.error) {
            handleError(data.error);
        }

        updateProgress(data);
    };
    
    currentEventSource.onerror = function() {
        handleError('Connection error occurred');
    };
}

function abortGeneration() {
    if (currentTaskId) {
        fetch(`/api/abort/${currentTaskId}`, {
            method: 'POST'
        }).catch(error => {
            console.error('Failed to abort generation:', error);
        });
        
        if (currentEventSource) {
            currentEventSource.close();
        }
        handleAbort();
    }
}

function handleAbort() {
    currentEventSource?.close();
    document.getElementById('abortBtn').style.display = 'none';
    document.getElementById('startBtn').style.display = 'block';
    document.getElementById('progressContainer').classList.add('hidden');
    showError('Generation aborted');
}

function handleError(message) {
    currentEventSource?.close();
    document.getElementById('abortBtn').style.display = 'none';
    document.getElementById('startBtn').style.display = 'block';
    document.getElementById('progressContainer').classList.add('hidden');
    showError(message);
}

function showError(message) {
    const errorContainer = document.getElementById('errorContainer');
    const errorMessage = document.getElementById('errorMessage');
    errorMessage.textContent = message;
    errorContainer.classList.remove('hidden');
}

function updateProgress(data) {
    // Update progress bar
    if (data.progress) {
        const progressBar = document.getElementById('progressBar');
        const progressText = document.getElementById('progressText');
        progressBar.style.width = `${data.progress}%`;
        progressText.textContent = `${Math.round(data.progress)}%`;
    }

    // Update steps
    if (data.steps) {
        // First render if steps don't exist
        // if (!document.getElementById('step-0')) {
            renderSteps(data.steps);
        // }
        updateSteps(data.steps);
    }

    // Update chapter progress if available
    if (data.chapter_progress) {
        updateChapterProgress(data.chapter_progress);
    }

    // Handle completion
    if (data.status === 'complete' || data.status === 'partial_success') {
        handleCompletion(data);
    }
}

function renderSteps(steps) {
    const progressSteps = document.getElementById('progressSteps');
    progressSteps.innerHTML = ''; // Clear existing steps
    
    steps.forEach(step => {
        const stepElement = document.createElement('div');
        stepElement.className = 'flex items-start';
        stepElement.id = `step-${step.id}`;
        
        let stepContent = `
            <div class="flex-shrink-0 h-5 w-5 text-gray-400 mt-1">
                <i class="far fa-circle" id="step-icon-${step.id}"></i>
            </div>
            <div class="ml-3">
                <p class="text-sm font-medium text-gray-700" id="step-text-${step.id}">${step.text}</p>
                <p class="text-xs text-gray-500 hidden" id="step-message-${step.id}"></p>
        `;
        
        // Add sub-steps if they exist
        if (step.subSteps && step.subSteps.length > 0) {
            stepContent += `<div class="ml-4 mt-2 space-y-2" id="substeps-${step.id}">`;
            step.subSteps.forEach(subStep => {
                stepContent += `
                    <div class="flex items-center">
                        <div class="flex-shrink-0 h-4 w-4 text-gray-400">
                            <i class="far fa-circle" id="substep-icon-${subStep.id}"></i>
                        </div>
                        <div class="ml-2">
                            <p class="text-xs font-medium text-gray-700" id="substep-text-${subStep.id}">${subStep.text}</p>
                            <p class="text-xs text-gray-500 hidden" id="substep-message-${subStep.id}"></p>
                        </div>
                    </div>
                `;
            });
            stepContent += `</div>`;
        }
        
        stepContent += `</div>`;
        stepElement.innerHTML = stepContent;
        progressSteps.appendChild(stepElement);
    });
}

function updateSteps(steps) {
    steps.forEach(step => {
        const icon = document.getElementById(`step-icon-${step.id}`);
        const message = document.getElementById(`step-message-${step.id}`);
        
        if (icon) {
            icon.className = getStepIconClass(step.status);
        }
        
        if (message && step.message) {
            message.textContent = step.message;
            message.classList.remove('hidden');
        }

        // Update sub-steps if they exist
        if (step.subSteps) {
            step.subSteps.forEach(subStep => {
                const subIcon = document.getElementById(`substep-icon-${subStep.id}`);
                const subMessage = document.getElementById(`substep-message-${subStep.id}`);
                
                if (subIcon) {
                    subIcon.className = getStepIconClass(subStep.status);
                }
                
                if (subMessage && subStep.message) {
                    subMessage.textContent = subStep.message;
                    subMessage.classList.remove('hidden');
                }
            });
        }
    });
}

function getStepIconClass(status) {
    switch (status) {
        case 'pending': return 'far fa-circle text-gray-400';
        case 'in-progress': return 'fas fa-spinner fa-spin text-indigo-500';
        case 'complete': return 'fas fa-check-circle text-green-500';
        case 'error': return 'fas fa-exclamation-circle text-red-500';
        default: return 'far fa-circle text-gray-400';
    }
}

function handleCompletion(data) {
    const resultContainer = document.getElementById('resultContainer');
    const abortBtn = document.getElementById('abortBtn');
    const startBtn = document.getElementById('startBtn');

    if (data.docx_file) {
        document.getElementById('downloadDocx').href = `/api/download/${data.docx_file}`;
    }
    if (data.md_file) {
        document.getElementById('downloadMd').href = `/api/download/${data.md_file}`;
    }
    
    resultContainer.classList.remove('hidden');
    abortBtn.style.display = 'none';
    startBtn.style.display = 'block';
}

// Handle page unload
window.addEventListener('beforeunload', function() {
    if (currentTaskId) {
        abortGeneration();
    }
});

function updateChapterProgress(chapterProgress) {
    const container = document.getElementById('chapterProgressContainer');
    const currentChapter = document.getElementById('currentChapter');
    const chapterPercent = document.getElementById('chapterPercent');
    const chapterProgressBar = document.getElementById('chapterProgressBar');
    const chapterTime = document.getElementById('chapterTime');
    const chapterStatus = document.getElementById('chapterStatus');
    const chapterError = document.getElementById('chapterError');

    container.classList.remove('hidden');

    if (chapterProgress.chapter) {
        currentChapter.textContent = `Chapter ${chapterProgress.current}/${chapterProgress.total}: ${chapterProgress.chapter}`;
        chapterPercent.textContent = `${Math.round(chapterProgress.percent)}%`;
        chapterProgressBar.style.width = `${chapterProgress.percent}%`;
        
        if (chapterProgress.duration) {
            chapterTime.textContent = `Time taken: ${chapterProgress.duration}`;
        }
        
        if (chapterProgress.error) {
            chapterStatus.textContent = 'Error';
            chapterError.textContent = chapterProgress.error;
            chapterError.classList.remove('hidden');
        } else {
            chapterStatus.textContent = 'In progress';
            chapterError.classList.add('hidden');
        }
    }

    if (chapterProgress.complete) {
        chapterStatus.textContent = `Completed ${chapterProgress.total_chapters} chapters`;
    }
} 