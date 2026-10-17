// Application State
let currentJobs = [];
let profileData = null;
let trackerData = null;
let selectedFile = null;
let uploadMode = 'file'; // 'file' or 'paste'

// Initialize on Load
document.addEventListener('DOMContentLoaded', () => {
  setupDragAndDrop();
  loadTracker();
});

// Toast Notification
function showToast(message, isSuccess = true) {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.innerHTML = `<span>${isSuccess ? '✓' : 'ℹ'}</span> ${message}`;
  toast.className = `fixed bottom-6 right-6 z-50 text-white text-xs font-semibold px-4 py-3 rounded-xl shadow-2xl transition-all duration-300 flex items-center gap-2 ${isSuccess ? 'bg-emerald-600' : 'bg-blue-600'}`;
  toast.classList.remove('opacity-0', 'pointer-events-none', 'translate-y-4');
  toast.classList.add('opacity-100', 'translate-y-0');

  setTimeout(() => {
    toast.classList.remove('opacity-100', 'translate-y-0');
    toast.classList.add('opacity-0', 'pointer-events-none', 'translate-y-4');
  }, 2600);
}

// Copy to Clipboard Helper
function copyText(text, alertMsg = "Copied to clipboard!") {
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => showToast(alertMsg));
  } else {
    const textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.style.position = "fixed";
    textArea.style.left = "-999999px";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
      document.execCommand('copy');
      showToast(alertMsg);
    } catch (err) {
      showToast("Unable to copy", false);
    }
    textArea.remove();
  }
}

// ============================================================================
// STEP 1: UPLOAD SCREEN LOGIC
// ============================================================================

function setUploadTab(mode) {
  uploadMode = mode;
  const fileZone = document.getElementById('upload-zone-file');
  const pasteZone = document.getElementById('upload-zone-paste');
  const btnFile = document.getElementById('toggle-tab-file');
  const btnPaste = document.getElementById('toggle-tab-paste');

  if (mode === 'file') {
    fileZone.classList.remove('hidden');
    pasteZone.classList.add('hidden');
    btnFile.className = "flex-1 py-2 rounded-lg bg-blue-600 text-white font-bold transition shadow";
    btnPaste.className = "flex-1 py-2 rounded-lg text-gray-400 hover:text-white transition";
  } else {
    fileZone.classList.add('hidden');
    pasteZone.classList.remove('hidden');
    btnPaste.className = "flex-1 py-2 rounded-lg bg-blue-600 text-white font-bold transition shadow";
    btnFile.className = "flex-1 py-2 rounded-lg text-gray-400 hover:text-white transition";
  }
}

function setupDragAndDrop() {
  const dropArea = document.getElementById('drop-area');
  const fileInput = document.getElementById('resume-file-input');
  if (!dropArea || !fileInput) return;

  dropArea.addEventListener('click', () => fileInput.click());

  ['dragenter', 'dragover'].forEach(eventName => {
    dropArea.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropArea.classList.add('border-blue-500', 'bg-blue-950/20');
    }, false);
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropArea.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropArea.classList.remove('border-blue-500', 'bg-blue-950/20');
    }, false);
  });

  dropArea.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length) {
      selectedFile = files[0];
      displaySelectedFile();
    }
  });
}

function handleFileSelected(event) {
  if (event.target.files && event.target.files.length) {
    selectedFile = event.target.files[0];
    displaySelectedFile();
  }
}

function displaySelectedFile() {
  if (!selectedFile) return;
  const info = document.getElementById('selected-file-info');
  const nameEl = document.getElementById('selected-file-name');
  if (info && nameEl) {
    nameEl.innerText = `${selectedFile.name} (${Math.round(selectedFile.size / 1024)} KB)`;
    info.classList.remove('hidden');
  }
}

function clearSelectedFile(event) {
  if (event) event.stopPropagation();
  selectedFile = null;
  const fileInput = document.getElementById('resume-file-input');
  if (fileInput) fileInput.value = '';
  const info = document.getElementById('selected-file-info');
  if (info) info.classList.add('hidden');
}

// Pre-Loaded Profile Transition
async function usePreloadedProfile() {
  animateLoading("Loading sample resume (Sample Fresher)...", 100, async () => {
    await loadProfile();
    await loadJobs();
    loadResumeAudit();
    switchToResultsScreen();
    showToast("Profile loaded: Sample Fresher");
  });
}

// Process Uploaded Resume
async function processResumeUpload() {
  if (uploadMode === 'file') {
    if (!selectedFile) {
      showToast("Please choose a resume file or click 'Use Pre-Loaded Resume'", false);
      return;
    }

    const formData = new FormData();
    formData.append('file', selectedFile);

    animateLoading("Extracting text and analyzing skills...", 75, async () => {
      try {
        const res = await fetch('/api/resume/upload-and-match', {
          method: 'POST',
          body: formData
        });
        const data = await res.json();
        if (data.success) {
          applyParsedData(data);
          switchToResultsScreen();
          showToast(`Resume uploaded: ${data.profile?.name || 'Parsed successfully'}`);
        } else {
          showToast(data.detail || "Error reading file", false);
        }
      } catch (err) {
        showToast("Error uploading resume", false);
      }
    });

  } else {
    // Paste Mode
    const pasteText = document.getElementById('resume-paste-input').value;
    if (!pasteText.trim()) {
      showToast("Please paste your resume text first", false);
      return;
    }

    animateLoading("Analyzing pasted resume content...", 75, async () => {
      try {
        const res = await fetch('/api/resume/paste-and-match', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ resumeText: pasteText })
        });
        const data = await res.json();
        if (data.success) {
          applyParsedData(data);
          switchToResultsScreen();
          showToast(`Resume parsed: ${data.profile?.name || 'Candidate'}`);
        } else {
          showToast(data.detail || "Error parsing text", false);
        }
      } catch (err) {
        showToast("Error processing resume", false);
      }
    });
  }
}

function animateLoading(stepText, targetPercent, callback) {
  const loadingBox = document.getElementById('upload-loading-state');
  const bar = document.getElementById('loading-progress-bar');
  const text = document.getElementById('loading-step-text');
  const pct = document.getElementById('loading-percentage');

  if (!loadingBox) {
    if (callback) callback();
    return;
  }

  loadingBox.classList.remove('hidden');
  text.innerText = stepText;
  bar.style.width = '35%';
  pct.innerText = '35%';

  setTimeout(() => {
    bar.style.width = `${targetPercent}%`;
    pct.innerText = `${targetPercent}%`;
    text.innerText = "Matching against 26 active verified company career portals...";
  }, 400);

  setTimeout(async () => {
    bar.style.width = '100%';
    pct.innerText = '100%';
    text.innerText = "Complete! Unlocking matched openings...";
    if (callback) await callback();
    loadingBox.classList.add('hidden');
  }, 1000);
}

function applyParsedData(data) {
  const profile = data.profile || {};
  const audit = data.audit || {};
  currentJobs = data.rankedJobs || [];

  // Update Candidate Header
  const name = profile.name || "Candidate";
  document.getElementById('profile-name').innerText = name;
  document.getElementById('candidate-seniority').innerText = profile.seniority || "Entry-Level (0–1 Years)";
  document.getElementById('profile-headline').innerText = profile.education || "B.Tech Engineering";
  document.getElementById('profile-email').innerText = profile.email || "Email provided in resume";
  document.getElementById('profile-phone').innerText = profile.phone || "Phone provided in resume";

  // Avatar Initials
  const initials = name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase() || 'CV';
  document.getElementById('candidate-avatar').innerText = initials;

  // Skills banner
  const skillsList = profile.allKeywords || [];
  if (skillsList.length) {
    document.getElementById('resume-skills-summary-text').innerText = 
      `Extracted Key Skills: ${skillsList.slice(0, 8).join(', ').toUpperCase()}`;
  }

  // ATS metrics
  document.getElementById('ats-score-display').innerText = `${audit.atsScore || 90}/100`;
  document.getElementById('quantified-metrics-count').innerText = audit.quantifiedMetricsCount || 4;
  document.getElementById('action-verbs-count').innerText = audit.actionVerbsFound?.length || 10;

  // Render Jobs
  renderJobsGrid(currentJobs);
  document.getElementById('jobs-count-badge').innerText = currentJobs.length;
  document.getElementById('stat-total-jobs').innerText = currentJobs.length;

  const applyFirstCount = currentJobs.filter(j => j.category === 'Apply First').length;
  document.getElementById('apply-first-count-badge').innerText = applyFirstCount;
  const topScore = currentJobs[0]?.fitScore || 94;
  document.getElementById('top-match-score-badge').innerText = `${topScore}%`;
}

function switchToResultsScreen() {
  document.getElementById('view-upload-screen').classList.add('hidden');
  document.getElementById('view-results-screen').classList.remove('hidden');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function goToUploadScreen() {
  document.getElementById('view-results-screen').classList.add('hidden');
  document.getElementById('view-upload-screen').classList.remove('hidden');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ============================================================================
// STEP 2: DASHBOARD / TAB LOGIC
// ============================================================================

function switchTab(tabKey) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
  document.querySelectorAll('.nav-tab-btn').forEach(btn => {
    btn.classList.remove('tab-active');
    btn.classList.add('text-gray-400');
  });

  const pane = document.getElementById(`tab-${tabKey}`);
  const btn = document.getElementById(`btn-tab-${tabKey}`);
  if (pane) pane.classList.remove('hidden');
  if (btn) {
    btn.classList.add('tab-active');
    btn.classList.remove('text-gray-400');
  }

  if (tabKey === 'tracker') loadTracker();
}

async function loadProfile() {
  try {
    const res = await fetch('/api/profile');
    profileData = await res.json();
    renderProfileHeader();
    renderTargetRoles();
  } catch (err) {
    console.error("Error loading profile:", err);
  }
}

function renderProfileHeader() {
  if (!profileData) return;
  document.getElementById('profile-name').innerText = profileData.name || "Sample Fresher";
  document.getElementById('profile-headline').innerText = `${profileData.education?.degree} • ${profileData.education?.institution} (${profileData.education?.aggregate})`;
  document.getElementById('profile-email').innerText = profileData.email;
  document.getElementById('profile-phone').innerText = profileData.phone;
}

// Load and Filter Jobs
async function loadJobs() {
  const q = document.getElementById('filter-search')?.value || '';
  const category = document.getElementById('filter-category')?.value || 'ALL';
  const track = document.getElementById('filter-track')?.value || 'ALL';
  const location = document.getElementById('filter-location')?.value || 'ALL';
  const sort = document.getElementById('filter-sort')?.value || 'fit-desc';

  const params = new URLSearchParams({ q, category, track, location, sort });
  try {
    const res = await fetch(`/api/jobs?${params.toString()}`);
    const data = await res.json();
    currentJobs = data.jobs || [];
    renderJobsGrid(currentJobs);
    document.getElementById('jobs-count-badge').innerText = data.count || currentJobs.length;
    document.getElementById('stat-total-jobs').innerText = data.total || 26;
  } catch (err) {
    console.error("Error loading jobs:", err);
  }
}

function resetJobFilters() {
  if (document.getElementById('filter-search')) document.getElementById('filter-search').value = '';
  if (document.getElementById('filter-category')) document.getElementById('filter-category').value = 'ALL';
  if (document.getElementById('filter-track')) document.getElementById('filter-track').value = 'ALL';
  if (document.getElementById('filter-location')) document.getElementById('filter-location').value = 'ALL';
  if (document.getElementById('filter-sort')) document.getElementById('filter-sort').value = 'fit-desc';
  loadJobs();
}

function renderJobsGrid(jobs) {
  const container = document.getElementById('jobs-grid');
  if (!container) return;

  if (!jobs.length) {
    container.innerHTML = `
      <div class="col-span-full py-16 text-center text-gray-400 bg-gray-900/60 border border-gray-800 rounded-2xl">
        <p class="text-base font-semibold text-gray-300">No active positions match your filters.</p>
        <p class="text-xs text-gray-500 mt-1">Try resetting or broadening your search criteria.</p>
        <button onclick="resetJobFilters()" class="mt-4 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold rounded-lg transition">
          Reset Filters
        </button>
      </div>
    `;
    return;
  }

  container.innerHTML = jobs.map(job => {
    const catClass = job.category === 'Apply First' ? 'badge-apply-first' : (job.category === 'Good Match' ? 'badge-good-match' : 'badge-stretch');
    const isSaved = job.trackerStatus === 'Saved';
    const isApplied = job.trackerStatus === 'Applied';

    return `
      <div class="job-card bg-gray-900 border border-gray-800 rounded-2xl p-5 flex flex-col justify-between">
        <div>
          <div class="flex items-start justify-between gap-3 mb-2.5">
            <div>
              <span class="text-[11px] font-semibold px-2.5 py-0.5 rounded-full ${catClass} inline-block mb-1.5">
                ${job.category}
              </span>
              <h3 class="font-bold text-base text-white hover:text-blue-400 transition cursor-pointer" onclick="openJobModal(${job.id})">
                ${job.title}
              </h3>
              <div class="text-sm font-semibold text-blue-400/90 mt-0.5">${job.company}</div>
            </div>
            
            <div class="w-12 h-12 rounded-xl bg-blue-950/40 border border-blue-500/30 flex flex-col items-center justify-center shrink-0">
              <span class="text-sm font-black text-blue-400">${job.fitScore}</span>
              <span class="text-[8px] uppercase tracking-wider text-gray-400">/ 100</span>
            </div>
          </div>

          <div class="flex flex-wrap items-center gap-2 text-xs text-gray-400 mb-3">
            <span>📍 ${job.location}</span>
            <span>•</span>
            <span>⏳ ${job.experience}</span>
            <span>•</span>
            <span class="text-emerald-400 font-medium">💰 ${job.salaryRange || 'Competitive'}</span>
          </div>

          <p class="text-xs text-gray-400 line-clamp-2 mb-3.5 leading-relaxed">
            ${job.summary}
          </p>

          <div class="flex flex-wrap gap-1.5 mb-4">
            ${(job.keySkills || []).slice(0, 4).map(skill => `
              <span class="text-[11px] px-2 py-0.5 rounded bg-gray-950 border border-gray-800 text-gray-300">
                ${skill}
              </span>
            `).join('')}
          </div>
        </div>

        <div class="pt-3 border-t border-gray-800/80 flex items-center justify-between gap-2 text-xs">
          <select onchange="updateStatus(${job.id}, this.value)" class="bg-gray-950 border border-gray-800 rounded-lg py-1.5 px-2 text-xs text-gray-300 focus:outline-none focus:border-blue-500">
            <option value="none" ${job.trackerStatus === 'None' ? 'selected' : ''}>Status: Not Set</option>
            <option value="saved" ${isSaved ? 'selected' : ''}>★ Saved</option>
            <option value="applied" ${isApplied ? 'selected' : ''}>✓ Applied</option>
            <option value="interviewing" ${job.trackerStatus === 'Interviewing' ? 'selected' : ''}>📅 Interviewing</option>
            <option value="offers" ${job.trackerStatus === 'Offer' ? 'selected' : ''}>🎉 Offer</option>
          </select>

          <div class="flex items-center gap-1.5">
            <button onclick="openJobModal(${job.id})" class="px-2.5 py-1.5 text-xs text-gray-300 hover:text-white bg-gray-800/60 hover:bg-gray-800 rounded-lg transition">
              Analysis
            </button>
            <a href="${job.applyLink}" target="_blank" rel="noopener noreferrer" class="px-3.5 py-1.5 bg-blue-600 hover:bg-blue-500 text-white font-medium rounded-lg transition shadow flex items-center gap-1">
              Apply <span>↗</span>
            </a>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

async function updateStatus(jobId, status) {
  try {
    const res = await fetch(`/api/jobs/${jobId}/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status })
    });
    const result = await res.json();
    if (result.success) {
      showToast(`Status updated: ${status.toUpperCase()}`);
      loadTracker();
    }
  } catch (err) {
    showToast("Failed to update status", false);
  }
}

async function loadTracker() {
  try {
    const res = await fetch('/api/tracker');
    trackerData = await res.json();

    renderKanbanColumn('kanban-saved', trackerData.savedJobs || [], 'saved');
    renderKanbanColumn('kanban-applied', trackerData.appliedJobs || [], 'applied');
    renderKanbanColumn('kanban-interviewing', trackerData.interviewingJobs || [], 'interviewing');
    renderKanbanColumn('kanban-offers', trackerData.offersJobs || [], 'offers');
  } catch (err) {
    console.error("Error loading tracker:", err);
  }
}

function renderKanbanColumn(containerId, jobs, stage) {
  const container = document.getElementById(containerId);
  if (!container) return;

  if (!jobs.length) {
    container.innerHTML = `<div class="p-4 text-center text-xs text-gray-500 italic">No roles in this stage.</div>`;
    return;
  }

  container.innerHTML = jobs.map(job => {
    const note = trackerData.notes?.[String(job.id)] || '';
    return `
      <div class="bg-gray-900 border border-gray-800 rounded-xl p-3.5 space-y-2 text-xs">
        <div class="flex items-start justify-between gap-2">
          <div>
            <h4 class="font-bold text-white">${job.title}</h4>
            <div class="text-xs text-blue-400 font-medium">${job.company}</div>
          </div>
          <span class="text-xs font-black text-emerald-400 bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-500/20">
            ${job.fitScore}%
          </span>
        </div>

        <div class="text-[11px] text-gray-400">📍 ${job.location}</div>

        ${note ? `<div class="bg-gray-950 p-2 rounded text-[11px] text-gray-300 border border-gray-800">📝 ${note}</div>` : ''}

        <div class="flex items-center justify-between pt-2 border-t border-gray-800/80">
          <select onchange="updateStatus(${job.id}, this.value)" class="bg-gray-950 text-[11px] text-gray-300 border border-gray-800 rounded px-1.5 py-1">
            <option value="saved" ${stage === 'saved' ? 'selected' : ''}>Move: Saved</option>
            <option value="applied" ${stage === 'applied' ? 'selected' : ''}>Move: Applied</option>
            <option value="interviewing" ${stage === 'interviewing' ? 'selected' : ''}>Move: Interview</option>
            <option value="offers" ${stage === 'offers' ? 'selected' : ''}>Move: Offer</option>
            <option value="none">Remove</option>
          </select>
          <a href="${job.applyLink}" target="_blank" rel="noopener noreferrer" class="text-blue-400 hover:underline text-[11px]">
            Portal ↗
          </a>
        </div>
      </div>
    `;
  }).join('');
}

function renderTargetRoles() {
  const container = document.getElementById('target-roles-grid');
  if (!container || !profileData?.targetRoles) return;

  container.innerHTML = profileData.targetRoles.map(role => `
    <div class="bg-gray-900 border border-gray-800 rounded-2xl p-5 flex flex-col justify-between hover:border-blue-500/30 transition">
      <div>
        <div class="flex items-start justify-between gap-3 mb-2">
          <h3 class="font-bold text-base text-white">${role.title}</h3>
          <span class="px-2.5 py-0.5 rounded-full text-xs font-black bg-blue-500/20 text-blue-400 border border-blue-500/30 shrink-0">
            ${role.fitScore}% Fit
          </span>
        </div>
        <div class="text-xs text-gray-400 mb-3">Seniority: <span class="text-gray-200 font-medium">${role.seniority}</span></div>

        <div class="space-y-3 text-xs">
          <div class="p-3 bg-gray-950 rounded-xl border border-gray-800">
            <span class="font-bold text-blue-400 block mb-1">Target Companies:</span>
            <span class="text-gray-300">${role.companies.join(', ')}</span>
          </div>
          <div>
            <span class="font-bold text-gray-300 block mb-0.5">Why You Match:</span>
            <p class="text-gray-400 leading-relaxed">${role.rationale}</p>
          </div>
        </div>
      </div>

      <div class="mt-4 pt-3 border-t border-gray-800 flex items-center justify-between text-xs">
        <span class="text-emerald-400 font-medium">Verified Career Match</span>
        <button onclick="document.getElementById('filter-search').value = '${role.title.split(' ')[0]}'; switchTab('jobs'); loadJobs();" class="text-blue-400 hover:text-blue-300 font-semibold">
          View Matching Jobs →
        </button>
      </div>
    </div>
  `).join('');
}

async function openJobModal(jobId) {
  try {
    const res = await fetch(`/api/jobs/${jobId}`);
    const job = await res.json();
    const modal = document.getElementById('job-modal');
    const modalContent = document.getElementById('modal-content');

    const catClass = job.category === 'Apply First' ? 'badge-apply-first' : (job.category === 'Good Match' ? 'badge-good-match' : 'badge-stretch');

    modalContent.innerHTML = `
      <div class="space-y-4">
        <div class="flex items-start justify-between gap-4 border-b border-gray-800 pb-4">
          <div>
            <span class="text-xs font-semibold px-2.5 py-0.5 rounded-full ${catClass} inline-block mb-1">
              ${job.category}
            </span>
            <h2 class="text-xl font-bold text-white">${job.title}</h2>
            <div class="text-base font-semibold text-blue-400">${job.company}</div>
            <div class="text-xs text-gray-400 mt-1">📍 ${job.location} • ⏳ ${job.experience} • 💰 ${job.salaryRange || 'Competitive'}</div>
          </div>
          <div class="text-center p-3 rounded-xl bg-blue-950/40 border border-blue-500/30 shrink-0">
            <div class="text-2xl font-black text-blue-400">${job.fitScore}</div>
            <div class="text-[9px] uppercase tracking-wider text-gray-400">Fit Score</div>
          </div>
        </div>

        <div>
          <h4 class="text-xs font-bold uppercase tracking-wider text-gray-400 mb-1">Position Overview</h4>
          <p class="text-xs md:text-sm text-gray-300 leading-relaxed">${job.summary}</p>
        </div>

        <div class="bg-gray-950 p-4 rounded-xl border border-emerald-500/30 space-y-1">
          <h4 class="text-xs font-bold text-emerald-400 flex items-center gap-1.5">
            <span>✓</span> Why Your Resume Matches This Job
          </h4>
          <p class="text-xs md:text-sm text-gray-300 leading-relaxed">${job.whyMatch}</p>
        </div>

        <div class="bg-gray-950 p-4 rounded-xl border border-amber-500/30 space-y-1">
          <h4 class="text-xs font-bold text-amber-400 flex items-center gap-1.5">
            <span>!</span> Missing Requirements & Recommended Preparation
          </h4>
          <p class="text-xs md:text-sm text-gray-300 leading-relaxed">${job.missingReqs}</p>
        </div>

        <div>
          <h4 class="text-xs font-bold uppercase tracking-wider text-gray-400 mb-2">Evaluated Key Skills</h4>
          <div class="flex flex-wrap gap-1.5">
            ${(job.keySkills || []).map(s => `
              <span class="text-xs px-2.5 py-1 rounded bg-gray-950 border border-gray-800 text-gray-300 font-mono">
                ${s}
              </span>
            `).join('')}
          </div>
        </div>

        <div class="pt-4 border-t border-gray-800 flex items-center justify-between gap-3">
          <select onchange="updateStatus(${job.id}, this.value)" class="bg-gray-950 border border-gray-800 text-xs rounded-xl px-3 py-2 text-gray-300">
            <option value="none" ${job.trackerStatus === 'None' ? 'selected' : ''}>Status: Not Set</option>
            <option value="saved" ${job.trackerStatus === 'Saved' ? 'selected' : ''}>Mark Saved</option>
            <option value="applied" ${job.trackerStatus === 'Applied' ? 'selected' : ''}>Mark Applied</option>
            <option value="interviewing" ${job.trackerStatus === 'Interviewing' ? 'selected' : ''}>Mark Interviewing</option>
            <option value="offers" ${job.trackerStatus === 'Offer' ? 'selected' : ''}>Mark Offer</option>
          </select>

          <a href="${job.applyLink}" target="_blank" rel="noopener noreferrer" class="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-xl text-xs flex items-center gap-1.5 shadow-lg shadow-blue-600/30">
            Open Official Application Page ↗
          </a>
        </div>
      </div>
    `;

    modal.classList.remove('hidden');
  } catch (err) {
    showToast("Error loading job details", false);
  }
}

function closeJobModal() {
  document.getElementById('job-modal').classList.add('hidden');
}

async function loadResumeAudit() {
  try {
    const res = await fetch('/api/resume/audit-existing', { method: 'POST' });
    const data = await res.json();
    const ats = data.atsOptimized?.audit || {};
    document.getElementById('ats-score-display').innerText = `${ats.atsScore || 96}/100`;
    document.getElementById('quantified-metrics-count').innerText = ats.quantifiedMetricsCount || 6;
    document.getElementById('action-verbs-count').innerText = ats.actionVerbsFound?.length || 14;

    const recContainer = document.getElementById('ats-recommendations-list');
    if (recContainer && ats.recommendations) {
      recContainer.innerHTML = ats.recommendations.map(r => `
        <li class="p-2.5 bg-gray-950 rounded-lg border border-gray-800 text-xs text-gray-300 flex items-start gap-2">
          <span class="text-blue-400">✓</span> <span>${r}</span>
        </li>
      `).join('');
    }
  } catch (err) {
    console.error("Error loading resume audit:", err);
  }
}

async function matchJobDescription() {
  const jdText = document.getElementById('jd-input-text').value;
  const roleName = document.getElementById('jd-role-title').value || "Target Job";

  if (!jdText.trim()) {
    showToast("Please paste a Job Description first", false);
    return;
  }

  try {
    const res = await fetch('/api/resume/match-jd', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jobDescription: jdText, jobTitle: roleName })
    });
    const result = await res.json();

    const resultBox = document.getElementById('jd-match-result');
    resultBox.classList.remove('hidden');

    document.getElementById('jd-match-score').innerText = `${result.matchScore}% Match`;
    document.getElementById('jd-matched-skills').innerHTML = result.matchedSkills.map(s => `
      <span class="px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-500/30 text-xs">${s}</span>
    `).join('') || '<span class="text-xs text-gray-500">None detected</span>';

    document.getElementById('jd-missing-skills').innerHTML = result.missingSkills.map(s => `
      <span class="px-2 py-0.5 rounded bg-amber-950 text-amber-400 border border-amber-500/30 text-xs">${s}</span>
    `).join('') || '<span class="text-xs text-emerald-400">All matching!</span>';

    showToast("JD Matched Successfully!");
  } catch (err) {
    showToast("Error analyzing JD", false);
  }
}

async function generateOutreach() {
  const company = document.getElementById('outreach-company').value;
  const role = document.getElementById('outreach-role').value;
  const recruiter = document.getElementById('outreach-recruiter').value;

  if (!company || !role) {
    showToast("Please enter Company and Role title", false);
    return;
  }

  try {
    const res = await fetch('/api/outreach/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ company, role, recruiterName: recruiter })
    });
    const data = await res.json();

    document.getElementById('outreach-result-box').classList.remove('hidden');
    document.getElementById('outreach-note-text').innerText = data.connectionNote;
    document.getElementById('outreach-note-length').innerText = `${data.connectionNoteLength} / 300 chars`;
    document.getElementById('outreach-email-text').innerText = data.inMailMessage;

    showToast("Messages generated successfully!");
  } catch (err) {
    showToast("Error generating outreach", false);
  }
}
