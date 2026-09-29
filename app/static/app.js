// Placement Readiness & Career Intelligence Portal - Frontend Logic

document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initApiKeyHandler();
    checkSystemStatus();
    loadStudentDropdowns();
    setupRunWorkflowForm();
    setupAgentChat();
    setupToolAnalysisForm();
    setupMemorySearchForm();
    setupCreateStudentForm();
    setupLab6();
    setupLab7();
    setupLab8();
});

// Helper for API headers with custom key
function getAuthHeaders() {
    const headers = { 'Content-Type': 'application/json' };
    const customKey = localStorage.getItem('custom_gemini_api_key');
    if (customKey && customKey.trim()) {
        headers['X-Gemini-API-Key'] = customKey.trim();
    }
    return headers;
}

function initApiKeyHandler() {
    const input = document.getElementById('custom-api-key-input');
    const btn = document.getElementById('save-api-key-btn');
    const savedKey = localStorage.getItem('custom_gemini_api_key');
    if (savedKey && input) {
        input.value = savedKey;
    }
    if (btn) {
        btn.addEventListener('click', () => {
            const val = input.value.trim();
            if (val) {
                localStorage.setItem('custom_gemini_api_key', val);
                alert('🔑 Gemini API Key saved to LocalStorage! Future calls will use your key.');
            } else {
                localStorage.removeItem('custom_gemini_api_key');
                alert('Cleared custom API key. Reverting to default server key.');
            }
            checkSystemStatus();
        });
    }
}

// Dynamic Dropdown loader
async function loadStudentDropdowns(selectIdToPick = null) {
    try {
        const res = await fetch('/students');
        const students = await res.json();

        const runSelect = document.getElementById('run-student-id');
        const toolSelect = document.getElementById('tool-student-id');
        const lab7Select = document.getElementById('lab7-student-id');

        if (runSelect && toolSelect) {
            const html = students.map(s => `
                <option value="${s.student_id}">${s.name} (${s.student_id} - ${s.branch})</option>
            `).join('');

            runSelect.innerHTML = html;
            toolSelect.innerHTML = html;
            if (lab7Select) lab7Select.innerHTML = html;

            if (selectIdToPick) {
                runSelect.value = selectIdToPick;
                toolSelect.value = selectIdToPick;
                if (lab7Select) lab7Select.value = selectIdToPick;
            }
        }
    } catch (e) {
        console.error('Failed to load dynamic students list:', e);
    }
}

// 1. Navigation & Tab Switching
function initNavigation() {
    const tabs = document.querySelectorAll('.nav-tab');
    const panes = document.querySelectorAll('.tab-pane');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            panes.forEach(p => p.classList.remove('active'));

            tab.classList.add('active');
            const targetPaneId = tab.getAttribute('data-tab');
            document.getElementById(targetPaneId).classList.add('active');
        });
    });
}

// 2. System Status Polling
async function checkSystemStatus() {
    const llmBadge = document.getElementById('llm-status-text');
    const llmDot = document.querySelector('#llm-status-badge .status-dot');

    try {
        const res = await fetch('/llm/status', { headers: getAuthHeaders() });
        const data = await res.json();

        if (data.llm_available) {
            const prefix = data.custom_key_used ? '🔑 Custom Gemini' : 'Gemini AI';
            llmBadge.textContent = `${prefix} (${data.model})`;
            llmDot.className = 'status-dot online';
        } else {
            llmBadge.textContent = 'Rule Fallback (No Key)';
            llmDot.className = 'status-dot';
        }
    } catch (e) {
        llmBadge.textContent = 'LLM Offline';
        llmDot.className = 'status-dot';
    }
}

// 3. Tab 1 — Run Workflow (Labs 1-5 Pipeline)
function setupRunWorkflowForm() {
    const form = document.getElementById('run-form');
    const btn = document.getElementById('run-workflow-btn');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const studentId = document.getElementById('run-student-id').value;
        const targetRole = document.getElementById('run-target-role').value;
        const actorRole = document.getElementById('run-actor-role').value;

        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Running Agent Loop...';

        document.getElementById('workflow-placeholder').style.display = 'none';
        document.getElementById('workflow-results').style.display = 'none';

        try {
            const response = await fetch('/run', {
                method: 'POST',
                headers: getAuthHeaders(),
                body: JSON.stringify({
                    student_id: studentId,
                    target_role: targetRole,
                    actor_id: 'system',
                    actor_role: actorRole
                })
            });

            if (!response.ok) {
                const err = await response.json();
                alert(`Error: ${err.detail || 'Failed to run workflow'}`);
                btn.disabled = false;
                btn.innerHTML = '<i class="fa-solid fa-play"></i> Run Agentic Readiness Workflow';
                return;
            }

            const data = await response.json();
            renderWorkflowResults(data);

        } catch (err) {
            alert('Failed to connect to API server.');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-play"></i> Run Agentic Readiness Workflow';
        }
    });
}

function renderWorkflowResults(data) {
    const report = data.report;
    const resultsContainer = document.getElementById('workflow-results');
    resultsContainer.style.display = 'block';

    // Header info
    document.getElementById('report-student-name').textContent = `${report.student_name} (${report.student_id})`;
    document.getElementById('report-target-role').textContent = report.target_role;
    document.getElementById('report-run-id').textContent = data.run_id;
    document.getElementById('report-plan-id').textContent = report.plan_id;

    // Threshold label & score gauge
    const scoreVal = report.overall_readiness_score;
    document.getElementById('score-percentage').textContent = `${scoreVal.toFixed(1)}%`;
    const scoreCircle = document.getElementById('score-circle');
    scoreCircle.setAttribute('stroke-dasharray', `${scoreVal}, 100`);

    const thresholdEl = document.getElementById('report-threshold');
    if (report.meets_threshold) {
        thresholdEl.textContent = '✅ MEETS minimum readiness threshold';
        thresholdEl.className = 'threshold-tag meets';
        scoreCircle.style.stroke = '#10b981';
    } else {
        thresholdEl.textContent = '⚠️ BELOW minimum readiness threshold — additional preparation recommended';
        thresholdEl.className = 'threshold-tag below';
        scoreCircle.style.stroke = '#f59e0b';
    }

    // AI Executive Summary
    const aiSummaryCard = document.getElementById('ai-summary-card');
    if (report.ai_summary) {
        aiSummaryCard.style.display = 'block';
        document.getElementById('ai-summary-text').textContent = report.ai_summary;
    } else {
        aiSummaryCard.style.display = 'none';
    }

    // Metrics breakdown
    const codingScore = report.coding_signals.coding_score || 0;
    const skillCoverage = report.coding_signals.skill_coverage_score || 0;
    const projScore = report.coding_signals.project_score || 0;

    document.getElementById('val-skill-coverage').textContent = `${skillCoverage}%`;
    document.getElementById('bar-skill-coverage').style.width = `${skillCoverage}%`;

    document.getElementById('val-coding-score').textContent = `${codingScore} / 100`;
    document.getElementById('bar-coding-score').style.width = `${codingScore}%`;

    document.getElementById('val-project-score').textContent = `${projScore}%`;
    document.getElementById('bar-project-score').style.width = `${projScore}%`;

    // Strengths
    const strengthsList = document.getElementById('report-strengths-list');
    strengthsList.innerHTML = report.strengths.length > 0 
        ? report.strengths.map(s => `<li class="badge-item">${s}</li>`).join('')
        : '<li class="badge-item">None identified</li>';

    // Skill Gaps
    const gapsList = document.getElementById('report-gaps-list');
    gapsList.innerHTML = report.skill_gaps.length > 0 
        ? report.skill_gaps.map(g => `<li class="badge-item" style="border-color: rgba(245, 158, 11, 0.4);">${g}</li>`).join('')
        : '<li class="badge-item" style="border-color: rgba(16, 185, 129, 0.4);">No skill gaps!</li>';

    // Next steps
    const stepsList = document.getElementById('report-steps-list');
    stepsList.innerHTML = report.recommended_steps.map(step => `<li>${step}</li>`).join('');

    // Historical Cases
    const casesContainer = document.getElementById('report-cases-container');
    if (report.historical_similar_cases && report.historical_similar_cases.length > 0) {
        casesContainer.innerHTML = report.historical_similar_cases.map(c => `
            <div class="case-card">
                <div class="case-header">
                    <span>${c.case_id} • ${c.target_role}</span>
                    <span class="case-outcome ${c.outcome === 'placed' ? 'placed' : 'not-placed'}">${c.outcome}</span>
                </div>
                <div class="case-body">
                    <strong>Score: ${c.readiness_score.toFixed(1)}</strong><br/>
                    ${c.summary}
                </div>
            </div>
        `).join('');
    } else {
        casesContainer.innerHTML = '<p class="description-text">No similar historical cases found.</p>';
    }

    // Raw Text Report
    document.getElementById('report-raw-text').textContent = data.report_text;
    document.getElementById('copy-report-btn').style.display = 'inline-flex';
    document.getElementById('copy-report-btn').onclick = () => {
        navigator.clipboard.writeText(data.report_text);
        alert('Report text copied to clipboard!');
    };
}

// 4. Tab 2 — Interactive Agent Loop (Lab 1)
function setupAgentChat() {
    const form = document.getElementById('agent-input-form');
    const input = document.getElementById('agent-raw-input');
    const chatBox = document.getElementById('chat-box');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text) return;

        // Append user bubble
        appendChatBubble('user', text);
        input.value = '';

        try {
            const response = await fetch('/clarify', {
                method: 'POST',
                headers: getAuthHeaders(),
                body: JSON.stringify({ raw_request: text })
            });

            const data = await response.json();

            if (data.status === 'needs_clarification') {
                let msg = `Request needs clarification. Missing ${data.questions.length} fields:\n`;
                data.questions.forEach(q => {
                    msg += `\n• [${q.field}]: ${q.question}`;
                });
                appendChatBubble('agent', msg);
            } else if (data.status === 'clarified') {
                const req = data.clarified_request;
                appendChatBubble('agent', `Request parsed successfully! Generating Readiness Plan for ${req.student_id} (${req.target_role})...`);
                
                // Call /plan endpoint
                const planRes = await fetch('/plan', {
                    method: 'POST',
                    headers: getAuthHeaders(),
                    body: JSON.stringify({ clarified_request: req })
                });
                const plan = await planRes.json();
                renderActivePlan(plan);
            }
        } catch (e) {
            appendChatBubble('agent', 'Error processing request.');
        }
    });
}

function appendChatBubble(sender, text) {
    const chatBox = document.getElementById('chat-box');
    const div = document.createElement('div');
    div.className = `chat-bubble ${sender}`;
    div.innerHTML = `
        <div class="chat-sender">${sender === 'user' ? 'You' : '<i class="fa-solid fa-robot"></i> PlannerAgent'}</div>
        <p>${text.replace(/\n/g, '<br/>')}</p>
    `;
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function renderActivePlan(plan) {
    const container = document.getElementById('plan-display-container');
    container.innerHTML = `
        <div class="plan-card">
            <h4>Plan ID: <code>${plan.plan_id}</code></h4>
            <p><strong>Student:</strong> ${plan.student_id} | <strong>Target Role:</strong> ${plan.target_role}</p>
            <p><strong>Focus Areas:</strong> ${plan.focus_areas.join(', ') || 'General'}</p>
            <p><strong>Status:</strong> <span class="role-badge">${plan.status}</span></p>
            <hr style="border-color: var(--border-color); margin: 12px 0;"/>
            <p><strong>Steps:</strong></p>
            <ol class="action-steps-list" style="font-size: 12px;">
                ${plan.steps.map(s => `<li>${s}</li>`).join('')}
            </ol>
        </div>
    `;
}

// 5. Tab 3 — Direct Tool Analysis (Lab 2)
function setupToolAnalysisForm() {
    const form = document.getElementById('analyze-form');
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const studentId = document.getElementById('tool-student-id').value;
        const roleName = document.getElementById('tool-role-name').value;

        try {
            const res = await fetch('/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ student_id: studentId, role_name: roleName })
            });

            if (!res.ok) {
                alert('Analysis failed');
                return;
            }

            const data = await res.json();
            document.getElementById('tool-result-container').innerHTML = `
                <div class="info-card">
                    <h4>Analysis Result for ${data.student_id} → ${data.target_role}</h4>
                    <p><strong>Overall Score:</strong> ${data.overall_readiness_score.toFixed(1)} / 100</p>
                    <p><strong>Skill Coverage:</strong> ${data.skill_coverage_score.toFixed(1)}%</p>
                    <p><strong>Coding Score:</strong> ${data.coding_score.toFixed(1)}</p>
                    <p><strong>Project Score:</strong> ${data.project_score.toFixed(1)}%</p>
                    <p><strong>Meets Threshold:</strong> ${data.meets_minimum_threshold ? 'YES ✅' : 'NO ⚠️'}</p>
                    <br/>
                    <p><strong>Strengths:</strong> ${data.strengths.join(', ') || 'None'}</p>
                    <p><strong>Gaps:</strong> ${data.skill_gaps.join(', ') || 'None'}</p>
                </div>
            `;
        } catch (err) {
            alert('Error running tool analysis');
        }
    });
}

// 6. Tab 4 — Memory Search (Lab 4)
function setupMemorySearchForm() {
    const form = document.getElementById('memory-search-form');
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const query = document.getElementById('memory-query').value.trim();
        const k = parseInt(document.getElementById('memory-k').value, 10);

        try {
            const res = await fetch('/memory/similar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: query, k: k })
            });

            const data = await res.json();
            const grid = document.getElementById('memory-results-grid');

            if (data.results.length === 0) {
                grid.innerHTML = '<p class="description-text">No similar cases found in ChromaDB vector store.</p>';
                return;
            }

            grid.innerHTML = data.results.map(c => `
                <div class="case-card">
                    <div class="case-header">
                        <span>${c.case_id} • ${c.target_role}</span>
                        <span class="case-outcome ${c.outcome === 'placed' ? 'placed' : 'not-placed'}">${c.outcome}</span>
                    </div>
                    <div class="case-body">
                        <strong>Score: ${c.readiness_score.toFixed(1)}</strong><br/>
                        ${c.summary}
                    </div>
                </div>
            `).join('');
        } catch (err) {
            alert('Memory search failed');
        }
    });
}

// 7. Tab 5 — Create New Student Profile
function setupCreateStudentForm() {
    const form = document.getElementById('create-student-form');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const btn = document.getElementById('create-student-btn');
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving Profile...';

        const studentId = document.getElementById('new-student-id').value.trim();
        const name = document.getElementById('new-student-name').value.trim();
        const branch = document.getElementById('new-student-branch').value.trim();
        const cgpa = parseFloat(document.getElementById('new-student-cgpa').value);
        
        // Parse skills: e.g. "Python:advanced, Docker:intermediate, Linux:advanced"
        const rawSkillsStr = document.getElementById('new-student-skills').value;
        const skillsObj = {};
        rawSkillsStr.split(',').forEach(item => {
            const parts = item.split(':');
            if (parts.length === 2) {
                skillsObj[parts[0].trim()] = parts[1].trim().toLowerCase();
            } else if (parts[0].trim()) {
                skillsObj[parts[0].trim()] = 'intermediate';
            }
        });

        // Parse projects: e.g. "Cloud Infrastructure Automation, AI Chatbot App"
        const rawProjStr = document.getElementById('new-student-projects').value;
        const projectsList = rawProjStr.split(',').map(p => p.trim()).filter(Boolean);

        const problemsSolved = parseInt(document.getElementById('new-problems-solved').value || '200', 10);
        const contestRating = parseInt(document.getElementById('new-contest-rating').value || '1400', 10);

        const payload = {
            student_id: studentId,
            name: name,
            branch: branch,
            cgpa: cgpa,
            skills: skillsObj,
            projects: projectsList,
            coding_stats: {
                problems_solved: problemsSolved,
                contest_rating: contestRating
            },
            dsa_score: 80.0,
            aptitude_score: 85.0,
            communication_score: 85.0,
            mock_interview_score: 80.0
        };

        try {
            const res = await fetch('/students', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!res.ok) {
                const err = await res.json();
                alert(`Error saving profile: ${JSON.stringify(err.detail)}`);
                return;
            }

            alert(`Profile for ${name} (${studentId}) successfully registered! Switching to Full Pipeline...`);
            
            // Reload dropdowns and select the newly created student
            await loadStudentDropdowns(studentId);

            // Switch UI tab to "Full Pipeline"
            document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
            document.querySelector('[data-tab="workflow-tab"]').classList.add('active');
            document.getElementById('workflow-tab').classList.add('active');

            // Trigger workflow automatically
            document.getElementById('run-form').dispatchEvent(new Event('submit'));

        } catch (err) {
            alert('Failed to connect to API server');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-save"></i> Save Profile & Select for Workflow';
        }
    });
}

// ==========================================
// LAB 7: AGENTIC NODE GRAPH
// ==========================================
let activeLab7Poll = null;

function setupLab7() {
    const form = document.getElementById('lab7-form');
    if (!form) return;
    
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const studentId = document.getElementById('lab7-student-id').value;
        const targetRole = document.getElementById('lab7-target-role').value;
        
        const btn = document.getElementById('lab7-run-btn');
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Starting Graph...';
        
        try {
            const res = await fetch('/runs', {
                method: 'POST',
                headers: getAuthHeaders(),
                body: JSON.stringify({
                    student_id: studentId,
                    target_role: targetRole,
                    actor_id: 'system',
                    actor_role: 'system'
                })
            });
            
            if (!res.ok) {
                const err = await res.json();
                alert(`Failed to start run: ${err.detail || 'Unknown error'}`);
                return;
            }
            const data = await res.json();
            
            // Link to Lab 6 text input for convenience
            const lab6Input = document.getElementById('lab6-run-id');
            if (lab6Input) lab6Input.value = data.run_id;
            
            pollLab7Run(data.run_id);
        } catch (err) {
            alert('Error starting graph');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-play"></i> Start Agentic Node Graph';
        }
    });
}

function pollLab7Run(runId) {
    if (activeLab7Poll) clearInterval(activeLab7Poll);
    
    const updateUI = (data) => {
        document.getElementById('lab7-run-id').textContent = data.run_id || '--';
        document.getElementById('lab7-status-pill').textContent = `Status: ${data.status || 'unknown'}`;
        document.getElementById('lab7-approval').textContent = data.approval_status || '--';
        
        const nodes = ['resume_agent', 'skill_gap_agent', 'coding_analytics_agent', 'job_matching_agent', 'interview_agent', 'validation_agent'];
        nodes.forEach(node => {
            const el = document.getElementById(`node-${node}`);
            if (el) {
                el.className = 'step-item';
                if (data.completed_nodes && data.completed_nodes.includes(node)) {
                    el.classList.add('active');
                    el.style.color = '';
                } else if (data.current_node === node) {
                    el.classList.add('pulsating');
                    el.style.color = '#f59e0b';
                }
            }
        });
        
        if (data.validation_report) {
            document.getElementById('lab7-validation').style.display = 'block';
            document.getElementById('lab7-validation-text').textContent = JSON.stringify(data.validation_report, null, 2);
        } else {
            document.getElementById('lab7-validation').style.display = 'none';
        }
        
        if (data.status !== 'running' && data.status !== 'pending') {
            clearInterval(activeLab7Poll);
        }
    };

    activeLab7Poll = setInterval(async () => {
        try {
            const res = await fetch(`/runs/${runId}`, { headers: getAuthHeaders() });
            if (res.ok) {
                const data = await res.json();
                updateUI(data);
            }
        } catch (e) {
            console.error('Polling error', e);
        }
    }, 1000);
    
    // Initial fetch
    fetch(`/runs/${runId}`, { headers: getAuthHeaders() }).then(r => r.ok && r.json()).then(d => { if(d) updateUI(d); });
}

// ==========================================
// LAB 6: GOVERNED RUNTIME (Audit & Approvals)
// ==========================================
function setupLab6() {
    const fetchBtn = document.getElementById('lab6-fetch-btn');
    if (!fetchBtn) return;
    
    fetchBtn.addEventListener('click', async () => {
        const runId = document.getElementById('lab6-run-id').value.trim();
        if (!runId) return;
        
        try {
            const statRes = await fetch(`/runs/${runId}`, { headers: getAuthHeaders() });
            if (statRes.ok) {
                const statData = await statRes.json();
                document.getElementById('lab6-status').textContent = statData.status || '--';
                document.getElementById('lab6-approval').textContent = statData.approval_status || '--';
                document.getElementById('lab6-budget').textContent = statData.completed_nodes ? `${statData.completed_nodes.length} nodes processed` : '--';
            }
            
            const audRes = await fetch(`/runs/${runId}/audit`, { headers: getAuthHeaders() });
            if (audRes.ok) {
                const audData = await audRes.json();
                const tbody = document.getElementById('lab6-audit-tbody');
                tbody.innerHTML = audData.events.map(e => `
                    <tr style="border-bottom: 1px solid var(--border-color);">
                        <td style="padding: 8px;">${e.node || '--'}</td>
                        <td style="padding: 8px;">${e.action}</td>
                        <td style="padding: 8px;"><span class="pill-tag">${e.status}</span></td>
                        <td style="padding: 8px; font-size: 0.8em; color: var(--text-dim);">${new Date(e.timestamp).toLocaleTimeString()}</td>
                    </tr>
                `).join('');
            }
        } catch(e) {
            alert('Failed to fetch Lab 6 data');
        }
    });

    const actionCall = async (endpoint, method, body=null) => {
        const runId = document.getElementById('lab6-run-id').value.trim();
        if (!runId) return;
        try {
            const res = await fetch(`/runs/${runId}${endpoint}`, {
                method: method,
                headers: getAuthHeaders(),
                body: body ? JSON.stringify(body) : undefined
            });
            if (res.ok) {
                alert('Action executed successfully.');
                fetchBtn.click();
            } else {
                const err = await res.json();
                alert(`Action failed: ${err.detail || 'Unknown'}`);
            }
        } catch(e) { alert('Network Error'); }
    };

    document.getElementById('lab6-resume-btn').addEventListener('click', () => {
        actionCall('/resume', 'POST', { student_id: "student_001", target_role: "Software Engineer", actor_id: "system", actor_role: "system" });
    });
    document.getElementById('lab6-approve-btn').addEventListener('click', () => {
        actionCall('/approve', 'POST', { reviewer_id: 'officer_1', decision: 'approved', comments: 'Looks good' });
    });
    document.getElementById('lab6-reject-btn').addEventListener('click', () => {
        actionCall('/approve', 'POST', { reviewer_id: 'officer_1', decision: 'rejected', comments: 'Rejected' });
    });
    document.getElementById('lab6-revise-btn').addEventListener('click', () => {
        actionCall('/revise', 'POST', { reviewer_id: 'officer_1', feedback: 'Needs more info' });
    });
    document.getElementById('lab6-publish-btn').addEventListener('click', () => {
        actionCall('/publish', 'POST');
    });
}

// ==========================================
// LAB 8: PARALLEL SWARM
// ==========================================
let activeLab8Poll = null;

function setupLab8() {
    const form = document.getElementById('lab8-form');
    if (!form) return;
    
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const idsStr = document.getElementById('lab8-student-ids').value;
        const studentIds = idsStr.split(',').map(s => s.trim()).filter(s => s);
        const targetRole = document.getElementById('lab8-target-role').value;
        
        const btn = document.getElementById('lab8-run-btn');
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Spawning Swarm...';
        
        try {
            const res = await fetch('/batch-runs', {
                method: 'POST',
                headers: getAuthHeaders(),
                body: JSON.stringify({
                    student_ids: studentIds,
                    target_role: targetRole,
                    actor_id: 'system',
                    actor_role: 'system',
                    max_concurrency: 5
                })
            });
            
            if (res.ok) {
                const data = await res.json();
                pollLab8Batch(data.batch_id);
            } else {
                const err = await res.json();
                alert(`Failed to start batch: ${err.detail || 'Unknown'}`);
            }
        } catch (err) {
            alert('Failed to start batch');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-play"></i> Start Parallel Swarm';
        }
    });
}

function pollLab8Batch(batchId) {
    if (activeLab8Poll) clearInterval(activeLab8Poll);
    
    const fetchBatch = async () => {
        try {
            const res = await fetch(`/batch-runs/${batchId}`, { headers: getAuthHeaders() });
            if (res.ok) {
                const data = await res.json();
                updateLab8UI(data);
                
                // If total processed equals total students, we can stop polling
                const totalProcessed = data.successful.length + data.failed.length + data.pending_approval.length + data.requires_review.length;
                if (totalProcessed >= data.total_students) {
                    clearInterval(activeLab8Poll);
                }
            }
        } catch (e) {
            console.error('Batch poll error', e);
        }
    };
    
    fetchBatch(); // immediate fetch
    activeLab8Poll = setInterval(fetchBatch, 2000); // Poll every 2s
}

function updateLab8UI(data) {
    document.getElementById('lab8-batch-id').textContent = `Batch: ${data.batch_id}`;
    
    document.getElementById('lab8-succ-count').textContent = data.successful.length;
    document.getElementById('lab8-fail-count').textContent = data.failed.length;
    document.getElementById('lab8-pend-count').textContent = data.pending_approval.length;
    
    document.getElementById('lab8-succ-list').innerHTML = data.successful.map(r => `<li>${r.student_id}</li>`).join('');
    document.getElementById('lab8-fail-list').innerHTML = data.failed.map(r => `<li>${r.student_id} <span style="color:red;font-size:0.8em">(${r.error || 'error'})</span></li>`).join('');
    document.getElementById('lab8-pend-list').innerHTML = data.pending_approval.map(r => `<li>${r.student_id}</li>`).join('');
    
    document.getElementById('lab8-metrics').textContent = JSON.stringify(data.aggregate_metrics || {}, null, 2);
}

